import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.checkpoints import CheckpointStore
from lib.extract import (
    extract_contributors,
    extract_edition_labels,
    extract_identifiers,
    extract_issued_year,
    extract_language,
    extract_publisher,
    extract_record_id,
    extract_title,
    extract_updated_at,
    extract_volume,
    is_ascii,
)
from lib.parser import detect_format, iter_jsonld_graph, iter_ndjson
from lib.paths import checkpoints_dir, dataset_name, deadletter_dir, iter_input_files, raw_dir


OS_URL = os.environ.get("OS_URL", "http://localhost:9200")
BOOKS_ALIAS = os.environ.get("BOOKS_ALIAS", "books_doc_write")
AC_ALIAS = os.environ.get("AC_ALIAS", "ac_suggest_write")
AUTHORS_ALIAS = os.environ.get("AUTHORS_ALIAS", "authors_doc_write")
ENABLE_ENTITY_INDICES = os.environ.get("ENABLE_ENTITY_INDICES", "1") == "1"

BULK_SIZE = int(os.environ.get("OS_BULK_SIZE", "10000"))
PROGRESS_EVERY = int(os.environ.get("OS_PROGRESS_EVERY", "5000"))
RESET = os.environ.get("RESET", "0") == "1"
TIMEOUT_SEC = int(os.environ.get("OS_TIMEOUT_SEC", "30"))

BIBLIO_DATASETS = {
    "offline",
    "online",
    "book",
    "serial",
    "thesis",
    "audiovisual",
    "govermentpublication",
    "governmentpublication",
}
AUTHOR_DATASETS = {"person", "organization"}


