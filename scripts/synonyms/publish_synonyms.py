#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

INDEX_WRITER_URL = os.environ.get("INDEX_WRITER_URL", "http://localhost:8090")


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


def fetch_synonym_set(conn, synonym_set_id: Optional[int], name: Optional[str], version: Optional[str]) -> Dict[str, Any]:
    with conn.cursor() as cursor:
        if synonym_set_id is not None:
            cursor.execute("SELECT * FROM synonym_set WHERE synonym_set_id=%s", (synonym_set_id,))
        else:
            cursor.execute(
                "SELECT * FROM synonym_set WHERE name=%s AND version=%s",
                (name, version),
            )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("synonym_set not found")
        return row


def parse_rules(rules_value: Any) -> Tuple[List[str], List[str]]:
    if rules_value is None:
        return [], []
    if isinstance(rules_value, (bytes, bytearray)):
        rules_value = rules_value.decode("utf-8")
    if isinstance(rules_value, str):
        rules_value = rules_value.strip()
        if not rules_value:
            return [], []
        rules_value = json.loads(rules_value)

    if isinstance(rules_value, list):
        return list(map(str, rules_value)), []

    if isinstance(rules_value, dict):
        ko = rules_value.get("ko") or []
        en = rules_value.get("en") or []
        if not isinstance(ko, list):
            ko = [str(ko)] if ko else []
        if not isinstance(en, list):
            en = [str(en)] if en else []
        return [str(item) for item in ko if str(item).strip()], [str(item) for item in en if str(item).strip()]

    return [], []


def apply_synonyms(mapping: Dict[str, Any], synonyms_ko: List[str], synonyms_en: List[str]) -> Dict[str, Any]:
    analysis = mapping.setdefault("settings", {}).setdefault("analysis", {})
    filters = analysis.setdefault("filter", {})
    analyzers = analysis.setdefault("analyzer", {})

    def ensure_filter(analyzer_name: str, filter_name: str) -> None:
        analyzer = analyzers.get(analyzer_name)
        if not analyzer:
            return
        current = analyzer.get("filter") or []
        if filter_name not in current:
            analyzer["filter"] = [*current, filter_name]

    if synonyms_ko:
        filters["synonym_ko"] = {
            "type": "synonym",
            "synonyms": synonyms_ko,
        }
        ensure_filter("ko_search", "synonym_ko")

    if synonyms_en:
        filters["synonym_en"] = {
            "type": "synonym",
            "synonyms": synonyms_en,
        }
        ensure_filter("en_search", "synonym_en")

    return mapping


def write_mapping(mapping_path: Path, mapping: Dict[str, Any]) -> None:
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")


def activate_synonym_set(conn, name: str, synonym_set_id: int) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE synonym_set SET status='ARCHIVED' WHERE name=%s AND synonym_set_id!=%s",
            (name, synonym_set_id),
        )
        cursor.execute(
            "UPDATE synonym_set SET status='ACTIVE' WHERE synonym_set_id=%s",
            (synonym_set_id,),
        )
    conn.commit()


def post_index_writer(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{INDEX_WRITER_URL}{path}"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Index writer error ({exc.code}): {exc.read().decode('utf-8')}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Index writer request failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish synonym set and trigger reindex")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--synonym-set-id", type=int, help="synonym_set_id")
    group.add_argument("--name", type=str, help="synonym set name")
    parser.add_argument("--version", type=str, help="synonym set version (required with --name)")
    parser.add_argument(
        "--mapping-template",
        type=str,
        default=str(ROOT_DIR / "infra/opensearch/books_doc_v2.mapping.json"),
    )
    parser.add_argument(
        "--mapping-output-dir",
        type=str,
        default=str(ROOT_DIR / "infra/opensearch/generated"),
    )
    parser.add_argument("--index-prefix", type=str, default="books_doc_v2_syn")
    parser.add_argument("--no-reindex", action="store_true")
    parser.add_argument("--activate-only", action="store_true")
    parser.add_argument("--material-kinds", type=str, default="")

    args = parser.parse_args()

    if args.name and not args.version:
        raise SystemExit("--version is required when using --name")

    conn = connect_mysql()
    try:
        row = fetch_synonym_set(conn, args.synonym_set_id, args.name, args.version)
    finally:
        conn.close()

    synonym_set_id = row["synonym_set_id"]
    name = row["name"]
    version = row["version"]
    rules_json = row.get("rules_json")

    synonyms_ko, synonyms_en = parse_rules(rules_json)
    if not synonyms_ko and not synonyms_en:
        log("[synonym] No synonyms found in rules_json")

    mapping_template = Path(args.mapping_template)
    if not mapping_template.is_absolute():
        mapping_template = ROOT_DIR / mapping_template
    mapping = json.loads(mapping_template.read_text(encoding="utf-8"))
    mapping = apply_synonyms(mapping, synonyms_ko, synonyms_en)

    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)
    output_dir = Path(args.mapping_output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT_DIR / output_dir
    mapping_path = output_dir / f"books_doc_v2_{safe_name}_{version}.mapping.json"

    if not args.activate_only:
        write_mapping(mapping_path, mapping)
        log(f"[synonym] Wrote mapping: {mapping_path}")

    conn = connect_mysql()
    try:
        activate_synonym_set(conn, name, synonym_set_id)
    finally:
        conn.close()

    log(f"[synonym] Activated {name} v{version} (id={synonym_set_id})")

    if args.activate_only or args.no_reindex:
        log("[synonym] Skipping reindex")
        return 0

    payload = {
        "logical_name": "books_doc",
        "params": {
            "index_prefix": args.index_prefix,
            "mapping_path": str(mapping_path.relative_to(ROOT_DIR)),
        },
    }

    if args.material_kinds:
        payload["params"]["material_kinds"] = [
            kind.strip() for kind in args.material_kinds.split(",") if kind.strip()
        ]

    log("[synonym] Triggering reindex via index-writer")
    response = post_index_writer("/internal/index/reindex-jobs", payload)
    job = response.get("job") or {}
    log(f"[synonym] Reindex job created: {job.get('reindex_job_id')} status={job.get('status')}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"[synonym] failed: {exc}")
        sys.exit(1)
