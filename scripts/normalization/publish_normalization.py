#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import pymysql
except ImportError as exc:
    raise SystemExit(
        "PyMySQL is required. Install with: python3 -m pip install -r scripts/ingest/requirements.txt"
    ) from exc

ROOT_DIR = Path(__file__).resolve().parents[2]

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")

OUTPUT_PATH = os.environ.get(
    "NORMALIZATION_OUTPUT_PATH",
    str(ROOT_DIR / "var" / "normalization" / "normalization_active.json"),
)


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
        autocommit=False,
    )


def fetch_rule_set(conn, rule_set_id: Optional[int], name: Optional[str], version: Optional[str]) -> Dict[str, Any]:
    with conn.cursor() as cursor:
        if rule_set_id is not None:
            cursor.execute(
                "SELECT * FROM normalization_rule_set WHERE normalization_rule_set_id=%s",
                (rule_set_id,),
            )
        else:
            cursor.execute(
                "SELECT * FROM normalization_rule_set WHERE name=%s AND version=%s",
                (name, version),
            )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("normalization_rule_set not found")
        return row


def activate_rule_set(conn, name: str, rule_set_id: int) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE normalization_rule_set SET status='ARCHIVED' WHERE name=%s AND normalization_rule_set_id!=%s",
            (name, rule_set_id),
        )
        cursor.execute(
            "UPDATE normalization_rule_set SET status='ACTIVE' WHERE normalization_rule_set_id=%s",
            (rule_set_id,),
        )
    conn.commit()


def write_rules(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish normalization rules")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--normalization-rule-set-id", type=int, help="normalization_rule_set_id")
    group.add_argument("--name", type=str, help="rule set name")
    parser.add_argument("--version", type=str, help="rule set version (required with --name)")
    parser.add_argument("--output", type=str, default=OUTPUT_PATH)
    parser.add_argument("--activate-only", action="store_true")

    args = parser.parse_args()

    if args.name and not args.version:
        raise SystemExit("--version is required when using --name")

    conn = connect_mysql()
    try:
        row = fetch_rule_set(conn, args.normalization_rule_set_id, args.name, args.version)
    finally:
        conn.close()

    rule_set_id = row["normalization_rule_set_id"]
    name = row["name"]
    version = row["version"]
    rules_json = row.get("rules_json")

    if isinstance(rules_json, (bytes, bytearray)):
        rules_json = rules_json.decode("utf-8")
    if isinstance(rules_json, str):
        rules_json = json.loads(rules_json)

    payload = {
        "version": version,
        "name": name,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "rules": rules_json,
    }

    conn = connect_mysql()
    try:
        activate_rule_set(conn, name, rule_set_id)
    finally:
        conn.close()

    log(f"[normalization] Activated {name} v{version} (id={rule_set_id})")

    if args.activate_only:
        log("[normalization] Skipping file write")
        return 0

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT_DIR / output_path
    write_rules(output_path, payload)
    log(f"[normalization] Wrote rules: {output_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"[normalization] failed: {exc}")
        sys.exit(1)
