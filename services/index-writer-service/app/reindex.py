import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pymysql

from app.config import Settings
from app.db import Database, parse_json, utc_now
from app.opensearch import OpenSearchClient, TRANSIENT_STATUSES


class ReindexException(Exception):
    def __init__(self, message: str, retryable: bool = False, stage: Optional[str] = None, detail: Any = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.stage = stage
        self.detail = detail


def log(msg: str) -> None:
    print(msg, flush=True)


def is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


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
    if isinstance(value, int):
        return value
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
    candidates = collect_isbn_candidates(rows, extras)
    if not candidates:
        return None

    isbn13_candidates = [value for value in candidates if len(value) == 13 and value.isdigit()]
    if isbn13_candidates:
        return isbn13_candidates[0]

    isbn10_candidates = [value for value in candidates if len(value) == 10]
    if isbn10_candidates:
        return isbn10_to_isbn13(isbn10_candidates[0])
    return None


def choose_isbn10(rows: List[Dict[str, Any]], extras: Optional[Dict[str, Any]]) -> Optional[str]:
    candidates = collect_isbn_candidates(rows, extras)
    if not candidates:
        return None
    for candidate in candidates:
        if len(candidate) == 10:
            return candidate
    return None


def choose_series_name(extras: Optional[Dict[str, Any]]) -> Optional[str]:
    if not extras:
        return None
    candidates = [
        extras.get("series_name"),
        extras.get("seriesName"),
        extras.get("series"),
        extras.get("collection"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    if isinstance(extras.get("series"), list):
        for entry in extras.get("series"):
            if isinstance(entry, str) and entry.strip():
                return entry.strip()
            if isinstance(entry, dict):
                for key in ("name", "label", "value"):
                    nested = entry.get(key)
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
    return None


def collect_isbn_candidates(rows: List[Dict[str, Any]], extras: Optional[Dict[str, Any]]) -> List[str]:
    candidates: List[str] = []
    for row in rows:
        scheme = (row.get("scheme") or "").upper()
        value = row.get("value")
        if not value:
            continue
        if "ISBN" in scheme:
            normalized = normalize_isbn(str(value))
            if normalized:
                candidates.append(normalized)
    if extras:
        ids = extras.get("identifiers")
        if isinstance(ids, dict):
            for key in ("isbn13", "isbn10"):
                extra = ids.get(key)
                if extra:
                    normalized = normalize_isbn(str(extra))
                    if normalized:
                        candidates.append(normalized)
    if not candidates:
        return []
    deduped: List[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    deduped.sort(key=lambda value: (0 if len(value) == 13 else 1, len(value)))
    return deduped


def normalize_isbn(value: str) -> Optional[str]:
    cleaned = "".join(ch for ch in value if ch.isdigit() or ch.upper() == "X")
    if len(cleaned) in (10, 13):
        return cleaned.upper()
    return None


def isbn10_to_isbn13(isbn10: str) -> Optional[str]:
    if len(isbn10) != 10:
        return None
    core = f"978{isbn10[:-1]}"
    if not core.isdigit():
        return None
    total = 0
    for idx, ch in enumerate(core):
        factor = 1 if idx % 2 == 0 else 3
        total += int(ch) * factor
    check = (10 - (total % 10)) % 10
    return f"{core}{check}"


def build_authors(rows: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    if not rows:
        return None
    authors: List[Dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: (r.get("role") or "", r.get("ord") or 0)):
        name = (
            row.get("preferred_name")
            or row.get("pref_label")
            or row.get("label")
            or row.get("name")
            or row.get("agent_name_raw")
        )
        entry: Dict[str, Any] = {
            "role": row.get("role") or "AUTHOR",
            "ord": int(row.get("ord") or 0),
        }
        if row.get("agent_id"):
            entry["agent_id"] = row.get("agent_id")
        if name:
            cleaned = str(name).strip()
            if cleaned:
                if is_ascii(cleaned):
                    entry["name_en"] = cleaned
                else:
                    entry["name_ko"] = cleaned
        authors.append(entry)
    return authors or None


def flatten_author_names(authors: Optional[List[Dict[str, Any]]], key: str) -> Optional[List[str]]:
    if not authors:
        return None
    names: List[str] = []
    for author in authors:
        value = author.get(key)
        if isinstance(value, str) and value.strip() and value not in names:
            names.append(value)
    return names or None


def build_concepts(rows: List[Dict[str, Any]]) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    if not rows:
        return None, None
    concept_ids: List[str] = []
    category_paths: List[str] = []
    for row in rows:
        concept_id = row.get("concept_id")
        if concept_id:
            concept_ids.append(str(concept_id))
        label = row.get("pref_label") or row.get("label")
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


def resolve_kdc_fields(
    rows: List[Dict[str, Any]],
    fallback_node_id: Optional[int],
) -> Tuple[Optional[str], Optional[List[str]], Optional[int]]:
    if not rows:
        return None, None, fallback_node_id

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            0 if int(row.get("is_primary") or 0) == 1 else 1,
            int(row.get("ord") or 0),
        ),
    )
    primary = sorted_rows[0]
    kdc_code = str(primary.get("kdc_code_raw") or "").strip() or None
    kdc_code_3 = str(primary.get("kdc_code_3") or "").strip() or None
    resolved_node_id = coerce_int(primary.get("kdc_node_id")) or fallback_node_id

    path_codes: List[str] = []
    if kdc_code_3:
        path_codes.append(kdc_code_3)
    if kdc_code and kdc_code not in path_codes:
        path_codes.append(kdc_code)
    if kdc_code and "." in kdc_code:
        prefix = kdc_code.split(".", 1)[0]
        if prefix and prefix not in path_codes:
            path_codes.insert(0, prefix)

    return kdc_code, (path_codes or None), resolved_node_id


def build_document(
    material: Dict[str, Any],
    overrides: Dict[str, Dict[str, Any]],
    merges: Dict[str, Dict[str, Any]],
    identifiers: Dict[str, List[Dict[str, Any]]],
    agents: Dict[str, List[Dict[str, Any]]],
    concepts: Dict[str, List[Dict[str, Any]]],
    kdc_rows: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    material_id = material["material_id"]
    override = overrides.get(material_id, {})
    extras = parse_json(material.get("extras_json")) or {}

    title = override.get("title") or material.get("title") or material.get("label")
    title_ko, title_en = choose_title_fields(title, extras)

    language_code = override.get("language_code") or material.get("language_code") or material.get("language")
    publisher_name = (
        override.get("publisher_name")
        or material.get("publisher_name")
        or material.get("publisher")
    )
    issued_year = override.get("issued_year") or material.get("issued_year")
    series_name = choose_series_name(extras)

    edition_labels = normalize_list(extras.get("edition_labels") or extras.get("editionLabels"))
    volume = coerce_int(extras.get("volume"))
    kdc_node_id = coerce_int(material.get("kdc_node_id"))
    kdc_code, kdc_path_codes, resolved_kdc_node_id = resolve_kdc_fields(kdc_rows.get(material_id, []), kdc_node_id)
    kdc_edition = extras.get("kdc_edition") or extras.get("kdcEdition")

    isbn13 = choose_isbn13(identifiers.get(material_id, []), extras)
    isbn10 = choose_isbn10(identifiers.get(material_id, []), extras)
    authors = build_authors(agents.get(material_id, []))
    author_names_ko = flatten_author_names(authors, "name_ko")
    author_names_en = flatten_author_names(authors, "name_en")
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
    if series_name:
        doc["series_name"] = series_name
    if authors:
        doc["authors"] = authors
    if author_names_ko:
        doc["author_names_ko"] = author_names_ko
    if author_names_en:
        doc["author_names_en"] = author_names_en
    if publisher_name:
        doc["publisher_name"] = publisher_name
    if isbn13 or isbn10:
        identifiers_doc: Dict[str, Any] = {}
        if isbn13:
            identifiers_doc["isbn13"] = isbn13
        if isbn10:
            identifiers_doc["isbn10"] = isbn10
        doc["identifiers"] = identifiers_doc
    if language_code:
        doc["language_code"] = language_code
    if issued_year is not None:
        doc["issued_year"] = int(issued_year)
    if volume is not None:
        doc["volume"] = volume
    if edition_labels:
        doc["edition_labels"] = edition_labels
    if resolved_kdc_node_id is not None:
        doc["kdc_node_id"] = resolved_kdc_node_id
    if kdc_code:
        doc["kdc_code"] = kdc_code
    if isinstance(kdc_edition, str) and kdc_edition.strip():
        doc["kdc_edition"] = kdc_edition.strip()
    if kdc_path_codes:
        doc["kdc_path_codes"] = kdc_path_codes
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


def connect_mysql(settings: Settings, cursorclass) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
        cursorclass=cursorclass,
    )


def table_exists(conn: pymysql.connections.Connection, table_name: str, database: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (database, table_name),
        )
        row = cursor.fetchone()
        return bool(row and row.get("cnt"))


def get_table_columns(conn: pymysql.connections.Connection, table_name: str, database: str) -> set:
    if not table_exists(conn, table_name, database):
        return set()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (database, table_name),
        )
        return {row["COLUMN_NAME"] for row in cursor.fetchall()}


def load_table_info(conn: pymysql.connections.Connection, tables: List[str], database: str) -> Dict[str, set]:
    info: Dict[str, set] = {}
    for table in tables:
        info[table] = get_table_columns(conn, table, database)
    return info


def build_select_parts(table_alias: str, columns: set, required: List[str], optional: List[str]) -> List[str]:
    parts: List[str] = []
    for col in required:
        if col not in columns:
            raise ReindexException(f"Missing required column {table_alias}.{col}")
        parts.append(f"{table_alias}.{col}")
    for col in optional:
        if col in columns:
            parts.append(f"{table_alias}.{col}")
        else:
            parts.append(f"NULL AS {col}")
    return parts


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


def build_action_pairs(actions: List[str]) -> List[Tuple[str, str, str]]:
    pairs: List[Tuple[str, str, str]] = []
    for i in range(0, len(actions), 2):
        action_line = actions[i]
        doc_line = actions[i + 1] if i + 1 < len(actions) else "{}"
        action_meta = json.loads(action_line)
        action = next(iter(action_meta.values()))
        doc_id = action.get("_id") or ""
        pairs.append((doc_id, action_line, doc_line))
    return pairs


def flatten_pairs(pairs: List[Tuple[str, str, str]]) -> List[str]:
    actions: List[str] = []
    for _, action_line, doc_line in pairs:
        actions.append(action_line)
        actions.append(doc_line)
    return actions


def bulk_request(
    client: OpenSearchClient,
    index_alias: str,
    pairs: List[Tuple[str, str, str]],
    retry_max: int,
    retry_backoff_sec: float,
    job_id: int,
    db: Database,
    bulk_delay_sec: float,
) -> Tuple[int, int, int]:
    indexed = 0
    failed = 0
    retried = 0
    attempt = 0
    pending = pairs

    while pending and attempt <= retry_max:
        if bulk_delay_sec > 0:
            time.sleep(bulk_delay_sec)
        client.maybe_throttle()
        payload = "\n".join([line for _, action_line, doc_line in pending for line in (action_line, doc_line)]) + "\n"
        status, body = client.request_raw(
            "POST",
            f"/{index_alias}/_bulk",
            payload.encode("utf-8"),
            {"Content-Type": "application/x-ndjson"},
        )
        if status in TRANSIENT_STATUSES:
            sleep_for = retry_backoff_sec * (2 ** attempt)
            log(f"[bulk] HTTP {status}, retrying in {sleep_for:.1f}s (attempt {attempt + 1}/{retry_max})")
            time.sleep(sleep_for)
            attempt += 1
            continue
        if status >= 300:
            raise ReindexException(f"Bulk request failed (HTTP {status}): {body}", retryable=status in TRANSIENT_STATUSES)

        result = json.loads(body)
        items = result.get("items", [])
        retry_pairs: List[Tuple[str, str, str]] = []
        for idx, item in enumerate(items):
            action = item.get("index") or item.get("create") or item.get("update")
            if not action:
                continue
            doc_id, action_line, doc_line = pending[idx] if idx < len(pending) else ("", "", "")
            if action.get("error"):
                status_code = action.get("status")
                error_info = action.get("error")
                reason = error_info.get("reason") if isinstance(error_info, dict) else str(error_info)
                if status_code in TRANSIENT_STATUSES and attempt < retry_max:
                    retry_pairs.append((doc_id, action_line, doc_line))
                else:
                    failed += 1
                    db.insert_reindex_error(job_id, doc_id, status_code, reason, {"action": action})
            else:
                indexed += 1

        if not retry_pairs:
            return indexed, failed, retried

        retried += len(retry_pairs)
        pending = retry_pairs
        attempt += 1
        sleep_for = retry_backoff_sec * (2 ** max(attempt - 1, 0))
        time.sleep(sleep_for)

    if pending:
        for doc_id, action_line, doc_line in pending:
            failed += 1
            db.insert_reindex_error(
                job_id,
                doc_id,
                None,
                "retry_exhausted",
                {"action": json.loads(action_line), "doc": json.loads(doc_line)},
            )
    return indexed, failed, retried


def fetch_material_count(conn: pymysql.connections.Connection, material_kinds: Optional[List[str]]) -> int:
    with conn.cursor() as cursor:
        if material_kinds:
            placeholders = ",".join(["%s"] * len(material_kinds))
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM material WHERE material_kind IN ({placeholders})",
                material_kinds,
            )
        else:
            cursor.execute("SELECT COUNT(*) AS cnt FROM material")
        row = cursor.fetchone()
        return int(row["cnt"]) if row and row.get("cnt") is not None else 0


def fetch_sample_titles(conn: pymysql.connections.Connection) -> List[str]:
    titles: List[str] = []
    with conn.cursor() as cursor:
        cursor.execute("SELECT title FROM material WHERE title IS NOT NULL LIMIT 3")
        for row in cursor.fetchall():
            title = row.get("title")
            if title:
                titles.append(title)
    return titles or ["harry", "history", "science"]


def run_sample_query(client: OpenSearchClient, index_name: str, query_text: str) -> int:
    body = {
        "size": 1,
        "query": {
            "multi_match": {
                "query": query_text,
                "fields": ["title_ko", "title_en", "author_names_ko", "author_names_en"],
            }
        },
    }
    response = client.search(index_name, body)
    return response.get("hits", {}).get("total", {}).get("value", 0)


def schema_hash(mapping_path: Path) -> str:
    data = mapping_path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def generate_index_name(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}"


def to_error_payload(exc: Exception) -> Dict[str, Any]:
    if isinstance(exc, ReindexException):
        return {
            "message": str(exc),
            "retryable": exc.retryable,
            "stage": exc.stage,
            "detail": exc.detail,
        }
    return {"message": str(exc), "retryable": False}


def should_pause(db: Database, job_id: int) -> bool:
    status = db.get_job_status(job_id)
    return status == "PAUSED"


def bulk_load(
    job_id: int,
    settings: Settings,
    db: Database,
    client: OpenSearchClient,
    progress: Dict[str, Any],
    material_kinds: Optional[List[str]],
    index_name: str,
) -> Dict[str, Any]:
    total = progress.get("total")
    processed = progress.get("processed", 0)
    failed = progress.get("failed", 0)
    retries = progress.get("retries", 0)
    cursor = progress.get("cursor") or {}
    last_material_id = cursor.get("last_material_id")

    conn_stream = connect_mysql(settings, pymysql.cursors.SSDictCursor)
    conn_lookup = connect_mysql(settings, pymysql.cursors.DictCursor)

    table_info = load_table_info(
        conn_lookup,
        [
            "material",
            "material_override",
            "material_merge",
            "material_identifier",
            "material_agent",
            "agent",
            "material_concept",
            "concept",
            "material_kdc",
        ],
        settings.mysql_database,
    )

    material_cols = table_info.get("material", set())
    if "material_id" not in material_cols:
        raise ReindexException("material.material_id is required but missing", stage="BULK_LOAD")

    if material_kinds and "material_kind" not in material_cols:
        material_kinds = None

    if total is None:
        total = fetch_material_count(conn_lookup, material_kinds)

    material_select_cols = build_select_parts(
        "m",
        material_cols,
        required=["material_id"],
        optional=[
            "title",
            "label",
            "publisher_name",
            "publisher",
            "language_code",
            "language",
            "issued_year",
            "extras_json",
            "kdc_node_id",
            "updated_at",
        ],
    )

    where_clauses = []
    params: List[Any] = []
    if last_material_id:
        where_clauses.append("m.material_id > %s")
        params.append(last_material_id)
    if material_kinds:
        placeholders = ",".join(["%s"] * len(material_kinds))
        where_clauses.append(f"m.material_kind IN ({placeholders})")
        params.extend(material_kinds)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    query = f"SELECT {', '.join(material_select_cols)} FROM material m {where_sql} ORDER BY material_id"

    batch: List[Dict[str, Any]] = []
    actions: List[str] = []

    with conn_stream.cursor() as cursor_stream:
        cursor_stream.execute(query, params)
        for row in cursor_stream:
            batch.append(row)
            if len(batch) >= settings.batch_size:
                processed, failed, retries, last_material_id = process_batch(
                    batch,
                    conn_lookup,
                    actions,
                    processed,
                    failed,
                    retries,
                    job_id,
                    settings,
                    db,
                    client,
                    table_info,
                    index_name,
                )
                batch = []
                actions = []
                progress = {
                    "total": total,
                    "processed": processed,
                    "failed": failed,
                    "retries": retries,
                    "cursor": {"last_material_id": last_material_id},
                    "attempts": progress.get("attempts"),
                }
                db.update_job_progress(job_id, progress)
                if should_pause(db, job_id):
                    conn_stream.close()
                    conn_lookup.close()
                    db.update_job_status(job_id, "PAUSED", progress=progress, paused_at=utc_now())
                    return progress

        if batch:
            processed, failed, retries, last_material_id = process_batch(
                batch,
                conn_lookup,
                actions,
                processed,
                failed,
                retries,
                job_id,
                settings,
                db,
                client,
                table_info,
                index_name,
            )

    conn_stream.close()
    conn_lookup.close()

    progress = {
        "total": total,
        "processed": processed,
        "failed": failed,
        "retries": retries,
        "cursor": {"last_material_id": last_material_id},
        "attempts": progress.get("attempts"),
    }
    db.update_job_progress(job_id, progress)
    return progress


def process_batch(
    batch: List[Dict[str, Any]],
    conn_lookup: pymysql.connections.Connection,
    actions: List[str],
    processed: int,
    failed: int,
    retries: int,
    job_id: int,
    settings: Settings,
    db: Database,
    client: OpenSearchClient,
    table_info: Dict[str, set],
    index_name: str,
) -> Tuple[int, int, int, Optional[str]]:
    material_ids = [row["material_id"] for row in batch]
    last_material_id = material_ids[-1] if material_ids else None
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
                if "pref_label" in agent_cols:
                    agent_select.append("a.pref_label")
                if "label" in agent_cols:
                    agent_select.append("a.label")
                if "name" in agent_cols:
                    agent_select.append("a.name")
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
                if "label" in concept_cols:
                    concept_select.append("c.label")
            concepts = fetch_map(
                cursor,
                f"SELECT {', '.join(concept_select)} FROM material_concept mc {join_clause} "
                "WHERE mc.material_id IN ({placeholders})",
                material_ids,
            )

        kdc_rows = {}
        mk_cols = table_info.get("material_kdc", set())
        if "material_id" in mk_cols:
            kdc_select = build_select_parts(
                "mk",
                mk_cols,
                required=["material_id"],
                optional=["kdc_code_raw", "kdc_code_3", "kdc_node_id", "ord", "is_primary"],
            )
            kdc_rows = fetch_map(
                cursor,
                f"SELECT {', '.join(kdc_select)} FROM material_kdc mk WHERE mk.material_id IN ({{placeholders}})",
                material_ids,
            )

    for material in batch:
        doc = build_document(material, overrides, merges, identifiers, agents, concepts, kdc_rows)
        actions.append(json.dumps({"index": {"_id": doc["doc_id"]}}, ensure_ascii=False))
        actions.append(json.dumps(doc, ensure_ascii=False))
        if len(actions) // 2 >= settings.bulk_size:
            indexed, failed_batch, retried_batch = bulk_request(
                client,
                index_name,
                build_action_pairs(actions),
                settings.retry_max,
                settings.retry_backoff_sec,
                job_id,
                db,
                settings.bulk_delay_sec,
            )
            processed += indexed
            failed += failed_batch
            retries += retried_batch
            log(f"[bulk] job_id={job_id} indexed={indexed} failed={failed_batch} retried={retried_batch}")
            actions.clear()

    if actions:
        indexed, failed_batch, retried_batch = bulk_request(
            client,
            index_name,
            build_action_pairs(actions),
            settings.retry_max,
            settings.retry_backoff_sec,
            job_id,
            db,
            settings.bulk_delay_sec,
        )
        processed += indexed
        failed += failed_batch
        retries += retried_batch
        log(f"[bulk] job_id={job_id} indexed={indexed} failed={failed_batch} retried={retried_batch}")
        actions.clear()

    if failed > settings.max_failures:
        raise ReindexException(
            f"Exceeded max failures ({failed} > {settings.max_failures})",
            retryable=False,
            stage="BULK_LOAD",
        )

    return processed, failed, retries, last_material_id


class ReindexRunner:
    def __init__(self, settings: Settings, db: Database, client: OpenSearchClient) -> None:
        self.settings = settings
        self.db = db
        self.client = client

    def run_job(self, job: Dict[str, Any]) -> None:
        job_id = job["reindex_job_id"]
        params = job.get("params_json") or {}
        settings = self.settings.override(params)
        material_kinds = params.get("material_kinds") if isinstance(params, dict) else None

        progress = job.get("progress_json") or {}
        progress["attempts"] = int(progress.get("attempts", 0)) + 1
        self.db.update_job_progress(job_id, progress)

        try:
            self.db.update_job_status(job_id, "PREPARE", progress=progress)
            from_physical = job.get("from_physical") or self.db.get_alias_physical(settings.doc_read_alias)
            if from_physical is None:
                alias_indices = self.client.resolve_alias_indices(settings.doc_read_alias)
                from_physical = alias_indices[0] if alias_indices else None

            to_physical = job.get("to_physical")
            if not to_physical:
                to_physical = generate_index_name(settings.index_prefix)
                self.db.update_job_targets(job_id, to_physical, from_physical)

            if settings.delete_existing:
                existing = self.client.list_indices(f"{settings.index_prefix}*")
                for idx in existing:
                    if idx != to_physical:
                        self.client.delete_index(idx)

            if not self.client.index_exists(to_physical):
                mapping = json.loads(settings.mapping_path.read_text())
                self.client.create_index(to_physical, mapping)

            schema_digest = schema_hash(settings.mapping_path)
            self.db.insert_index_version(job["logical_name"], to_physical, schema_digest, "BUILDING")

            self.db.update_job_status(job_id, "BUILD_INDEX", progress=progress)
            if settings.refresh_interval_bulk:
                self.client.update_settings(to_physical, {"index": {"refresh_interval": settings.refresh_interval_bulk}})

            self.db.update_job_status(job_id, "BULK_LOAD", progress=progress)
            progress = bulk_load(job_id, settings, self.db, self.client, progress, material_kinds, to_physical)

            if settings.refresh_interval_post:
                self.client.update_settings(to_physical, {"index": {"refresh_interval": settings.refresh_interval_post}})

            if self.db.get_job_status(job_id) == "PAUSED":
                return

            self.db.update_job_status(job_id, "VERIFY", progress=progress)
            self.client.refresh(to_physical)
            count_value = self.client.count(to_physical)
            if count_value == 0:
                raise ReindexException("verification failed: count is 0", retryable=False, stage="VERIFY")

            self.db.update_index_version_status(job["logical_name"], to_physical, "READY")

            conn_titles = connect_mysql(settings, pymysql.cursors.DictCursor)
            try:
                sample_titles = fetch_sample_titles(conn_titles)
            finally:
                conn_titles.close()
            for title in sample_titles:
                hits = run_sample_query(self.client, to_physical, title)
                log(f"[verify] job_id={job_id} query='{title}' hits={hits}")

            self.db.update_job_status(job_id, "ALIAS_SWAP", progress=progress)
            existing_read = self.client.resolve_alias_indices(settings.doc_read_alias)
            existing_write = self.client.resolve_alias_indices(settings.doc_alias)
            actions: List[Dict[str, Any]] = []
            for idx in set(existing_read):
                actions.append({"remove": {"index": idx, "alias": settings.doc_read_alias}})
            for idx in set(existing_write):
                actions.append({"remove": {"index": idx, "alias": settings.doc_alias}})
            actions.append({"add": {"index": to_physical, "alias": settings.doc_read_alias}})
            actions.append({"add": {"index": to_physical, "alias": settings.doc_alias, "is_write_index": True}})
            self.client.update_aliases(actions)
            self.db.upsert_alias(settings.doc_read_alias, to_physical)
            self.db.upsert_alias(settings.doc_alias, to_physical)

            self.db.update_index_version_status(job["logical_name"], to_physical, "ACTIVE")
            if from_physical:
                self.db.update_index_version_status(job["logical_name"], from_physical, "DEPRECATED")

            self.db.update_job_status(job_id, "CLEANUP", progress=progress)
            if settings.delete_existing:
                existing = self.client.list_indices(f"{settings.index_prefix}*")
                for idx in existing:
                    if idx != to_physical:
                        self.client.delete_index(idx)

            self.db.update_job_status(job_id, "SUCCESS", progress=progress, finished_at=utc_now())
            log(f"[reindex] job_id={job_id} complete")

        except Exception as exc:
            error_payload = to_error_payload(exc)
            self.db.update_job_status(
                job_id,
                "FAILED",
                progress=progress,
                error=error_payload,
                error_message=str(exc),
                finished_at=utc_now(),
            )
            log(f"[reindex] job_id={job_id} failed: {exc}")
            raise
