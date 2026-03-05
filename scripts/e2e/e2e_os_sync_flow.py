#!/usr/bin/env python3
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Optional, Tuple
from urllib import error, request
from urllib.parse import quote

import pymysql

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")

OS_URL = os.environ.get("OS_URL", "http://localhost:9200").rstrip("/")
OS_READ_ALIAS = os.environ.get("BOOKS_DOC_READ_ALIAS", "books_doc_read")
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
OS_SYNC_TOPIC = os.environ.get("OS_SYNC_TOPIC", "os.sync.material.v1")
OS_SYNC_HANDLER = os.environ.get("OS_SYNC_HANDLER", "index-writer-os-sync-v1")
TIMEOUT_SEC = int(os.environ.get("OS_SYNC_E2E_TIMEOUT_SEC", "120"))



def log(msg: str) -> None:
    print(f"[os-sync-e2e] {msg}", flush=True)



def connect_mysql():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=False,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )



def outbox_dedup(event_type: str, material_id: str, version: str) -> str:
    return hashlib.sha256(f"{event_type}:{material_id}:{version}".encode("utf-8")).hexdigest()



def enqueue_outbox(conn, event_type: str, material_id: str, version: str) -> Tuple[int, str]:
    dedup_key = outbox_dedup(event_type, material_id, version)
    payload = json.dumps({"version": "v1", "material_id": material_id}, ensure_ascii=False)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO outbox_event "
            "(event_type, aggregate_type, aggregate_id, dedup_key, payload_json, occurred_at, status) "
            "VALUES (%s, 'material', %s, %s, %s, NOW(), 'NEW')",
            (event_type, material_id, dedup_key, payload),
        )
        event_id = int(cur.lastrowid)
    conn.commit()
    return event_id, dedup_key



def wait_outbox_published(conn, dedup_key: str, timeout_sec: int) -> int:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT event_id, status, retry_count, last_error FROM outbox_event WHERE dedup_key=%s",
                (dedup_key,),
            )
            row = cur.fetchone()
        if row and row.get("status") == "PUBLISHED":
            return int(row["event_id"])
        if row and row.get("status") == "FAILED":
            raise RuntimeError(f"outbox publish failed: {row}")
        time.sleep(1)
    raise RuntimeError(f"timeout waiting outbox publish dedup_key={dedup_key}")



def wait_processed(conn, event_id: int, timeout_sec: int) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM processed_event WHERE event_id=%s AND handler=%s LIMIT 1",
                (event_id, OS_SYNC_HANDLER),
            )
            if cur.fetchone():
                return
        time.sleep(1)
    raise RuntimeError(f"timeout waiting processed_event event_id={event_id}")



def os_get_doc(material_id: str) -> Tuple[int, Optional[dict]]:
    url = f"{OS_URL}/{OS_READ_ALIAS}/_source/{quote(material_id, safe='')}"
    req = request.Request(url, method="GET")
    try:
        with request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except error.HTTPError as exc:
        if exc.code == 404:
            return 404, None
        payload = exc.read().decode("utf-8")
        raise RuntimeError(f"OpenSearch read failed: {exc.code} {payload}")



def wait_doc_state(material_id: str, exists: bool, timeout_sec: int) -> Optional[dict]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        status, doc = os_get_doc(material_id)
        if exists and status == 200:
            return doc
        if not exists and status == 404:
            return None
        time.sleep(1)
    raise RuntimeError(f"timeout waiting doc state exists={exists} material_id={material_id}")



def duplicate_kafka_event(material_id: str, event_id: int) -> None:
    try:
        from kafka import KafkaProducer
    except ImportError:
        log("kafka-python not installed; duplicate-event check skipped")
        return

    producer = KafkaProducer(
        bootstrap_servers=[item.strip() for item in KAFKA_BOOTSTRAP_SERVERS.split(",") if item.strip()],
        key_serializer=lambda v: v.encode("utf-8"),
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    )
    envelope = {
        "schema_version": "v1",
        "event_id": str(event_id),
        "event_type": "material.upsert_requested",
        "dedup_key": f"dup-check-{event_id}",
        "occurred_at": datetime.utcnow().isoformat() + "Z",
        "producer": "e2e-os-sync",
        "aggregate_type": "material",
        "aggregate_id": material_id,
        "payload": {"version": "v1", "material_id": material_id},
    }
    producer.send(OS_SYNC_TOPIC, key=material_id, value=envelope).get(timeout=5)
    producer.send(OS_SYNC_TOPIC, key=material_id, value=envelope).get(timeout=5)
    producer.flush(timeout=5)
    producer.close()



