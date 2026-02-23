#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pymysql
except ImportError as exc:
    raise SystemExit(
        "PyMySQL is required. Install with: python3 -m pip install -r scripts/ingest/requirements.txt"
    ) from exc


ROOT_DIR = Path(__file__).resolve().parents[1]

OS_URL = os.environ.get("OS_URL", "http://localhost:9200")
DOC_ALIAS = os.environ.get("BOOKS_DOC_ALIAS", "books_doc_write")
DOC_READ_ALIAS = os.environ.get("BOOKS_DOC_READ_ALIAS", "books_doc_read")
INDEX_PREFIX = os.environ.get("BOOKS_DOC_INDEX_PREFIX", "books_doc_v2_local")
MAPPING_FILE = Path(
    os.environ.get("BOOKS_DOC_MAPPING", ROOT_DIR / "infra/opensearch/books_doc_v2.mapping.json")
)
DELETE_EXISTING = os.environ.get("DELETE_EXISTING", "1") == "1"

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")

BATCH_SIZE = int(os.environ.get("MYSQL_BATCH_SIZE", "1000"))
BULK_SIZE = int(os.environ.get("OS_BULK_SIZE", "1000"))
RETRY_MAX = int(os.environ.get("OS_RETRY_MAX", "3"))
RETRY_BACKOFF_SEC = float(os.environ.get("OS_RETRY_BACKOFF_SEC", "1.0"))
TIMEOUT_SEC = int(os.environ.get("OS_TIMEOUT_SEC", "30"))
FAILURE_LOG = Path(
    os.environ.get(
        "REINDEX_FAILURE_LOG", str(ROOT_DIR / "data" / "reindex_books_failures.ndjson")
    )
)


def log(msg: str) -> None:
    print(msg, flush=True)


def is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def parse_json(value: Any) -> Optional[Any]:
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


def normalize_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        items = [str(item) for item in value if item is not None and str(item).strip()]
        return items or None
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return None


def coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int,)):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            return int(trimmed)
        except ValueError:
            return None
    return None


def format_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return None
    if isinstance(value, str):
        return value
    return None


