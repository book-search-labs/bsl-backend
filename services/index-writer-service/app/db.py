import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pymysql

from app.config import Settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def connect(self):
        return pymysql.connect(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_user,
            password=self.settings.mysql_password,
            database=self.settings.mysql_database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    @contextmanager
    def cursor(self):
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def fetch_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        with self.cursor() as cursor:
            cursor.execute("SELECT * FROM reindex_job WHERE reindex_job_id=%s", (job_id,))
            row = cursor.fetchone()
        if not row:
            return None
        row["params_json"] = parse_json(row.get("params_json"))
        row["progress_json"] = parse_json(row.get("progress_json"))
        row["error_json"] = parse_json(row.get("error_json"))
        return row

    def claim_next_job(self) -> Optional[Dict[str, Any]]:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT reindex_job_id FROM reindex_job "
                "WHERE status IN ('CREATED','RESUME','RETRY') "
                "ORDER BY created_at ASC LIMIT 1 FOR UPDATE"
            )
            row = cursor.fetchone()
            if not row:
                return None
            job_id = row["reindex_job_id"]
            cursor.execute(
                "UPDATE reindex_job SET status='PREPARE', started_at=COALESCE(started_at,%s), updated_at=%s "
                "WHERE reindex_job_id=%s",
                (utc_now(), utc_now(), job_id),
            )
        return self.fetch_job(job_id)

    def insert_job(self, logical_name: str, params: Optional[Dict[str, Any]], from_physical: Optional[str]) -> Dict[str, Any]:
        with self.cursor() as cursor:
            cursor.execute(
                "INSERT INTO reindex_job (logical_name, from_physical, to_physical, status, params_json, started_at, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    logical_name,
                    from_physical,
                    None,
                    "CREATED",
                    json.dumps(params or {}),
                    None,
                    utc_now(),
                    utc_now(),
                ),
            )
            job_id = cursor.lastrowid
        return self.fetch_job(job_id)

    def update_job_status(
        self,
        job_id: int,
        status: str,
        progress: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        finished_at: Optional[datetime] = None,
        paused_at: Optional[datetime] = None,
    ) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "UPDATE reindex_job SET status=%s, progress_json=%s, error_json=%s, error_message=%s, "
                "finished_at=%s, paused_at=%s, updated_at=%s WHERE reindex_job_id=%s",
                (
                    status,
                    json.dumps(progress) if progress is not None else None,
                    json.dumps(error) if error is not None else None,
                    error_message,
                    finished_at,
                    paused_at,
                    utc_now(),
                    job_id,
                ),
            )

    def update_job_progress(self, job_id: int, progress: Dict[str, Any]) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "UPDATE reindex_job SET progress_json=%s, updated_at=%s WHERE reindex_job_id=%s",
                (json.dumps(progress), utc_now(), job_id),
            )

    def set_job_field(self, job_id: int, field: str, value: Any) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                f"UPDATE reindex_job SET {field}=%s, updated_at=%s WHERE reindex_job_id=%s",
                (value, utc_now(), job_id),
            )

    def get_job_status(self, job_id: int) -> Optional[str]:
        with self.cursor() as cursor:
            cursor.execute("SELECT status FROM reindex_job WHERE reindex_job_id=%s", (job_id,))
            row = cursor.fetchone()
        return row["status"] if row else None

    def update_job_targets(self, job_id: int, to_physical: Optional[str], from_physical: Optional[str]) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "UPDATE reindex_job SET to_physical=%s, from_physical=%s, updated_at=%s WHERE reindex_job_id=%s",
                (to_physical, from_physical, utc_now(), job_id),
            )

    def get_alias_physical(self, alias_name: str) -> Optional[str]:
        with self.cursor() as cursor:
            cursor.execute("SELECT physical_name FROM search_index_alias WHERE alias_name=%s", (alias_name,))
            row = cursor.fetchone()
        return row["physical_name"] if row else None

    def upsert_alias(self, alias_name: str, physical_name: str) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "INSERT INTO search_index_alias (alias_name, physical_name, switched_at) "
                "VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE physical_name=VALUES(physical_name), switched_at=VALUES(switched_at)",
                (alias_name, physical_name, utc_now()),
            )

    def insert_index_version(self, logical_name: str, physical_name: str, schema_hash: str, status: str) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "INSERT INTO search_index_version (logical_name, physical_name, schema_hash, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE schema_hash=VALUES(schema_hash), status=VALUES(status)",
                (logical_name, physical_name, schema_hash, status, utc_now()),
            )

    def update_index_version_status(self, logical_name: str, physical_name: str, status: str) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "UPDATE search_index_version SET status=%s WHERE logical_name=%s AND physical_name=%s",
                (status, logical_name, physical_name),
            )

    def insert_reindex_error(
        self,
        job_id: int,
        doc_id: str,
        status_code: Optional[int],
        reason: str,
        payload: Optional[Dict[str, Any]],
    ) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "INSERT INTO reindex_error (reindex_job_id, doc_id, status_code, reason, payload_json, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    job_id,
                    doc_id,
                    status_code,
                    reason,
                    json.dumps(payload) if payload is not None else None,
                    utc_now(),
                ),
            )

    def is_event_processed(self, event_id: int, handler: str) -> bool:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM processed_event WHERE event_id=%s AND handler=%s LIMIT 1",
                (event_id, handler),
            )
            row = cursor.fetchone()
        return row is not None

    def mark_event_processed(self, event_id: int, handler: str) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO processed_event (event_id, handler, processed_at) VALUES (%s, %s, %s)",
                (event_id, handler, utc_now()),
            )

    def insert_outbox_event(self, event_type: str, aggregate_type: str, aggregate_id: str, version: str, payload: Dict[str, Any]) -> bool:
        dedup_key = hashlib.sha256(f"{event_type}:{aggregate_id}:{version}".encode("utf-8")).hexdigest()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self.cursor() as cursor:
            affected = cursor.execute(
                "INSERT IGNORE INTO outbox_event "
                "(event_type, aggregate_type, aggregate_id, dedup_key, payload_json, occurred_at, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'NEW')",
                (event_type, aggregate_type, aggregate_id, dedup_key, payload_json, utc_now()),
            )
        return bool(affected)

    def fetch_reconcile_checkpoint(self, checkpoint_name: str) -> Optional[Dict[str, Any]]:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT checkpoint_name, last_updated_at, last_material_id, updated_at "
                "FROM reconcile_checkpoint WHERE checkpoint_name=%s",
                (checkpoint_name,),
            )
            row = cursor.fetchone()
        return row

    def upsert_reconcile_checkpoint(
        self,
        checkpoint_name: str,
        last_updated_at: Optional[datetime],
        last_material_id: Optional[str],
    ) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "INSERT INTO reconcile_checkpoint (checkpoint_name, last_updated_at, last_material_id, updated_at) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE last_updated_at=VALUES(last_updated_at), "
                "last_material_id=VALUES(last_material_id), updated_at=VALUES(updated_at)",
                (checkpoint_name, last_updated_at, last_material_id, utc_now()),
            )

    def fetch_material_delta(
        self,
        last_updated_at: Optional[datetime],
        last_material_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        with self.cursor() as cursor:
            if last_updated_at is None:
                cursor.execute(
                    "SELECT material_id, updated_at, deleted_at "
                    "FROM material ORDER BY updated_at ASC, material_id ASC LIMIT %s",
                    (limit,),
                )
            else:
                cursor.execute(
                    "SELECT material_id, updated_at, deleted_at "
                    "FROM material "
                    "WHERE updated_at > %s OR (updated_at = %s AND material_id > %s) "
                    "ORDER BY updated_at ASC, material_id ASC LIMIT %s",
                    (last_updated_at, last_updated_at, last_material_id or "", limit),
                )
            rows = cursor.fetchall()
        return rows

    def fetch_os_sync_lag_seconds(self) -> int:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT TIMESTAMPDIFF(SECOND, MIN(occurred_at), NOW()) AS lag_sec "
                "FROM outbox_event "
                "WHERE status='NEW' "
                "AND event_type IN ('material.upsert_requested', 'material.delete_requested')"
            )
            row = cursor.fetchone()
        if not row or row.get("lag_sec") is None:
            return 0
        return max(int(row["lag_sec"]), 0)

    def fetch_recent_os_sync_failures(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT event_id, event_type, aggregate_id, retry_count, last_error, occurred_at "
                "FROM outbox_event "
                "WHERE status='FAILED' "
                "AND event_type IN ('material.upsert_requested', 'material.delete_requested') "
                "ORDER BY event_id DESC LIMIT %s",
                (limit,),
            )
            rows = cursor.fetchall()
        return rows