def alias_exists(alias: str) -> bool:
    request = urllib.request.Request(f"{OS_URL}/_alias/{alias}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def post_bulk(index_alias: str, actions: List[Dict[str, Any]], deadletter_path: Path) -> None:
    if not actions:
        return
    payload_lines = []
    for action in actions:
        payload_lines.append(json.dumps(action["meta"], ensure_ascii=False))
        payload_lines.append(json.dumps(action["doc"], ensure_ascii=False))
    payload = "\n".join(payload_lines) + "\n"

    req = urllib.request.Request(
        f"{OS_URL}/{index_alias}/_bulk",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise RuntimeError(f"OpenSearch bulk failed ({exc.code}): {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenSearch bulk failed: {exc}") from exc

    result = json.loads(body)
    if result.get("errors"):
        with deadletter_path.open("a", encoding="utf-8") as handle:
            for item in result.get("items", []):
                action = item.get("index") or item.get("create") or item.get("update")
                if not action:
                    continue
                if action.get("error"):
                    handle.write(json.dumps(action, ensure_ascii=False) + "\n")


def format_updated_at(updated_at_raw: Optional[str], updated_at: Optional[Any]) -> Optional[str]:
    if updated_at_raw:
        return updated_at_raw
    if updated_at is None:
        return None
    if hasattr(updated_at, "isoformat"):
        return updated_at.isoformat()
    return None


def build_book_doc(record_id: str, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title_ko, title_en = extract_title(node)
    if not title_ko and not title_en:
        return None

    updated_at, updated_raw = extract_updated_at(node)
    contributors = extract_contributors(node)
    authors = []
    for idx, entry in enumerate(contributors):
        author: Dict[str, Any] = {"ord": idx, "role": entry.get("role", "AUTHOR")}
        if entry.get("agent_id"):
            author["agent_id"] = entry["agent_id"]
        if entry.get("name_ko"):
            author["name_ko"] = entry["name_ko"]
        if entry.get("name_en"):
            author["name_en"] = entry["name_en"]
        authors.append(author)

    doc: Dict[str, Any] = {
        "doc_id": record_id,
        "publisher_name": extract_publisher(node),
        "identifiers": extract_identifiers(node) or None,
        "language_code": extract_language(node),
        "issued_year": extract_issued_year(node),
        "volume": extract_volume(node),
        "edition_labels": extract_edition_labels(node) or None,
        "updated_at": format_updated_at(updated_raw, updated_at),
    }

    if title_ko:
        doc["title_ko"] = title_ko
    if title_en:
        doc["title_en"] = title_en
    if authors:
        doc["authors"] = authors

    return {k: v for k, v in doc.items() if v is not None}


def build_suggest_docs(record_id: str, book_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    seen = set()

    def add_suggestion(text: str, kind: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        key = f"{kind}:{cleaned.lower()}"
        if key in seen:
            return
        seen.add(key)
        lang = "en" if is_ascii(cleaned) else "ko"
        suggest_id = hashlib.sha1(f"{record_id}:{kind}:{cleaned}".encode("utf-8")).hexdigest()
        suggestions.append(
            {
                "suggest_id": suggest_id,
                "type": kind,
                "lang": lang,
                "text": cleaned,
                "text_kw": cleaned,
                "target_id": record_id,
                "target_doc_id": record_id,
                "weight": 1,
                "updated_at": book_doc.get("updated_at"),
            }
        )

    if book_doc.get("title_ko"):
        add_suggestion(book_doc["title_ko"], "title")
    if book_doc.get("title_en"):
        add_suggestion(book_doc["title_en"], "title")

    for author in book_doc.get("authors", []):
        name = author.get("name_ko") or author.get("name_en")
        if name:
            add_suggestion(name, "author")

    return suggestions


def build_author_doc(record_id: str, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name_ko, name_en = extract_title(node)
    if not name_ko and not name_en:
        return None
    updated_at, updated_raw = extract_updated_at(node)
    doc: Dict[str, Any] = {
        "author_id": record_id,
        "name_ko": name_ko,
        "name_en": name_en,
        "updated_at": format_updated_at(updated_raw, updated_at),
    }
    return {k: v for k, v in doc.items() if v is not None}


def process_file(
    checkpoint_store: CheckpointStore,
    file_path: Path,
    books_deadletter: Path,
    suggest_deadletter: Path,
    authors_deadletter: Path,
) -> None:
    dataset = dataset_name(file_path)
    dataset_lower = dataset.lower()
    format_type = detect_format(file_path)
    checkpoint = checkpoint_store.load(file_path)
    start_offset = int(checkpoint.get("offset", 0))
    start_index = int(checkpoint.get("graph_index", 0))

    book_actions: List[Dict[str, Any]] = []
    suggest_actions: List[Dict[str, Any]] = []
    author_actions: List[Dict[str, Any]] = []
    processed = 0
    last_checkpoint = time.time()
    last_offset = start_offset
    last_line = checkpoint.get("line", 0)
    last_index = start_index

    def flush(latest_checkpoint: Dict[str, Any]) -> None:
        nonlocal book_actions, suggest_actions, author_actions, last_checkpoint
        post_bulk(BOOKS_ALIAS, book_actions, books_deadletter)
        post_bulk(AC_ALIAS, suggest_actions, suggest_deadletter)
        if ENABLE_ENTITY_INDICES and alias_exists(AUTHORS_ALIAS):
            post_bulk(AUTHORS_ALIAS, author_actions, authors_deadletter)
        book_actions = []
        suggest_actions = []
        author_actions = []
        if latest_checkpoint:
            checkpoint_store.save(file_path, latest_checkpoint)
        last_checkpoint = time.time()

    if dataset_lower in BIBLIO_DATASETS or (ENABLE_ENTITY_INDICES and dataset_lower in AUTHOR_DATASETS):
        if format_type == "ndjson":
            for line_number, offset, node in iter_ndjson(file_path, start_offset):
                record_id = extract_record_id(node)
                if not record_id:
                    continue
                last_offset = offset
                last_line = line_number
                if dataset_lower in BIBLIO_DATASETS:
                    book_doc = build_book_doc(record_id, node)
                    if book_doc:
                        book_actions.append(
                            {"meta": {"index": {"_id": record_id}}, "doc": book_doc}
                        )
                        for suggest_doc in build_suggest_docs(record_id, book_doc):
                            suggest_actions.append(
                                {"meta": {"index": {"_id": suggest_doc["suggest_id"]}}, "doc": suggest_doc}
                            )
                if ENABLE_ENTITY_INDICES and dataset_lower in AUTHOR_DATASETS:
                    author_doc = build_author_doc(record_id, node)
                    if author_doc:
                        author_actions.append(
                            {"meta": {"index": {"_id": record_id}}, "doc": author_doc}
                        )

                processed += 1
                if processed % BULK_SIZE == 0:
                    flush({"offset": last_offset, "line": last_line})
                if processed % PROGRESS_EVERY == 0:
                    elapsed = time.time() - last_checkpoint
                    rate = PROGRESS_EVERY / elapsed if elapsed > 0 else 0
                    print(f"[opensearch] {file_path.name}: {processed} records ({rate:.1f}/s)")
        else:
            for index, node in iter_jsonld_graph(file_path, start_index):
                record_id = extract_record_id(node)
                if not record_id:
                    continue
                last_index = index
                if dataset_lower in BIBLIO_DATASETS:
                    book_doc = build_book_doc(record_id, node)
                    if book_doc:
                        book_actions.append(
                            {"meta": {"index": {"_id": record_id}}, "doc": book_doc}
                        )
                        for suggest_doc in build_suggest_docs(record_id, book_doc):
                            suggest_actions.append(
                                {"meta": {"index": {"_id": suggest_doc["suggest_id"]}}, "doc": suggest_doc}
                            )
                if ENABLE_ENTITY_INDICES and dataset_lower in AUTHOR_DATASETS:
                    author_doc = build_author_doc(record_id, node)
                    if author_doc:
                        author_actions.append(
                            {"meta": {"index": {"_id": record_id}}, "doc": author_doc}
                        )

                processed += 1
                if processed % BULK_SIZE == 0:
                    flush({"graph_index": last_index})
                if processed % PROGRESS_EVERY == 0:
                    elapsed = time.time() - last_checkpoint
                    rate = PROGRESS_EVERY / elapsed if elapsed > 0 else 0
                    print(f"[opensearch] {file_path.name}: {processed} records ({rate:.1f}/s)")

    if book_actions or suggest_actions or author_actions:
        if format_type == "ndjson":
            flush({"offset": last_offset, "line": last_line})
        else:
            flush({"graph_index": last_index})


def main() -> int:
    if not raw_dir().exists():
        print(f"Raw data directory not found: {raw_dir()}")
        return 1

    if not alias_exists(BOOKS_ALIAS):
        print(f"Missing alias: {BOOKS_ALIAS}. Run scripts/os_bootstrap_indices_v1_1.sh first.")
        return 1
    if not alias_exists(AC_ALIAS):
        print(f"Missing alias: {AC_ALIAS}. Run scripts/os_bootstrap_indices_v1_1.sh first.")
        return 1
    global ENABLE_ENTITY_INDICES
    if ENABLE_ENTITY_INDICES and not alias_exists(AUTHORS_ALIAS):
        print(f"Optional alias missing: {AUTHORS_ALIAS}. Skipping author docs.")
        ENABLE_ENTITY_INDICES = False

    checkpoint_store = CheckpointStore(checkpoints_dir(), "opensearch")
    if RESET:
        checkpoint_store.clear()

    deadletter_dir().mkdir(parents=True, exist_ok=True)
    books_deadletter = deadletter_dir() / "books_doc_deadletter.ndjson"
    suggest_deadletter = deadletter_dir() / "ac_suggest_deadletter.ndjson"
    authors_deadletter = deadletter_dir() / "authors_doc_deadletter.ndjson"

    files = iter_input_files()
    if not files:
        print(f"No input files found in {raw_dir()}")
        return 1

    for file_path in files:
        print(f"[opensearch] ingesting {file_path.name}")
        process_file(checkpoint_store, file_path, books_deadletter, suggest_deadletter, authors_deadletter)

    print("[opensearch] ingestion complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
