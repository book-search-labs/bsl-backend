#!/usr/bin/env python3
"""
Backfill current offers for materials that do not have an active offer yet.

This script calls the existing Commerce API endpoint:
  GET /api/v1/materials/{materialId}/current-offer

That endpoint already provisions default seller/sku/offer/inventory when missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable, List, Optional

import pymysql


ACTIVE_OFFER_JOIN = """
LEFT JOIN offer o
       ON o.sku_id = s.sku_id
      AND o.status = 'ACTIVE'
      AND (o.start_at IS NULL OR o.start_at <= UTC_TIMESTAMP())
      AND (o.end_at IS NULL OR o.end_at > UTC_TIMESTAMP())
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill missing current offers")
    parser.add_argument("--db-host", default=os.environ.get("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--db-port", type=int, default=int(os.environ.get("MYSQL_PORT", "3306")))
    parser.add_argument("--db-user", default=os.environ.get("MYSQL_USER", "bsl"))
    parser.add_argument("--db-password", default=os.environ.get("MYSQL_PASSWORD", "bsl"))
    parser.add_argument("--db-name", default=os.environ.get("MYSQL_DATABASE", "bsl"))
    parser.add_argument(
        "--commerce-base-url",
        default=os.environ.get("COMMERCE_BASE_URL", "http://localhost:8091"),
        help="Commerce service base URL",
    )
    parser.add_argument("--workers", type=int, default=8, help="Concurrent request workers")
    parser.add_argument("--timeout-seconds", type=float, default=5.0, help="HTTP timeout per request")
    parser.add_argument("--retries", type=int, default=2, help="Retry count for non-2xx calls")
    parser.add_argument("--limit", type=int, default=None, help="Max materials to process")
    parser.add_argument("--all-materials", action="store_true", help="Process all materials (not only missing ones)")
    parser.add_argument("--dry-run", action="store_true", help="Print targets only without API calls")
    return parser.parse_args()


def connect_mysql(args: argparse.Namespace) -> pymysql.Connection:
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_password,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=True,
    )


def fetch_targets(conn: pymysql.Connection, args: argparse.Namespace) -> List[str]:
    with conn.cursor() as cur:
        if args.all_materials:
            sql = "SELECT m.material_id FROM material m ORDER BY m.material_id"
            params: List[object] = []
            if args.limit is not None:
                sql += " LIMIT %s"
                params.append(args.limit)
            cur.execute(sql, params)
        else:
            sql = f"""
                SELECT m.material_id
                  FROM material m
             LEFT JOIN sku s
                    ON s.material_id = m.material_id
                {ACTIVE_OFFER_JOIN}
                 WHERE o.offer_id IS NULL
              ORDER BY m.material_id
            """
            params = []
            if args.limit is not None:
                sql += " LIMIT %s"
                params.append(args.limit)
            cur.execute(sql, params)
        rows = cur.fetchall()
    return [str(row[0]) for row in rows]


def fetch_coverage(conn: pymysql.Connection) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              COUNT(DISTINCT m.material_id) AS total_materials,
              COUNT(DISTINCT s.material_id) AS materials_with_sku,
              COUNT(DISTINCT CASE WHEN o.offer_id IS NOT NULL THEN m.material_id END) AS materials_with_active_offer
            FROM material m
            LEFT JOIN sku s
              ON s.material_id = m.material_id
            {ACTIVE_OFFER_JOIN}
            """
        )
        row = cur.fetchone()
    return {
        "total_materials": int(row[0] or 0),
        "materials_with_sku": int(row[1] or 0),
        "materials_with_active_offer": int(row[2] or 0),
    }


@dataclass
class BackfillResult:
    material_id: str
    ok: bool
    status: int
    message: str
    elapsed_ms: int


def call_current_offer(
    base_url: str,
    material_id: str,
    timeout_seconds: float,
    retries: int,
) -> BackfillResult:
    encoded = urllib.parse.quote(material_id, safe="")
    url = f"{base_url.rstrip('/')}/api/v1/materials/{encoded}/current-offer"
    started = time.time()
    attempts = max(1, retries + 1)

    for idx in range(attempts):
        try:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=timeout_seconds) as resp:
                status = int(resp.status)
                body = resp.read().decode("utf-8", errors="ignore")
                if 200 <= status < 300:
                    return BackfillResult(
                        material_id=material_id,
                        ok=True,
                        status=status,
                        message=extract_message(body),
                        elapsed_ms=int((time.time() - started) * 1000),
                    )
                if idx == attempts - 1:
                    return BackfillResult(
                        material_id=material_id,
                        ok=False,
                        status=status,
                        message=extract_message(body),
                        elapsed_ms=int((time.time() - started) * 1000),
                    )
        except urllib.error.HTTPError as ex:
            body = ex.read().decode("utf-8", errors="ignore")
            if idx == attempts - 1:
                return BackfillResult(
                    material_id=material_id,
                    ok=False,
                    status=int(ex.code),
                    message=extract_message(body),
                    elapsed_ms=int((time.time() - started) * 1000),
                )
        except Exception as ex:  # noqa: BLE001
            if idx == attempts - 1:
                return BackfillResult(
                    material_id=material_id,
                    ok=False,
                    status=0,
                    message=str(ex),
                    elapsed_ms=int((time.time() - started) * 1000),
                )
        time.sleep(0.1 * (idx + 1))

    return BackfillResult(
        material_id=material_id,
        ok=False,
        status=0,
        message="unknown_error",
        elapsed_ms=int((time.time() - started) * 1000),
    )


def extract_message(body: str) -> str:
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except Exception:  # noqa: BLE001
        return body[:200]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            if code and message:
                return f"{code}:{message}"
            if code:
                return str(code)
            if message:
                return str(message)
        if "current_offer" in payload:
            return "ok"
    return str(payload)[:200]


def process_targets(args: argparse.Namespace, targets: Iterable[str]) -> List[BackfillResult]:
    results: List[BackfillResult] = []
    target_list = list(targets)
    total = len(target_list)

    if total == 0:
        return results

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        future_map = {
            executor.submit(
                call_current_offer,
                args.commerce_base_url,
                material_id,
                args.timeout_seconds,
                args.retries,
            ): material_id
            for material_id in target_list
        }

        done = 0
        for future in as_completed(future_map):
            result = future.result()
            results.append(result)
            done += 1
            if done == total or done % 100 == 0:
                success = sum(1 for r in results if r.ok)
                failed = done - success
                print(f"[progress] {done}/{total} success={success} failed={failed}")

    return results


def main() -> int:
    args = parse_args()

    print("[backfill] connecting MySQL")
    conn = connect_mysql(args)
    try:
        before = fetch_coverage(conn)
        print(f"[backfill] coverage(before)={before}")

        targets = fetch_targets(conn, args)
        print(f"[backfill] target_count={len(targets)}")
        if args.dry_run:
            for material_id in targets[:50]:
                print(f"  - {material_id}")
            if len(targets) > 50:
                print(f"  ... ({len(targets) - 50} more)")
            return 0

        started = time.time()
        results = process_targets(args, targets)
        elapsed = int((time.time() - started) * 1000)

        success = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]
        print(
            f"[backfill] done elapsed_ms={elapsed} total={len(results)} "
            f"success={len(success)} failed={len(failed)}"
        )
        if failed:
            print("[backfill] failures (up to 20):")
            for row in failed[:20]:
                print(
                    f"  - material_id={row.material_id} status={row.status} "
                    f"elapsed_ms={row.elapsed_ms} message={row.message}"
                )

        after = fetch_coverage(conn)
        print(f"[backfill] coverage(after)={after}")

        return 0 if not failed else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
