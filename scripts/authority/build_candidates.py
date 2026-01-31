#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

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

ISBN_SCHEMES = ("ISBN", "ISBN13", "isbn", "isbn13")


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


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    lowered = value.lower()
    return re.sub(r"[^a-z0-9가-힣]", "", lowered)


def hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fetch_material_details(cursor, material_ids: List[str]) -> Dict[str, Dict]:
    if not material_ids:
        return {}
    placeholders = ",".join(["%s"] * len(material_ids))
    cursor.execute(
        f"SELECT material_id, title, subtitle, publisher, description, issued_year FROM material WHERE material_id IN ({placeholders})",
        material_ids,
    )
    rows = cursor.fetchall()
    return {row["material_id"]: row for row in rows}


def score_material(row: Dict) -> Tuple[int, int, str]:
    score = 0
    if row.get("title"):
        score += 2
    if row.get("subtitle"):
        score += 1
    if row.get("publisher"):
        score += 1
    if row.get("description"):
        score += 1
    issued_year = row.get("issued_year") or 0
    return (score, issued_year, row.get("material_id"))


def choose_material_master(details: Dict[str, Dict]) -> Optional[str]:
    if not details:
        return None
    best_id = None
    best_key = None
    for material_id, row in details.items():
        row = dict(row)
        row["material_id"] = material_id
        key = score_material(row)
        if best_key is None or key > best_key:
            best_key = key
            best_id = material_id
    return best_id


