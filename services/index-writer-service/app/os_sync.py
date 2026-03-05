import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from app.config import Settings
from app.db import Database, utc_now
from app.opensearch import OpenSearchClient, TRANSIENT_STATUSES
from app.reindex import build_document, build_select_parts, fetch_map, fetch_single_map, load_table_info

logger = logging.getLogger("index-writer.os-sync")

EVENT_UPSERT = "material.upsert_requested"
EVENT_DELETE = "material.delete_requested"
SUPPORTED_EVENTS = {EVENT_UPSERT, EVENT_DELETE}



def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt



def _version_from_datetime(value: Any) -> str:
    dt = _parse_datetime(value) or utc_now()
    return dt.strftime("%Y%m%d%H%M%S%f")



def _event_version(event_id: Any) -> int:
    try:
        parsed = int(str(event_id).strip())
    except Exception:
        parsed = 0
    if parsed > 0:
        return parsed
    return int(time.time() * 1000)


@dataclass
class OsSyncMetrics:
    processed_total: Dict[str, int] = field(default_factory=dict)
    skipped_duplicate_total: int = 0
    failures_total: Dict[str, int] = field(default_factory=dict)
    dlq_total: int = 0
    reconcile_last_scanned: int = 0
    reconcile_last_requeued: int = 0
    reconcile_last_run_at: Optional[datetime] = None
    last_error: Optional[str] = None

    def inc_processed(self, event_type: str) -> None:
        self.processed_total[event_type] = self.processed_total.get(event_type, 0) + 1

    def inc_failure(self, reason: str, error: Optional[str] = None) -> None:
        self.failures_total[reason] = self.failures_total.get(reason, 0) + 1
        if error:
            self.last_error = error

    def snapshot(self) -> Dict[str, Any]:
        return {
            "processed_total": dict(self.processed_total),
            "skipped_duplicate_total": self.skipped_duplicate_total,
            "failures_total": dict(self.failures_total),
            "dlq_total": self.dlq_total,
            "reconcile_last_scanned": self.reconcile_last_scanned,
            "reconcile_last_requeued": self.reconcile_last_requeued,
            "reconcile_last_run_at": self.reconcile_last_run_at,
            "last_error": self.last_error,
        }