def http_request(method: str, path: str, body: Optional[Any] = None, headers: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
    url = f"{OS_URL}{path}"
    data = None
    req_headers = headers.copy() if headers else {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenSearch request failed: {exc}") from exc


def http_request_raw(method: str, path: str, payload: bytes, headers: Dict[str, str]) -> Tuple[int, str]:
    url = f"{OS_URL}{path}"
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenSearch request failed: {exc}") from exc


def ensure_opensearch_ready() -> None:
    for attempt in range(1, 31):
        try:
            status, _ = http_request("GET", "/")
            if 200 <= status < 300:
                return
        except RuntimeError:
            pass
        time.sleep(1)
    raise RuntimeError(f"OpenSearch not reachable at {OS_URL}")


def list_indices(pattern: str) -> List[str]:
    status, body = http_request("GET", f"/_cat/indices/{pattern}?h=index")
    if status == 404:
        return []
    if status >= 300:
        raise RuntimeError(f"Failed to list indices ({status}): {body}")
    indices = [line.strip() for line in body.splitlines() if line.strip()]
    return indices


def delete_index(index_name: str) -> None:
    status, body = http_request("DELETE", f"/{index_name}")
    if status >= 300 and status != 404:
        raise RuntimeError(f"Failed to delete index {index_name} ({status}): {body}")


def create_index(index_name: str, mapping_path: Path) -> None:
    if not mapping_path.exists():
        raise RuntimeError(f"Mapping file not found: {mapping_path}")
    mapping = json.loads(mapping_path.read_text())
    status, body = http_request("PUT", f"/{index_name}", mapping)
    if status >= 300:
        raise RuntimeError(f"Failed to create index {index_name} ({status}): {body}")


def remove_alias(alias_name: str, index_pattern: str) -> None:
    payload = {"actions": [{"remove": {"index": index_pattern, "alias": alias_name}}]}
    status, body = http_request("POST", "/_aliases", payload)
    if status >= 300 and status != 404:
        raise RuntimeError(f"Failed to remove alias {alias_name} ({status}): {body}")


def add_alias(index_name: str, alias_name: str, is_write: bool = False) -> None:
    action = {"add": {"index": index_name, "alias": alias_name}}
    if is_write:
        action["add"]["is_write_index"] = True
    payload = {"actions": [action]}
    status, body = http_request("POST", "/_aliases", payload)
    if status >= 300:
        raise RuntimeError(f"Failed to add alias {alias_name} ({status}): {body}")


def connect_mysql(cursorclass) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=cursorclass,
    )


def fetch_map(cursor, query: str, ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not ids:
        return {}
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(query.format(placeholders=placeholders), ids)
    rows = cursor.fetchall()
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        material_id = row["material_id"]
        grouped.setdefault(material_id, []).append(row)
    return grouped


def fetch_single_map(cursor, query: str, ids: List[str], key: str) -> Dict[str, Dict[str, Any]]:
    if not ids:
        return {}
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(query.format(placeholders=placeholders), ids)
    rows = cursor.fetchall()
    return {row[key]: row for row in rows}


def choose_title_fields(title: Optional[str], extras: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    title_ko = None
    title_en = None
    if extras:
        extra_title_en = extras.get("title_en") or extras.get("titleEn")
        if isinstance(extra_title_en, str) and extra_title_en.strip():
            title_en = extra_title_en.strip()
    if title:
        cleaned = title.strip()
        if cleaned:
            if is_ascii(cleaned):
                title_en = title_en or cleaned
            else:
                title_ko = cleaned
    return title_ko, title_en


def choose_isbn13(rows: List[Dict[str, Any]], extras: Optional[Dict[str, Any]]) -> Optional[str]:
    candidates: List[str] = []
    for row in rows:
        scheme = (row.get("scheme") or "").upper()
        value = row.get("value")
        if not value:
            continue
        if "ISBN" in scheme:
            candidates.append(str(value))
    if extras:
        ids = extras.get("identifiers")
        if isinstance(ids, dict):
            extra = ids.get("isbn13")
            if extra:
                candidates.append(str(extra))
    if not candidates:
        return None
    def score(v: str) -> Tuple[int, int]:
        digits = "".join(ch for ch in v if ch.isdigit())
        return (0 if len(digits) == 13 else 1, len(digits))
    candidates.sort(key=score)
    return candidates[0]


def build_authors(rows: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    if not rows:
        return None
    authors: List[Dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: (r.get("role") or "", r.get("ord") or 0)):
        name = row.get("preferred_name") or row.get("agent_name_raw")
        entry: Dict[str, Any] = {
            "role": row.get("role") or "AUTHOR",
            "ord": int(row.get("ord") or 0),
        }
        if row.get("agent_id"):
            entry["agent_id"] = row["agent_id"]
        if name:
            cleaned = str(name).strip()
            if cleaned:
                if is_ascii(cleaned):
                    entry["name_en"] = cleaned
                else:
                    entry["name_ko"] = cleaned
        authors.append(entry)
    return authors or None


def build_concepts(rows: List[Dict[str, Any]]) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    if not rows:
        return None, None
    concept_ids: List[str] = []
    category_paths: List[str] = []
    for row in rows:
        concept_id = row.get("concept_id")
        if concept_id:
            concept_ids.append(str(concept_id))
        label = row.get("pref_label")
        if label:
            category_paths.append(str(label))
    if concept_ids:
        concept_ids = sorted(set(concept_ids))
    else:
        concept_ids = None
    if category_paths:
        category_paths = sorted(set(category_paths))
    else:
        category_paths = None
    return concept_ids, category_paths


def build_document(
    material: Dict[str, Any],
    overrides: Dict[str, Dict[str, Any]],
    merges: Dict[str, Dict[str, Any]],
    identifiers: Dict[str, List[Dict[str, Any]]],
    agents: Dict[str, List[Dict[str, Any]]],
    concepts: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    material_id = material["material_id"]
    override = overrides.get(material_id, {})
    extras = parse_json(material.get("extras_json")) or {}

    title = override.get("title") or material.get("title")
    title_ko, title_en = choose_title_fields(title, extras)

    language_code = override.get("language_code") or material.get("language_code")
    publisher_name = override.get("publisher_name") or material.get("publisher_name")
    issued_year = override.get("issued_year") or material.get("issued_year")

    edition_labels = normalize_list(extras.get("edition_labels") or extras.get("editionLabels"))
    volume = coerce_int(extras.get("volume"))

    isbn13 = choose_isbn13(identifiers.get(material_id, []), extras)
    authors = build_authors(agents.get(material_id, []))
    concept_ids, category_paths = build_concepts(concepts.get(material_id, []))

    is_hidden = bool(override.get("hidden"))
    merge = merges.get(material_id)
    redirect_to = merge.get("to_material_id") if merge else None

    doc: Dict[str, Any] = {
        "doc_id": material_id,
        "is_hidden": is_hidden,
    }

    if title_ko:
        doc["title_ko"] = title_ko
    if title_en:
        doc["title_en"] = title_en
    if authors:
        doc["authors"] = authors
    if publisher_name:
        doc["publisher_name"] = publisher_name
    if isbn13:
        doc["identifiers"] = {"isbn13": isbn13}
    if language_code:
        doc["language_code"] = language_code
    if issued_year is not None:
        doc["issued_year"] = int(issued_year)
    if volume is not None:
        doc["volume"] = volume
    if edition_labels:
        doc["edition_labels"] = edition_labels
    if category_paths:
        doc["category_paths"] = category_paths
    if concept_ids:
        doc["concept_ids"] = concept_ids
    if redirect_to:
        doc["redirect_to"] = redirect_to
    updated_at = format_datetime(material.get("updated_at"))
    if updated_at:
        doc["updated_at"] = updated_at

    return doc


def send_bulk(actions: List[str], retry_max: int) -> Tuple[int, int]:
    if not actions:
        return 0, 0
    payload = "\n".join(actions) + "\n"
    attempt = 0
    while True:
        attempt += 1
        status, body = http_request_raw(
            "POST",
            f"/{DOC_ALIAS}/_bulk",
            payload.encode("utf-8"),
            {"Content-Type": "application/x-ndjson"},
        )
        if status >= 300:
            if attempt <= retry_max:
                sleep_for = RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
                log(f"[bulk] HTTP {status}, retrying in {sleep_for:.1f}s (attempt {attempt}/{retry_max})")
                time.sleep(sleep_for)
                continue
            raise RuntimeError(f"Bulk request failed (HTTP {status}): {body}")

        result = json.loads(body)
        if not result.get("errors"):
            return len(actions) // 2, 0

        failures = 0
        with FAILURE_LOG.open("a", encoding="utf-8") as handle:
            for item in result.get("items", []):
                action = item.get("index") or item.get("create") or item.get("update")
                if not action:
                    continue
                if action.get("error"):
                    failures += 1
                    handle.write(json.dumps(action, ensure_ascii=False) + "\n")
        return len(actions) // 2, failures


def main() -> int:
    log("[reindex] starting books reindex")
    ensure_opensearch_ready()
    FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    index_name = f"{INDEX_PREFIX}_{timestamp}"

    if DELETE_EXISTING:
        existing = list_indices("books_doc_*")
        if existing:
            log(f"[reindex] deleting {len(existing)} existing books_doc indices")
            for idx in existing:
                delete_index(idx)

    remove_alias(DOC_ALIAS, "books_doc_*")
    remove_alias(DOC_READ_ALIAS, "books_doc_*")

    log(f"[reindex] creating index {index_name}")
    create_index(index_name, MAPPING_FILE)
    add_alias(index_name, DOC_READ_ALIAS)
    add_alias(index_name, DOC_ALIAS, is_write=True)

    conn_stream = connect_mysql(pymysql.cursors.SSDictCursor)
    conn_lookup = connect_mysql(pymysql.cursors.DictCursor)

    table_info = load_table_info(conn_lookup, [
        "material",
        "material_override",
        "material_merge",
        "material_identifier",
        "material_agent",
        "agent",
        "material_concept",
        "concept",
    ])
    material_cols = table_info.get("material", set())
    if "material_id" not in material_cols:
        raise RuntimeError("material.material_id is required but missing")

    material_count = fetch_material_count()
    log(f"[reindex] material rows: {material_count}")

    total_indexed = 0
    total_failed = 0
    batch: List[Dict[str, Any]] = []
    actions: List[str] = []

    material_select_cols = build_select_parts(
        "m",
        material_cols,
        required=["material_id"],
        optional=[
            "title",
            "language_code",
            "publisher_name",
            "issued_year",
            "extras_json",
            "updated_at",
        ],
    )
    query = f"SELECT {', '.join(material_select_cols)} FROM material m ORDER BY material_id"

    with conn_stream.cursor() as cursor_stream:
        cursor_stream.execute(query)
        for row in cursor_stream:
            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                total_indexed, total_failed = process_batch(
                    batch,
                    conn_lookup,
                    actions,
                    total_indexed,
                    total_failed,
                    table_info,
                )
                batch = []
                actions = []
        if batch:
            total_indexed, total_failed = process_batch(
                batch,
                conn_lookup,
                actions,
                total_indexed,
                total_failed,
                table_info,
            )

    conn_stream.close()
    conn_lookup.close()

    log("[reindex] verifying index")
    http_request("POST", f"/{DOC_READ_ALIAS}/_refresh")
    count_status, count_body = http_request("GET", f"/{DOC_READ_ALIAS}/_count")
    if count_status >= 300:
        raise RuntimeError(f"Count failed ({count_status}): {count_body}")
    count_value = json.loads(count_body).get("count", 0)
    log(f"[reindex] indexed docs: {total_indexed}, failures: {total_failed}, os_count: {count_value}")

    sample_titles = fetch_sample_titles()
    for title in sample_titles:
        hits = run_sample_query(title)
        log(f"[verify] query='{title}' hits={hits}")

    if count_value == 0:
        log("[reindex] verification failed: count is 0")
        return 1
    log("[reindex] complete")
    return 0


def process_batch(
    batch: List[Dict[str, Any]],
    conn_lookup: pymysql.connections.Connection,
    actions: List[str],
    total_indexed: int,
    total_failed: int,
    table_info: Dict[str, set],
) -> Tuple[int, int]:
    material_ids = [row["material_id"] for row in batch]
    with conn_lookup.cursor() as cursor:
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
                material_ids,
                "material_id",
            )

        merges = {}
        merge_cols = table_info.get("material_merge", set())
        if "from_material_id" in merge_cols and "to_material_id" in merge_cols:
            merges = fetch_single_map(
                cursor,
                "SELECT from_material_id AS material_id, to_material_id FROM material_merge "
                "WHERE from_material_id IN ({placeholders})",
                material_ids,
                "material_id",
            )

        identifiers = {}
        ident_cols = table_info.get("material_identifier", set())
        if "material_id" in ident_cols and "scheme" in ident_cols and "value" in ident_cols:
            identifiers = fetch_map(
                cursor,
                "SELECT material_id, scheme, value FROM material_identifier WHERE material_id IN ({placeholders})",
                material_ids,
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
                else:
                    agent_select.append("NULL AS preferred_name")
            else:
                agent_select.append("NULL AS preferred_name")
            agents = fetch_map(
                cursor,
                f"SELECT {', '.join(agent_select)} FROM material_agent ma {join_clause} "
                "WHERE ma.material_id IN ({placeholders})",
                material_ids,
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
                else:
                    concept_select.append("NULL AS pref_label")
                if "scheme" in concept_cols:
                    concept_select.append("c.scheme")
                else:
                    concept_select.append("NULL AS scheme")
            else:
                concept_select.append("NULL AS pref_label")
                concept_select.append("NULL AS scheme")
            concepts = fetch_map(
                cursor,
                f"SELECT {', '.join(concept_select)} FROM material_concept mc {join_clause} "
                "WHERE mc.material_id IN ({placeholders})",
                material_ids,
            )

    for material in batch:
        doc = build_document(material, overrides, merges, identifiers, agents, concepts)
        actions.append(json.dumps({"index": {"_id": doc["doc_id"]}}, ensure_ascii=False))
        actions.append(json.dumps(doc, ensure_ascii=False))
        if len(actions) // 2 >= BULK_SIZE:
            indexed, failed = send_bulk(actions, RETRY_MAX)
            total_indexed += indexed
            total_failed += failed
            log(f"[bulk] indexed {indexed} (failed {failed})")
            actions.clear()

    if actions:
        indexed, failed = send_bulk(actions, RETRY_MAX)
        total_indexed += indexed
        total_failed += failed
        log(f"[bulk] indexed {indexed} (failed {failed})")
        actions.clear()

    return total_indexed, total_failed


def fetch_sample_titles() -> List[str]:
    conn = connect_mysql(pymysql.cursors.DictCursor)
    titles: List[str] = []
    with conn.cursor() as cursor:
        cursor.execute("SELECT title FROM material WHERE title IS NOT NULL LIMIT 3")
        for row in cursor.fetchall():
            title = row.get("title")
            if title:
                titles.append(title)
    conn.close()
    if not titles:
        titles = ["해리", "history", "science"]
    return titles


def fetch_material_count() -> int:
    conn = connect_mysql(pymysql.cursors.DictCursor)
    count = 0
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS cnt FROM material")
        row = cursor.fetchone()
        if row and row.get("cnt") is not None:
            count = int(row["cnt"])
    conn.close()
    return count


def table_exists(conn: pymysql.connections.Connection, table_name: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (MYSQL_DATABASE, table_name),
        )
        row = cursor.fetchone()
        return bool(row and row.get("cnt"))


def get_table_columns(conn: pymysql.connections.Connection, table_name: str) -> set:
    if not table_exists(conn, table_name):
        return set()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (MYSQL_DATABASE, table_name),
        )
        return {row["COLUMN_NAME"] for row in cursor.fetchall()}


def load_table_info(conn: pymysql.connections.Connection, tables: List[str]) -> Dict[str, set]:
    info: Dict[str, set] = {}
    for table in tables:
        info[table] = get_table_columns(conn, table)
    return info


def build_select_parts(table_alias: str, columns: set, required: List[str], optional: List[str]) -> List[str]:
    parts: List[str] = []
    for col in required:
        if col not in columns:
            raise RuntimeError(f"Missing required column {table_alias}.{col}")
        parts.append(f"{table_alias}.{col}")
    for col in optional:
        if col in columns:
            parts.append(f"{table_alias}.{col}")
        else:
            parts.append(f"NULL AS {col}")
    return parts


def run_sample_query(query_text: str) -> int:
    body = {
        "size": 1,
        "query": {
            "multi_match": {
                "query": query_text,
                "fields": ["title_ko", "title_en", "authors.name_ko", "authors.name_en"],
            }
        },
    }
    status, response = http_request("POST", f"/{DOC_READ_ALIAS}/_search", body)
    if status >= 300:
        return 0
    data = json.loads(response)
    return data.get("hits", {}).get("total", {}).get("value", 0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"[reindex] failed: {exc}")
        sys.exit(1)
