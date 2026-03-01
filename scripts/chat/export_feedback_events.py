#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pymysql


MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")


def connect_mysql():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=True,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _sha256_prefix(text: str, length: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def normalize_feedback_record(row: dict[str, Any], *, include_comment: bool) -> dict[str, Any]:
    payload = parse_payload(row.get("payload_json"))
    comment = str(payload.get("comment") or "").strip()
    normalized: dict[str, Any] = {
        "version": str(payload.get("version") or "v1"),
        "trace_id": payload.get("trace_id"),
        "request_id": payload.get("request_id"),
        "session_id": payload.get("session_id"),
        "message_id": payload.get("message_id"),
        "rating": payload.get("rating"),
        "reason_code": payload.get("reason_code"),
        "flag_hallucination": payload.get("flag_hallucination"),
        "flag_insufficient": payload.get("flag_insufficient"),
        "actor_user_id": payload.get("actor_user_id"),
        "auth_mode": payload.get("auth_mode"),
        "event_time": payload.get("event_time"),
        "outbox_event_id": row.get("event_id"),
        "outbox_status": row.get("status"),
        "outbox_created_at": str(row.get("created_at")) if row.get("created_at") is not None else None,
    }
    if include_comment:
        normalized["comment"] = comment
    elif comment:
        normalized["comment_hash"] = _sha256_prefix(comment)
    return normalized


def fetch_feedback_rows(
    conn,
    *,
    event_type: str,
    status: str | None,
    since_iso: str | None,
    limit: int,
) -> List[Dict[str, Any]]:
    where = ["event_type=%s"]
    params: list[Any] = [event_type]
    if status:
        where.append("status=%s")
        params.append(status)
    if since_iso:
        where.append("created_at >= %s")
        params.append(since_iso)
    sql = (
        "SELECT event_id, aggregate_id, payload_json, status, created_at "
        "FROM outbox_event "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY event_id ASC "
        "LIMIT %s"
    )
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return list(cur.fetchall())


def resolve_since_iso(days: int) -> str:
    ts = datetime.now(timezone.utc) - timedelta(days=max(0, days))
    return ts.replace(microsecond=0).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export chat feedback outbox events to JSONL.")
    parser.add_argument("--event-type", default="chat_feedback_v1")
    parser.add_argument("--status", default="", help="optional outbox status filter (e.g. NEW/SENT/FAILED)")
    parser.add_argument("--since", default="", help="ISO8601 lower-bound for outbox created_at")
    parser.add_argument("--days", type=int, default=7, help="when --since is empty, export recent N days")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--output", default="evaluation/chat/feedback.jsonl")
    parser.add_argument("--include-comment", action="store_true", help="include raw comment text")
    args = parser.parse_args()

    since_iso = str(args.since or "").strip() or resolve_since_iso(args.days)
    conn = connect_mysql()
    try:
        rows = fetch_feedback_rows(
            conn,
            event_type=str(args.event_type or "chat_feedback_v1").strip(),
            status=str(args.status or "").strip() or None,
            since_iso=since_iso,
            limit=max(1, int(args.limit)),
        )
    finally:
        conn.close()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exported = len(rows)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            record = normalize_feedback_record(row, include_comment=bool(args.include_comment))
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    if exported <= 0:
        print(f"[WARN] no feedback events found; wrote empty file -> {output_path}")
        return 0
    print(f"[OK] wrote {exported} feedback records -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