class OsSyncService:
    def __init__(self, settings: Settings, db: Database, client: OpenSearchClient) -> None:
        self.settings = settings
        self.db = db
        self.client = client
        self.metrics = OsSyncMetrics()
        self._table_info: Optional[Dict[str, set[str]]] = None

    def consume_loop(self, stop_event) -> None:
        if not self.settings.os_sync_enabled:
            logger.info("OS sync consumer disabled")
            return

        try:
            from kafka import KafkaConsumer, KafkaProducer
        except ImportError:
            logger.error("kafka-python is required for OS sync consumer; install requirements.txt")
            return

        while not stop_event.is_set():
            consumer = None
            producer = None
            try:
                consumer = KafkaConsumer(
                    self.settings.os_sync_topic,
                    bootstrap_servers=self._bootstrap_servers(),
                    group_id=self.settings.os_sync_group_id,
                    enable_auto_commit=False,
                    auto_offset_reset="earliest",
                    max_poll_records=max(1, self.settings.os_sync_consumer_batch_size),
                    value_deserializer=lambda b: b.decode("utf-8") if b else "",
                    key_deserializer=lambda b: b.decode("utf-8") if b else None,
                    consumer_timeout_ms=1000,
                )
                if self.settings.os_sync_dlq_enabled:
                    producer = KafkaProducer(
                        bootstrap_servers=self._bootstrap_servers(),
                        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                        key_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
                    )

                logger.info(
                    "OS sync consumer started topic=%s group=%s",
                    self.settings.os_sync_topic,
                    self.settings.os_sync_group_id,
                )
                while not stop_event.is_set():
                    records = consumer.poll(
                        timeout_ms=max(int(self.settings.os_sync_poll_timeout_sec * 1000), 100),
                        max_records=max(1, self.settings.os_sync_consumer_batch_size),
                    )
                    if not records:
                        continue
                    for _, rowset in records.items():
                        for record in rowset:
                            self._process_record(record, producer)
                    consumer.commit()
            except Exception as exc:
                self.metrics.inc_failure("consumer_loop_error", str(exc))
                logger.exception("OS sync consumer loop error: %s", exc)
                stop_event.wait(2)
            finally:
                if consumer is not None:
                    try:
                        consumer.close()
                    except Exception:
                        pass
                if producer is not None:
                    try:
                        producer.flush(timeout=5)
                        producer.close()
                    except Exception:
                        pass

    def reconcile_loop(self, stop_event) -> None:
        if not self.settings.os_sync_enabled:
            return
        while not stop_event.is_set():
            try:
                if self.settings.os_sync_reconcile_enabled:
                    self.run_reconcile_once()
            except Exception as exc:
                self.metrics.inc_failure("reconcile_loop_error", str(exc))
                logger.exception("OS sync reconcile loop error: %s", exc)
            stop_event.wait(max(1, self.settings.os_sync_reconcile_interval_sec))

    def run_reconcile_once(self) -> Dict[str, int]:
        checkpoint = self.db.fetch_reconcile_checkpoint(self.settings.os_sync_reconcile_checkpoint_name)
        last_updated_at = checkpoint.get("last_updated_at") if checkpoint else None
        last_material_id = checkpoint.get("last_material_id") if checkpoint else None

        rows = self.db.fetch_material_delta(
            _parse_datetime(last_updated_at),
            last_material_id,
            max(1, self.settings.os_sync_reconcile_batch_size),
        )
        scanned = 0
        requeued = 0
        checkpoint_updated_at = _parse_datetime(last_updated_at)
        checkpoint_material_id = last_material_id

        for row in rows:
            scanned += 1
            material_id = str(row.get("material_id") or "").strip()
            if not material_id:
                continue
            row_updated_at = _parse_datetime(row.get("updated_at"))
            row_deleted_at = _parse_datetime(row.get("deleted_at"))

            should_enqueue = False
            event_type = EVENT_UPSERT
            if row_deleted_at is not None:
                should_enqueue = True
                event_type = EVENT_DELETE
                version = _version_from_datetime(row_deleted_at)
            else:
                should_enqueue = self._is_drifted(material_id, row_updated_at)
                version = _version_from_datetime(row_updated_at)

            if should_enqueue and requeued < max(1, self.settings.os_sync_reconcile_max_enqueue):
                inserted = self.db.insert_outbox_event(
                    event_type,
                    "material",
                    material_id,
                    version,
                    {"version": "v1", "material_id": material_id},
                )
                if inserted:
                    requeued += 1

            checkpoint_updated_at = row_updated_at or checkpoint_updated_at
            checkpoint_material_id = material_id

        if scanned > 0:
            self.db.upsert_reconcile_checkpoint(
                self.settings.os_sync_reconcile_checkpoint_name,
                checkpoint_updated_at,
                checkpoint_material_id,
            )

        self.metrics.reconcile_last_scanned = scanned
        self.metrics.reconcile_last_requeued = requeued
        self.metrics.reconcile_last_run_at = utc_now()
        return {"scanned": scanned, "requeued": requeued}

    def repair(self, material_ids: List[str], action: str = "upsert") -> Dict[str, Any]:
        normalized: List[str] = []
        for material_id in material_ids:
            value = str(material_id or "").strip()
            if value and value not in normalized:
                normalized.append(value)

        if action == "delete":
            event_type = EVENT_DELETE
        else:
            event_type = EVENT_UPSERT

        inserted = 0
        skipped = 0
        base_version = _version_from_datetime(utc_now())
        for idx, material_id in enumerate(normalized):
            version = f"{base_version}{idx:04d}"
            ok = self.db.insert_outbox_event(
                event_type,
                "material",
                material_id,
                version,
                {"version": "v1", "material_id": material_id},
            )
            if ok:
                inserted += 1
            else:
                skipped += 1

        return {
            "requested": len(normalized),
            "inserted": inserted,
            "skipped": skipped,
            "event_type": event_type,
        }

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.settings.os_sync_enabled,
            "topic": self.settings.os_sync_topic,
            "group_id": self.settings.os_sync_group_id,
            "handler": self.settings.os_sync_handler,
            "lag_seconds": self.db.fetch_os_sync_lag_seconds(),
            "metrics": self.metrics.snapshot(),
            "recent_failures": self.db.fetch_recent_os_sync_failures(),
        }

    def _process_record(self, record, producer) -> None:
        envelope = self._parse_envelope(record.value)
        if envelope is None:
            self.metrics.inc_failure("invalid_envelope", "invalid envelope payload")
            return

        event_type = str(envelope.get("event_type") or "").strip()
        if event_type not in SUPPORTED_EVENTS:
            return

        payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        material_id = str(payload.get("material_id") or envelope.get("aggregate_id") or "").strip()
        if not material_id:
            self.metrics.inc_failure("invalid_payload", f"missing material_id event_type={event_type}")
            self._publish_dlq(producer, record.key, envelope, "missing material_id")
            return

        version = _event_version(envelope.get("event_id"))
        event_id = version

        if self.db.is_event_processed(event_id, self.settings.os_sync_handler):
            self.metrics.skipped_duplicate_total += 1
            return

        error_message: Optional[str] = None
        for attempt in range(1, max(1, self.settings.os_sync_retry_max) + 1):
            try:
                if event_type == EVENT_UPSERT:
                    self._upsert_material(material_id, version)
                else:
                    self._delete_material(material_id, version)
                self.db.mark_event_processed(event_id, self.settings.os_sync_handler)
                self.metrics.inc_processed(event_type)
                return
            except Exception as exc:
                error_message = str(exc)
                if attempt < max(1, self.settings.os_sync_retry_max):
                    time.sleep(self.settings.os_sync_retry_backoff_sec * attempt)

        self.metrics.inc_failure("process_error", error_message)
        self._publish_dlq(producer, record.key, envelope, error_message or "process_error")

    def _parse_envelope(self, payload: Any) -> Optional[Dict[str, Any]]:
        if isinstance(payload, dict):
            return payload
        if not isinstance(payload, str):
            return None
        text = payload.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    def _upsert_material(self, material_id: str, version: int) -> None:
        docs = self._fetch_documents([material_id])
        doc = docs.get(material_id)
        if doc is None:
            self._delete_material(material_id, version)
            return

        doc_id = quote(str(doc["doc_id"]), safe="")
        path = f"/{self.settings.doc_alias}/_doc/{doc_id}?version_type=external_gte&version={max(version, 1)}"
        status, body = self.client.request("PUT", path, doc)
        if status in TRANSIENT_STATUSES:
            raise RuntimeError(f"transient upsert error ({status}): {body}")
        if status >= 300:
            raise RuntimeError(f"upsert failed ({status}): {body}")

    def _delete_material(self, material_id: str, version: int) -> None:
        doc_id = quote(material_id, safe="")
        path = f"/{self.settings.doc_alias}/_doc/{doc_id}?version_type=external_gte&version={max(version, 1)}"
        status, body = self.client.request("DELETE", path)
        if status == 404:
            return
        if status in TRANSIENT_STATUSES:
            raise RuntimeError(f"transient delete error ({status}): {body}")
        if status >= 300:
            raise RuntimeError(f"delete failed ({status}): {body}")

    def _fetch_documents(self, material_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        ids = [material_id for material_id in material_ids if material_id]
        if not ids:
            return {}

        conn = self.db.connect()
        try:
            table_info = self._table_info
            if table_info is None:
                table_info = load_table_info(
                    conn,
                    [
                        "material",
                        "material_override",
                        "material_merge",
                        "material_identifier",
                        "material_agent",
                        "agent",
                        "material_concept",
                        "concept",
                        "material_kdc",
                    ],
                    self.settings.mysql_database,
                )
                self._table_info = table_info

            material_cols = table_info.get("material", set())
            if "material_id" not in material_cols:
                return {}

            with conn.cursor() as cursor:
                material_select_cols = build_select_parts(
                    "m",
                    material_cols,
                    required=["material_id"],
                    optional=[
                        "title",
                        "label",
                        "publisher_name",
                        "publisher",
                        "language_code",
                        "language",
                        "issued_year",
                        "extras_json",
                        "kdc_node_id",
                        "updated_at",
                        "deleted_at",
                    ],
                )
                placeholders = ",".join(["%s"] * len(ids))
                cursor.execute(
                    f"SELECT {', '.join(material_select_cols)} FROM material m WHERE m.material_id IN ({placeholders})",
                    ids,
                )
                materials = [
                    row
                    for row in cursor.fetchall()
                    if row.get("deleted_at") is None
                ]
                if not materials:
                    return {}

                resolved_material_ids = [str(row["material_id"]) for row in materials]

                overrides = {}
                override_cols = table_info.get("material_override", set())
                if "material_id" in override_cols:
                    override_select = build_select_parts(
                        "mo",
                        override_cols,
                        required=["material_id"],
                        optional=["title", "language_code", "publisher_name", "issued_year", "hidden"],
                    )
                    overrides = fetch_single_map(
                        cursor,
                        f"SELECT {', '.join(override_select)} FROM material_override mo WHERE material_id IN ({{placeholders}})",
                        resolved_material_ids,
                        "material_id",
                    )

                merges = {}
                merge_cols = table_info.get("material_merge", set())
                if "from_material_id" in merge_cols and "to_material_id" in merge_cols:
                    merges = fetch_single_map(
                        cursor,
                        "SELECT from_material_id AS material_id, to_material_id FROM material_merge "
                        "WHERE from_material_id IN ({placeholders})",
                        resolved_material_ids,
                        "material_id",
                    )

                identifiers = {}
                ident_cols = table_info.get("material_identifier", set())
                if "material_id" in ident_cols and "scheme" in ident_cols and "value" in ident_cols:
                    identifiers = fetch_map(
                        cursor,
                        "SELECT material_id, scheme, value FROM material_identifier WHERE material_id IN ({placeholders})",
                        resolved_material_ids,
                    )

                agents = {}
                ma_cols = table_info.get("material_agent", set())
                agent_cols = table_info.get("agent", set())
                if "material_id" in ma_cols:
                    agent_select = build_select_parts(
                        "ma",
                        ma_cols,
                        required=["material_id"],
                        optional=["role", "ord", "agent_id", "agent_name_raw"],
                    )
                    join_clause = ""
                    if "agent_id" in ma_cols and "agent_id" in agent_cols:
                        join_clause = "LEFT JOIN agent a ON a.agent_id = ma.agent_id"
                        if "preferred_name" in agent_cols:
                            agent_select.append("a.preferred_name")
                        if "pref_label" in agent_cols:
                            agent_select.append("a.pref_label")
                        if "label" in agent_cols:
                            agent_select.append("a.label")
                        if "name" in agent_cols:
                            agent_select.append("a.name")
                    agents = fetch_map(
                        cursor,
                        f"SELECT {', '.join(agent_select)} FROM material_agent ma {join_clause} "
                        "WHERE ma.material_id IN ({placeholders})",
                        resolved_material_ids,
                    )

                concepts = {}
                mc_cols = table_info.get("material_concept", set())
                concept_cols = table_info.get("concept", set())
                if "material_id" in mc_cols and "concept_id" in mc_cols:
                    concept_select = build_select_parts(
                        "mc",
                        mc_cols,
                        required=["material_id", "concept_id"],
                        optional=[],
                    )
                    join_clause = ""
                    if "concept_id" in concept_cols:
                        join_clause = "LEFT JOIN concept c ON c.concept_id = mc.concept_id"
                        if "pref_label" in concept_cols:
                            concept_select.append("c.pref_label")
                        if "label" in concept_cols:
                            concept_select.append("c.label")
                    concepts = fetch_map(
                        cursor,
                        f"SELECT {', '.join(concept_select)} FROM material_concept mc {join_clause} "
                        "WHERE mc.material_id IN ({placeholders})",
                        resolved_material_ids,
                    )

                kdc_rows = {}
                mk_cols = table_info.get("material_kdc", set())
                if "material_id" in mk_cols:
                    kdc_select = build_select_parts(
                        "mk",
                        mk_cols,
                        required=["material_id"],
                        optional=["kdc_code_raw", "kdc_code_3", "kdc_node_id", "ord", "is_primary"],
                    )
                    kdc_rows = fetch_map(
                        cursor,
                        f"SELECT {', '.join(kdc_select)} FROM material_kdc mk WHERE mk.material_id IN ({{placeholders}})",
                        resolved_material_ids,
                    )

            docs: Dict[str, Dict[str, Any]] = {}
            for material in materials:
                doc = build_document(material, overrides, merges, identifiers, agents, concepts, kdc_rows)
                docs[str(material["material_id"])] = doc
            return docs
        finally:
            conn.close()

    def _is_drifted(self, material_id: str, material_updated_at: Optional[datetime]) -> bool:
        if material_updated_at is None:
            return False
        path = f"/{self.settings.doc_read_alias}/_source/{quote(material_id, safe='')}"
        status, body = self.client.request("GET", path)
        if status == 404:
            return True
        if status >= 300:
            raise RuntimeError(f"failed to read os document ({status}): {body}")
        try:
            doc = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid os document payload: {exc}") from exc
        doc_updated_at = _parse_datetime(doc.get("updated_at"))
        if doc_updated_at is None:
            return True
        return doc_updated_at < material_updated_at

    def _publish_dlq(self, producer, key: Optional[str], envelope: Dict[str, Any], error_message: str) -> None:
        if producer is None or not self.settings.os_sync_dlq_enabled:
            return
        try:
            dlq_payload = dict(envelope)
            dlq_payload["failed_at"] = utc_now().isoformat()
            dlq_payload["original_topic"] = self.settings.os_sync_topic
            dlq_payload["error"] = error_message
            producer.send(
                f"{self.settings.os_sync_topic}{self.settings.os_sync_dlq_suffix}",
                key=key,
                value=dlq_payload,
            ).get(timeout=5)
            self.metrics.dlq_total += 1
        except Exception as exc:
            self.metrics.inc_failure("dlq_publish_error", str(exc))

    def _bootstrap_servers(self) -> List[str]:
        return [item.strip() for item in self.settings.kafka_bootstrap_servers.split(",") if item.strip()]
