#!/usr/bin/env python3
import argparse
import os
import sys
from typing import List, Tuple

try:
    import pymysql
except ImportError as exc:
    raise SystemExit(
        "PyMySQL is required. Install with: python3 -m pip install -r scripts/ingest/requirements.txt"
    ) from exc

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")


def log(msg: str) -> None:
    print(msg, flush=True)


def connect_mysql() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def fetch_count(cursor, sql: str, params: Tuple = ()) -> int:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if not row:
        return 0
    return int(list(row.values())[0] or 0)


def check_required(cursor, table: str, columns: List[str]) -> int:
    condition = " OR ".join([f"{col} IS NULL" for col in columns])
    return fetch_count(cursor, f"SELECT COUNT(*) FROM {table} WHERE {condition}")


def run_checks(conn, strict_links: bool) -> int:
    errors = 0
    warnings = 0
    with conn.cursor() as cursor:
        log("[quality] Required field checks")
        required_checks = [
            ("agent", ["agent_id", "agent_type", "raw_payload", "last_payload_hash"]),
            ("concept", ["concept_id", "raw_payload", "last_payload_hash"]),
            ("material", ["material_id", "material_kind", "raw_payload", "last_payload_hash"]),
            ("library", ["library_id", "raw_payload", "last_payload_hash"]),
        ]
        for table, cols in required_checks:
            count = check_required(cursor, table, cols)
            if count > 0:
                errors += 1
                log(f"[quality][ERROR] {table}: {count} rows missing {', '.join(cols)}")
            else:
                log(f"[quality][OK] {table}: required fields present")

        log("[quality] Orphan link checks")
        orphans = [
            (
                "material_agent(material)",
                "SELECT COUNT(*) FROM material_agent ma LEFT JOIN material m ON m.material_id=ma.material_id WHERE m.material_id IS NULL",
                "error",
            ),
            (
                "material_agent(agent)",
                "SELECT COUNT(*) FROM material_agent ma LEFT JOIN agent a ON a.agent_id=ma.agent_id WHERE a.agent_id IS NULL",
                "error" if strict_links else "warn",
            ),
            (
                "material_concept(material)",
                "SELECT COUNT(*) FROM material_concept mc LEFT JOIN material m ON m.material_id=mc.material_id WHERE m.material_id IS NULL",
                "error",
            ),
            (
                "material_concept(concept)",
                "SELECT COUNT(*) FROM material_concept mc LEFT JOIN concept c ON c.concept_id=mc.concept_id WHERE c.concept_id IS NULL",
                "error" if strict_links else "warn",
            ),
        ]
        for name, sql, level in orphans:
            count = fetch_count(cursor, sql)
            if count > 0:
                if level == "error":
                    errors += 1
                    log(f"[quality][ERROR] {name}: {count} orphan rows")
                else:
                    warnings += 1
                    log(f"[quality][WARN] {name}: {count} orphan rows")
            else:
                log(f"[quality][OK] {name}: no orphans")

        log("[quality] Duplicate identifier checks")
        duplicate_isbn = fetch_count(
            cursor,
            """
            SELECT COUNT(*) FROM (
              SELECT value, COUNT(*) AS cnt
              FROM material_identifier
              WHERE scheme IN ('ISBN','ISBN13','isbn','isbn13')
              GROUP BY value
              HAVING COUNT(*) > 1
            ) t
            """,
        )
        if duplicate_isbn > 0:
            warnings += 1
            log(f"[quality][WARN] ISBN duplicates found: {duplicate_isbn}")
        else:
            log("[quality][OK] no duplicate ISBN values")

        log("[quality] Distribution checks")
        cursor.execute("SELECT material_kind, COUNT(*) AS cnt FROM material GROUP BY material_kind")
        rows = cursor.fetchall()
        if rows:
            log("[quality] material_kind distribution:")
            for row in rows:
                log(f"  - {row['material_kind']}: {row['cnt']}")
        else:
            warnings += 1
            log("[quality][WARN] material table empty")

        cursor.execute("SELECT agent_type, COUNT(*) AS cnt FROM agent GROUP BY agent_type")
        rows = cursor.fetchall()
        if rows:
            log("[quality] agent_type distribution:")
            for row in rows:
                log(f"  - {row['agent_type']}: {row['cnt']}")
        else:
            warnings += 1
            log("[quality][WARN] agent table empty")

        cursor.execute(
            "SELECT issued_year, COUNT(*) AS cnt FROM material WHERE issued_year IS NOT NULL "
            "GROUP BY issued_year ORDER BY issued_year DESC LIMIT 5"
        )
        rows = cursor.fetchall()
        if rows:
            log("[quality] recent issued_year distribution (top 5):")
            for row in rows:
                log(f"  - {row['issued_year']}: {row['cnt']}")

    if errors:
        log(f"[quality] FAILED with {errors} error(s)")
        return 1
    if warnings:
        log(f"[quality] completed with {warnings} warning(s)")
    else:
        log("[quality] PASSED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical ETL quality checks")
    parser.add_argument(
        "--strict-links",
        action="store_true",
        help="treat all link-table orphan checks as errors (default: unresolved dimension links are warnings)",
    )
    args = parser.parse_args()
    conn = connect_mysql()
    try:
        return run_checks(conn, strict_links=args.strict_links)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