def json_payload(data: Dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build authority merge candidates")
    parser.add_argument("--rule-version", type=str, default="v1")
    parser.add_argument("--since-date", type=str, help="filter materials/agents updated_at >= date (YYYY-MM-DD)")
    parser.add_argument("--max-materials", type=int, help="limit material rows for title/author grouping")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = connect_mysql()
    try:
        with conn.cursor() as cursor:
            build_material_groups(cursor, args.rule_version, args.since_date, args.max_materials, args.dry_run)
            build_agent_alias_candidates(cursor, args.rule_version, args.since_date, args.dry_run)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    return 0


def build_material_groups(cursor, rule_version: str, since_date: Optional[str], max_materials: Optional[int], dry_run: bool) -> None:
    log("[authority] material merge candidates")

    where_clause = ""
    params: List = []
    if since_date:
        where_clause = "WHERE m.updated_at >= %s"
        params.append(since_date)

    cursor.execute(
        f"""
        SELECT mi.value AS isbn, GROUP_CONCAT(mi.material_id) AS ids, COUNT(*) AS cnt
        FROM material_identifier mi
        JOIN material m ON m.material_id = mi.material_id
        WHERE mi.scheme IN ({','.join(['%s'] * len(ISBN_SCHEMES))})
        {"AND m.updated_at >= %s" if since_date else ""}
        GROUP BY mi.value
        HAVING COUNT(*) > 1
        """,
        [*ISBN_SCHEMES, *params],
    )
    isbn_groups = cursor.fetchall()
    created = 0

    for row in isbn_groups:
        ids = row["ids"].split(",") if row.get("ids") else []
        ids = sorted({item.strip() for item in ids if item.strip()})
        if len(ids) < 2:
            continue
        details = fetch_material_details(cursor, ids)
        master_id = choose_material_master(details) or ids[0]
        group_key = hash_key(f"isbn|{row['isbn']}|{','.join(ids)}")
        payload = {
            "rule": "isbn",
            "isbn": row["isbn"],
            "members": ids,
            "master": master_id,
        }
        if not dry_run:
            cursor.execute(
                """
                INSERT INTO material_merge_group (status, rule_version, group_key, master_material_id, members_json)
                VALUES ('OPEN', %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  master_material_id=VALUES(master_material_id),
                  members_json=VALUES(members_json),
                  updated_at=NOW()
                """,
                (rule_version, group_key, master_id, json_payload(payload)),
            )
        created += 1

    log(f"[authority] isbn groups processed: {created}")

    cursor.execute(
        """
        SELECT
          m.material_id,
          m.title,
          m.issued_year,
          MIN(COALESCE(a.pref_label, a.label, a.name, ma.agent_name_raw)) AS author_name
        FROM material m
        LEFT JOIN material_agent ma ON ma.material_id = m.material_id
        LEFT JOIN agent a ON a.agent_id = ma.agent_id
        {where}
        GROUP BY m.material_id
        {limit}
        """.format(
            where=f"WHERE m.updated_at >= %s" if since_date else "",
            limit="LIMIT %s" if max_materials else "",
        ),
        ([since_date] if since_date else []) + ([max_materials] if max_materials else []),
    )
    rows = cursor.fetchall()
    buckets: Dict[str, List[str]] = {}
    for row in rows:
        title_norm = normalize_text(row.get("title"))
        author_norm = normalize_text(row.get("author_name"))
        if not title_norm or not author_norm:
            continue
        year = row.get("issued_year") or 0
        key = f"title_author_year|{title_norm}|{author_norm}|{year}"
        buckets.setdefault(key, []).append(row["material_id"])

    title_groups = 0
    for key, members in buckets.items():
        if len(members) < 2:
            continue
        ids = sorted({item for item in members if item})
        if len(ids) < 2:
            continue
        details = fetch_material_details(cursor, ids)
        master_id = choose_material_master(details) or ids[0]
        group_key = hash_key(f"title|{key}|{','.join(ids)}")
        payload = {
            "rule": "title_author_year",
            "key": key,
            "members": ids,
            "master": master_id,
        }
        if not dry_run:
            cursor.execute(
                """
                INSERT INTO material_merge_group (status, rule_version, group_key, master_material_id, members_json)
                VALUES ('OPEN', %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  master_material_id=VALUES(master_material_id),
                  members_json=VALUES(members_json),
                  updated_at=NOW()
                """,
                (rule_version, group_key, master_id, json_payload(payload)),
            )
        title_groups += 1

    log(f"[authority] title/author/year groups processed: {title_groups}")


def build_agent_alias_candidates(cursor, rule_version: str, since_date: Optional[str], dry_run: bool) -> None:
    log("[authority] agent alias candidates")
    params: List = []
    where_clause = ""
    if since_date:
        where_clause = "WHERE updated_at >= %s"
        params.append(since_date)

    cursor.execute(
        f"""
        SELECT
          agent_id,
          COALESCE(pref_label, label, name) AS display_name,
          isni,
          birth_year,
          death_year,
          job_title
        FROM agent
        {where_clause}
        """,
        params,
    )
    rows = cursor.fetchall()

    buckets: Dict[str, List[Dict]] = {}
    for row in rows:
        display_name = row.get("display_name")
        norm = normalize_text(display_name)
        if not norm:
            continue
        buckets.setdefault(norm, []).append(row)

    created = 0
    for norm_name, entries in buckets.items():
        if len(entries) < 2:
            continue
        def score(entry: Dict) -> Tuple[int, int, str]:
            score_val = 0
            if entry.get("isni"):
                score_val += 3
            for key in ("birth_year", "death_year", "job_title", "display_name"):
                if entry.get(key):
                    score_val += 1
            return (score_val, int(entry.get("birth_year") or 0), entry.get("agent_id"))

        canonical = sorted(entries, key=score, reverse=True)[0]
        members = sorted({entry["agent_id"] for entry in entries if entry.get("agent_id")})
        if len(members) < 2:
            continue
        candidate_key = hash_key(f"agent|{norm_name}|{','.join(members)}")
        payload = {
            "norm_name": norm_name,
            "canonical_agent_id": canonical["agent_id"],
            "variants": [
                {"agent_id": entry["agent_id"], "name": entry.get("display_name")}
                for entry in entries
            ],
        }
        if not dry_run:
            cursor.execute(
                """
                INSERT INTO agent_alias_candidate (status, rule_version, candidate_key, canonical_agent_id, variants_json)
                VALUES ('OPEN', %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  canonical_agent_id=VALUES(canonical_agent_id),
                  variants_json=VALUES(variants_json),
                  updated_at=NOW()
                """,
                (rule_version, candidate_key, canonical["agent_id"], json_payload(payload)),
            )
        created += 1

    log(f"[authority] agent alias candidates processed: {created}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"[authority] failed: {exc}")
        sys.exit(1)