def main() -> int:
    material_id = f"os-sync-e2e:{uuid.uuid4().hex[:12]}"
    conn = connect_mysql()

    try:
        log(f"create material {material_id}")
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO material (material_id, material_kind, title, raw_payload, created_at, updated_at, deleted_at) "
                "VALUES (%s, 'BOOK', %s, JSON_OBJECT(), NOW(), NOW(), NULL)",
                (material_id, "OS Sync E2E Title V1"),
            )
        conn.commit()

        log("enqueue upsert event")
        _, dedup1 = enqueue_outbox(conn, "material.upsert_requested", material_id, "v1")
        event_id_1 = wait_outbox_published(conn, dedup1, TIMEOUT_SEC)
        wait_processed(conn, event_id_1, TIMEOUT_SEC)
        doc = wait_doc_state(material_id, exists=True, timeout_sec=TIMEOUT_SEC)
        log(f"upsert reflected in OpenSearch title={doc.get('title_en') or doc.get('title_ko')}")

        log("update material title and enqueue second upsert")
        with conn.cursor() as cur:
            cur.execute("UPDATE material SET title=%s, updated_at=NOW() WHERE material_id=%s", ("OS Sync E2E Title V2", material_id))
        conn.commit()
        _, dedup2 = enqueue_outbox(conn, "material.upsert_requested", material_id, "v2")
        event_id_2 = wait_outbox_published(conn, dedup2, TIMEOUT_SEC)
        wait_processed(conn, event_id_2, TIMEOUT_SEC)
        doc2 = wait_doc_state(material_id, exists=True, timeout_sec=TIMEOUT_SEC)
        title_value = doc2.get("title_en") or doc2.get("title_ko")
        if title_value != "OS Sync E2E Title V2":
            raise RuntimeError(f"unexpected title after update: {title_value}")

        log("duplicate event delivery check (same event_id twice)")
        duplicate_event_id = event_id_2 + 900000000
        duplicate_kafka_event(material_id, duplicate_event_id)
        deadline = time.time() + TIMEOUT_SEC
        while time.time() < deadline:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM processed_event WHERE event_id=%s AND handler=%s",
                    (duplicate_event_id, OS_SYNC_HANDLER),
                )
                row = cur.fetchone()
            count = int((row or {}).get("cnt") or 0)
            if count >= 1:
                if count != 1:
                    raise RuntimeError("duplicate event processed more than once")
                break
            time.sleep(1)
        else:
            raise RuntimeError("duplicate event was not processed in time")

        log("soft-delete material (trigger -> delete_requested)")
        with conn.cursor() as cur:
            cur.execute("UPDATE material SET deleted_at=NOW(), updated_at=NOW() WHERE material_id=%s", (material_id,))
        conn.commit()

        delete_dedup_prefix = outbox_dedup("material.delete_requested", material_id, "")[:16]
        deadline = time.time() + TIMEOUT_SEC
        delete_event_id = None
        while time.time() < deadline:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT event_id, status, dedup_key FROM outbox_event "
                    "WHERE event_type='material.delete_requested' AND aggregate_id=%s "
                    "ORDER BY event_id DESC LIMIT 1",
                    (material_id,),
                )
                row = cur.fetchone()
            if row and row.get("status") == "PUBLISHED":
                delete_event_id = int(row["event_id"])
                break
            if row and row.get("status") == "FAILED":
                raise RuntimeError(f"delete outbox failed: {row}")
            time.sleep(1)

        if delete_event_id is None:
            raise RuntimeError("timeout waiting delete event publish")
        wait_processed(conn, delete_event_id, TIMEOUT_SEC)
        wait_doc_state(material_id, exists=False, timeout_sec=TIMEOUT_SEC)

        log("E2E os sync flow passed")
        return 0
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM material WHERE material_id=%s", (material_id,))
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"FAILED: {exc}")
        raise
