#!/usr/bin/env python3
import argparse
import os
from datetime import datetime
from typing import List, Optional

import pymysql


MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


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


def fetch_event_ids(conn, status: str, event_type: Optional[str], since: Optional[datetime], until: Optional[datetime], limit: int) -> List[int]:
    clauses = ["status=%s"]
    params: List[object] = [status]
    if event_type:
        clauses.append("event_type=%s")
        params.append(event_type)
    if since:
        clauses.append("created_at >= %s")
        params.append(since)
    if until:
        clauses.append("created_at <= %s")
        params.append(until)
    where = " AND ".join(clauses)
    sql = (
        "SELECT event_id FROM outbox_event WHERE "
        + where
        + " ORDER BY event_id ASC LIMIT %s"
    )
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [row["event_id"] for row in rows]


def requeue_events(conn, event_ids: List[int]) -> int:
    if not event_ids:
        return 0
    placeholders = ",".join(["%s"] * len(event_ids))
    sql = f"UPDATE outbox_event SET status='NEW', sent_at=NULL WHERE event_id IN ({placeholders})"
    with conn.cursor() as cur:
        cur.execute(sql, event_ids)
    return len(event_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay outbox events by resetting status to NEW.")
    parser.add_argument("--status", default="FAILED", help="current status to replay (default: FAILED)")
    parser.add_argument("--event-type", help="filter by event_type")
    parser.add_argument("--since", help="start time ISO-8601 (e.g., 2026-01-01T00:00:00)")
    parser.add_argument("--until", help="end time ISO-8601")
    parser.add_argument("--limit", type=int, default=1000, help="max rows to requeue")
    parser.add_argument("--dry-run", action="store_true", help="print count only")
    args = parser.parse_args()

    since = parse_dt(args.since)
    until = parse_dt(args.until)

    conn = connect_mysql()
    try:
        ids = fetch_event_ids(conn, args.status, args.event_type, since, until, args.limit)
        if args.dry_run:
            print(f"[replay] matched {len(ids)} events (dry-run)")
            return 0
        updated = requeue_events(conn, ids)
        conn.commit()
        print(f"[replay] requeued {updated} events")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
