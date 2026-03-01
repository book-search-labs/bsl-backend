import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymysql

from lib.checkpoints import CheckpointStore
from lib.extract import (
    extract_contributors,
    extract_concept_ids,
    extract_edition_labels,
    extract_identifiers,
    extract_issued_year,
    extract_language,
    extract_publisher,
    extract_record_id,
    extract_series_name,
    extract_strings,
    extract_title,
    extract_updated_at,
    extract_volume,
    is_ascii,
)
from lib.parser import detect_format, iter_jsonld_graph, iter_ndjson
from lib.paths import checkpoints_dir, dataset_name, deadletter_dir, iter_input_files, raw_dir
from vector_text import build_vector_text_v2, hash_vector_text, normalize_text
from embedding_cache import EmbeddingCache, RedisEmbeddingCache, SqliteEmbeddingCache


OS_URL = os.environ.get("OS_URL", "http://localhost:9200")
BOOKS_ALIAS = os.environ.get("BOOKS_ALIAS", "books_doc_write")
VEC_ALIAS = os.environ.get("VEC_ALIAS", "books_vec_write")
CHUNK_ALIAS = os.environ.get("CHUNK_ALIAS", "book_chunks_v1")
AC_ALIAS = os.environ.get("AC_ALIAS", "ac_candidates_write")
AUTHORS_ALIAS = os.environ.get("AUTHORS_ALIAS", "authors_doc_write")
ENABLE_ENTITY_INDICES = os.environ.get("ENABLE_ENTITY_INDICES", "1") == "1"
ENABLE_VECTOR_INDEX = os.environ.get("ENABLE_VECTOR_INDEX", "1") == "1"
ENABLE_CHUNK_INDEX = os.environ.get("ENABLE_CHUNK_INDEX", "0") == "1"

EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "mis").lower()
MIS_URL = os.environ.get("MIS_URL", "").rstrip("/")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "multilingual-e5-small")
EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "32"))
EMBED_TIMEOUT_SEC = float(os.environ.get("EMBED_TIMEOUT_SEC", "5"))
EMBED_MAX_RETRY = int(os.environ.get("EMBED_MAX_RETRY", "3"))
EMBED_FALLBACK_TO_TOY = os.environ.get("EMBED_FALLBACK_TO_TOY", "0") == "1"
EMBED_DIM = int(os.environ.get("EMBED_DIM", "384"))
EMBED_NORMALIZE = os.environ.get("EMBED_NORMALIZE", "1") == "1"
EMBED_CACHE = os.environ.get("EMBED_CACHE", "off").lower()
EMBED_CACHE_PATH = os.environ.get("EMBED_CACHE_PATH", "data/cache/emb.sqlite")
EMBED_CACHE_TTL_SEC = int(os.environ.get("EMBED_CACHE_TTL_SEC", "0"))
EMBED_CACHE_REDIS_URL = os.environ.get("EMBED_CACHE_REDIS_URL", "redis://localhost:6379/0")

BULK_SIZE = int(os.environ.get("OS_BULK_SIZE", "10000"))
PROGRESS_EVERY = int(os.environ.get("OS_PROGRESS_EVERY", "5000"))
RESET = os.environ.get("RESET", "0") == "1"
TIMEOUT_SEC = int(os.environ.get("OS_TIMEOUT_SEC", "30"))
MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")

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
KDC_CODE_RE = re.compile(r"([0-9]{3})(?:\\.[0-9]+)?")


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
    if updated_at_raw and "^^" in updated_at_raw:
        updated_at_raw = updated_at_raw.split("^^", 1)[0].strip()
    if updated_at_raw:
        return updated_at_raw
    if updated_at is None:
        return None
    if hasattr(updated_at, "isoformat"):
        return updated_at.isoformat()
    return None


def extract_kdc_codes(node: Dict[str, Any]) -> List[str]:
    candidates = (
        extract_strings(node.get("kdc"))
        + extract_strings(node.get("classification"))
        + extract_strings(node.get("kdcCode"))
    )
    seen = set()
    codes: List[str] = []
    for value in candidates:
        if not value:
            continue
        for match in KDC_CODE_RE.finditer(value):
            code = match.group(1)
            if code in seen:
                continue
            seen.add(code)
            codes.append(code)
    return codes


def load_kdc_node_map() -> Dict[str, int]:
    conn: Optional[pymysql.Connection] = None
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            charset="utf8mb4",
            autocommit=True,
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT code, id FROM kdc_node")
            rows = cursor.fetchall()
        mapping: Dict[str, int] = {}
        for row in rows:
            if not row or len(row) < 2:
                continue
            code = str(row[0]) if row[0] is not None else ""
            if not code:
                continue
            try:
                mapping[code] = int(row[1])
            except Exception:
                continue
        return mapping
    except Exception as exc:
        print(f"[opensearch] warning: unable to load kdc_node map from MySQL: {exc}")
        return {}
    finally:
        if conn is not None:
            conn.close()


def build_book_doc(record_id: str, node: Dict[str, Any], kdc_node_map: Dict[str, int]) -> Optional[Dict[str, Any]]:
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

    author_names_ko: List[str] = []
    author_names_en: List[str] = []
    for author in authors:
        name_ko = author.get("name_ko")
        name_en = author.get("name_en")
        if isinstance(name_ko, str) and name_ko.strip() and name_ko not in author_names_ko:
            author_names_ko.append(name_ko)
        if isinstance(name_en, str) and name_en.strip() and name_en not in author_names_en:
            author_names_en.append(name_en)

    is_hidden = bool(node.get("is_hidden") or node.get("hidden"))
    series_name = extract_series_name(node)
    kdc_edition = node.get("kdc_edition") or node.get("kdcEdition")

    doc: Dict[str, Any] = {
        "doc_id": record_id,
        "is_hidden": is_hidden,
        "publisher_name": extract_publisher(node),
        "identifiers": extract_identifiers(node) or None,
        "language_code": extract_language(node),
        "issued_year": extract_issued_year(node),
        "volume": extract_volume(node),
        "edition_labels": extract_edition_labels(node) or None,
        "concept_ids": extract_concept_ids(node) or None,
        "updated_at": format_updated_at(updated_raw, updated_at),
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

    kdc_codes = extract_kdc_codes(node)
    if kdc_codes:
        doc["kdc_code"] = kdc_codes[0]
        doc["kdc_path_codes"] = kdc_codes
        node_id = kdc_node_map.get(kdc_codes[0])
        if node_id is not None:
            doc["kdc_node_id"] = node_id
    if isinstance(kdc_edition, str) and kdc_edition.strip():
        doc["kdc_edition"] = kdc_edition.strip()

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
                "type": kind.upper(),
                "lang": lang,
                "text": cleaned,
                "target_id": record_id,
                "target_doc_id": record_id,
                "weight": 1,
                "is_blocked": False,
                "last_seen_at": book_doc.get("updated_at"),
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


class JavaRandom:
    def __init__(self, seed: int) -> None:
        self.seed = (seed ^ 0x5DEECE66D) & ((1 << 48) - 1)

    def next(self, bits: int) -> int:
        self.seed = (self.seed * 0x5DEECE66D + 0xB) & ((1 << 48) - 1)
        return self.seed >> (48 - bits)

    def next_double(self) -> float:
        return ((self.next(26) << 27) + self.next(27)) / float(1 << 53)


def toy_embed(text: str, dim: int = EMBED_DIM) -> List[float]:
    seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()[:8]
    seed = int.from_bytes(seed_bytes, "big", signed=True)
    rng = JavaRandom(seed)
    values = [rng.next_double() for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def build_vector_text(book_doc: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("title_ko", "title_en"):
        value = book_doc.get(key)
        if value:
            parts.append(str(value))
    for author in book_doc.get("authors", []) or []:
        name = author.get("name_ko") or author.get("name_en")
        if name:
            parts.append(str(name))
    publisher = book_doc.get("publisher_name")
    if publisher:
        parts.append(str(publisher))
    return " ".join(parts).strip()


def build_vector_doc(record_id: str, book_doc: Dict[str, Any], node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text_v2 = build_vector_text_v2(book_doc, node)
    if not text_v2:
        return None
    doc: Dict[str, Any] = {
        "doc_id": record_id,
        "is_hidden": bool(book_doc.get("is_hidden", False)),
        "vector_text_v2": text_v2,
        "vector_text_hash": hash_vector_text(text_v2),
    }
    for field in (
        "language_code",
        "issued_year",
        "volume",
        "edition_labels",
        "kdc_node_id",
        "kdc_code",
        "kdc_edition",
        "kdc_path_codes",
        "category_paths",
        "concept_ids",
        "identifiers",
        "updated_at",
    ):
        if book_doc.get(field) is not None:
            doc[field] = book_doc[field]
    return doc


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


def build_chunk_docs(
    record_id: str,
    book_doc: Dict[str, Any],
    node: Dict[str, Any],
    fallback_text: Optional[str],
) -> List[Dict[str, Any]]:
    sections: List[Tuple[str, List[str]]] = []

    def add_section(label: str, values: List[str]) -> None:
        cleaned = []
        seen = set()
        for value in values:
            text = normalize_text(value)
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            cleaned.append(text)
        if cleaned:
            sections.append((label, cleaned))

    if node:
        add_section(
            "summary",
            extract_strings(node.get("summary"))
            + extract_strings(node.get("description"))
            + extract_strings(node.get("abstract")),
        )
        add_section(
            "toc",
            extract_strings(node.get("toc"))
            + extract_strings(node.get("tableOfContents"))
            + extract_strings(node.get("contents")),
        )
        add_section(
            "keywords",
            extract_strings(node.get("keywords"))
            + extract_strings(node.get("keyword"))
            + extract_strings(node.get("subjects"))
            + extract_strings(node.get("subject")),
        )

    if not sections and fallback_text:
        add_section("pseudo", [fallback_text])

    docs: List[Dict[str, Any]] = []
    chunk_index = 0
    for label, values in sections:
        for value in values:
            chunk_id = f"{record_id}#c{chunk_index}"
            doc: Dict[str, Any] = {
                "chunk_id": chunk_id,
                "doc_id": record_id,
                "section": label,
                "text": value,
            }
            if book_doc.get("updated_at"):
                doc["updated_at"] = book_doc["updated_at"]
            docs.append(doc)
            chunk_index += 1
    return docs


class Embedder:
    def __init__(
        self,
        provider: str,
        model: str,
        timeout_sec: float,
        max_retry: int,
        fallback_to_toy: bool,
        normalize: bool,
    ) -> None:
        self.provider = provider
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_retry = max_retry
        self.fallback_to_toy = fallback_to_toy
        self.normalize = normalize

    def cache_key(self) -> str:
        suffix = "norm1" if self.normalize else "norm0"
        return f"{self.model or self.provider}:{suffix}"

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.provider == "toy":
            return [toy_embed(text) for text in texts]
        if self.provider == "mis":
            return self._embed_mis(texts)
        if self.provider == "os":
            return self._embed_opensearch(texts)
        raise RuntimeError(f"unknown embed provider: {self.provider}")

    def _embed_mis(self, texts: List[str]) -> List[List[float]]:
        payload = {"texts": texts, "normalize": self.normalize}
        if self.model:
            payload["model"] = self.model
        url = f"{MIS_URL}/v1/embed"
        return self._post_embed(url, payload, expect_dim=True, expected_len=len(texts))

    def _embed_opensearch(self, texts: List[str]) -> List[List[float]]:
        if not self.model:
            raise RuntimeError("EMBED_MODEL is required for OpenSearch embedding")
        url = f"{OS_URL}/_plugins/_ml/_predict/{self.model}"
        payload = {"text_docs": texts}
        vectors = self._post_embed(url, payload, expect_dim=False, expected_len=len(texts))
        return vectors

    def _post_embed(
        self,
        url: str,
        payload: Dict[str, Any],
        expect_dim: bool,
        expected_len: int,
    ) -> List[List[float]]:
        last_exc = None
        for attempt in range(max(1, self.max_retry + 1)):
            try:
                body = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as response:
                    raw = response.read().decode("utf-8")
                data = json.loads(raw)
                if expect_dim:
                    vectors = data.get("vectors") or []
                else:
                    vectors = self._extract_os_vectors(data)
                if len(vectors) != expected_len:
                    raise RuntimeError("embedding size mismatch")
                return vectors
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retry:
                    time.sleep(min(0.5 * (2 ** attempt), 2.0))
                    continue
                break
        raise RuntimeError(f"embed request failed: {last_exc}") from last_exc

    def _extract_os_vectors(self, data: Dict[str, Any]) -> List[List[float]]:
        results = data.get("inference_results") or []
        vectors: List[List[float]] = []
        for item in results:
            outputs = item.get("output") or []
            for output in outputs:
                values = output.get("data")
                if values:
                    vectors.append(values)
                    break
        return vectors


class EmbedMetrics:
    def __init__(self) -> None:
        self.batch_count = 0
        self.embed_calls = 0
        self.failed_batches = 0
        self.fail_total = 0
        self.cache_hit = 0
        self.cache_miss = 0


def build_embedding_actions(
    candidates: List[Dict[str, Any]],
    embedder: Embedder,
    cache: Optional[EmbeddingCache],
    deadletter_path: Path,
    embed_deadletter: Path,
    metrics: EmbedMetrics,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    local_cache: Dict[str, List[float]] = {}
    model_key = embedder.cache_key()

    for entry in candidates:
        text_hash = entry["hash"]
        cached = local_cache.get(text_hash)
        if cached is None and cache is not None:
            cached = cache.get(text_hash, model_key)
            if cached is not None:
                metrics.cache_hit += 1
        if cached is not None:
            entry["doc"]["embedding"] = cached
            actions.append({"meta": entry["meta"], "doc": entry["doc"]})
        else:
            metrics.cache_miss += 1
            pending.append(entry)

    if not pending:
        return actions

    batch_size = max(1, EMBED_BATCH_SIZE)
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        texts = [entry["text"] for entry in batch]
        metrics.batch_count += 1
        metrics.embed_calls += len(batch)
        started = time.time()
        try:
            vectors = embedder.embed_texts(texts)
        except Exception as exc:
            if embedder.fallback_to_toy:
                vectors = [toy_embed(text) for text in texts]
                print(f"[embed] provider failed, fallback to toy: {exc}")
            else:
                metrics.fail_total += len(batch)
                metrics.failed_batches += 1
                write_embed_deadletter(embed_deadletter, batch, str(exc))
                continue
        took_ms = int((time.time() - started) * 1000)
        print(f"[embed] batch={len(batch)} took_ms={took_ms}")
        if len(vectors) != len(batch):
            metrics.fail_total += len(batch)
            metrics.failed_batches += 1
            write_embed_deadletter(embed_deadletter, batch, "embedding size mismatch")
            continue
        for entry, vector in zip(batch, vectors):
            entry["doc"]["embedding"] = vector
            actions.append({"meta": entry["meta"], "doc": entry["doc"]})
            if cache is not None:
                cache.put(entry["hash"], model_key, vector)
            local_cache[entry["hash"]] = vector

    return actions


def write_embed_deadletter(deadletter_path: Path, batch: List[Dict[str, Any]], reason: str) -> None:
    if not batch:
        return
    with deadletter_path.open("a", encoding="utf-8") as handle:
        for entry in batch:
            payload = {
                "doc_id": entry.get("doc", {}).get("doc_id"),
                "error": reason,
                "vector_text_hash": entry.get("hash"),
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class VectorTextDump:
    def __init__(self, path: Path, limit: int) -> None:
        self.path = path
        self.limit = max(0, limit)
        self.count = 0
        self._handle = None

    def add(self, record_id: str, text_v1: str, text_v2: str, text_hash: str) -> None:
        if self.limit <= 0 or self.count >= self.limit:
            return
        if self._handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("w", encoding="utf-8")
        payload = {
            "doc_id": record_id,
            "vector_text": text_v1,
            "vector_text_v2": text_v2,
            "vector_text_hash": text_hash,
        }
        self._handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.count += 1

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()


def process_file(
    checkpoint_store: CheckpointStore,
    file_path: Path,
    books_deadletter: Path,
    vec_deadletter: Path,
    chunk_deadletter: Path,
    embed_deadletter: Path,
    suggest_deadletter: Path,
    authors_deadletter: Path,
    embedder: Embedder,
    cache: Optional[EmbeddingCache],
    metrics: EmbedMetrics,
    vector_dump: Optional[VectorTextDump],
    kdc_node_map: Dict[str, int],
) -> None:
    dataset = dataset_name(file_path)
    dataset_lower = dataset.lower()
    format_type = detect_format(file_path)
    checkpoint = checkpoint_store.load(file_path)
    start_offset = int(checkpoint.get("offset", 0))
    start_index = int(checkpoint.get("graph_index", 0))

    book_actions: List[Dict[str, Any]] = []
    vec_candidates: List[Dict[str, Any]] = []
    chunk_candidates: List[Dict[str, Any]] = []
    suggest_actions: List[Dict[str, Any]] = []
    author_actions: List[Dict[str, Any]] = []
    processed = 0
    last_checkpoint = time.time()
    last_offset = start_offset
    last_line = checkpoint.get("line", 0)
    last_index = start_index

    def flush(latest_checkpoint: Dict[str, Any]) -> None:
        nonlocal book_actions, vec_candidates, chunk_candidates, suggest_actions, author_actions, last_checkpoint
        post_bulk(BOOKS_ALIAS, book_actions, books_deadletter)
        if ENABLE_VECTOR_INDEX and alias_exists(VEC_ALIAS):
            vec_actions = build_embedding_actions(
                vec_candidates,
                embedder,
                cache,
                vec_deadletter,
                embed_deadletter,
                metrics,
            )
            post_bulk(VEC_ALIAS, vec_actions, vec_deadletter)
        if ENABLE_CHUNK_INDEX and alias_exists(CHUNK_ALIAS):
            chunk_actions = build_embedding_actions(
                chunk_candidates,
                embedder,
                cache,
                chunk_deadletter,
                embed_deadletter,
                metrics,
            )
            post_bulk(CHUNK_ALIAS, chunk_actions, chunk_deadletter)
        post_bulk(AC_ALIAS, suggest_actions, suggest_deadletter)
        if ENABLE_ENTITY_INDICES and alias_exists(AUTHORS_ALIAS):
            post_bulk(AUTHORS_ALIAS, author_actions, authors_deadletter)
        book_actions = []
        vec_candidates = []
        chunk_candidates = []
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
                    book_doc = build_book_doc(record_id, node, kdc_node_map)
                    if book_doc:
                        book_actions.append(
                            {"meta": {"index": {"_id": record_id}}, "doc": book_doc}
                        )
                        vec_doc = None
                        if ENABLE_VECTOR_INDEX:
                            vec_doc = build_vector_doc(record_id, book_doc, node)
                            if vec_doc:
                                vec_candidates.append(
                                    {
                                        "meta": {"index": {"_id": record_id}},
                                        "doc": vec_doc,
                                        "text": vec_doc["vector_text_v2"],
                                        "hash": vec_doc["vector_text_hash"],
                                    }
                                )
                                if vector_dump is not None:
                                    text_v1 = build_vector_text(book_doc)
                                    vector_dump.add(
                                        record_id, text_v1, vec_doc["vector_text_v2"], vec_doc["vector_text_hash"]
                                    )
                        if ENABLE_CHUNK_INDEX:
                            fallback_text = vec_doc["vector_text_v2"] if vec_doc else build_vector_text_v2(
                                book_doc, node
                            )
                            if not fallback_text:
                                fallback_text = build_vector_text(book_doc)
                            chunk_docs = build_chunk_docs(record_id, book_doc, node, fallback_text)
                            for chunk_doc in chunk_docs:
                                chunk_candidates.append(
                                    {
                                        "meta": {"index": {"_id": chunk_doc["chunk_id"]}},
                                        "doc": chunk_doc,
                                        "text": chunk_doc["text"],
                                        "hash": hash_vector_text(chunk_doc["text"]),
                                    }
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
                    book_doc = build_book_doc(record_id, node, kdc_node_map)
                    if book_doc:
                        book_actions.append(
                            {"meta": {"index": {"_id": record_id}}, "doc": book_doc}
                        )
                        vec_doc = None
                        if ENABLE_VECTOR_INDEX:
                            vec_doc = build_vector_doc(record_id, book_doc, node)
                            if vec_doc:
                                vec_candidates.append(
                                    {
                                        "meta": {"index": {"_id": record_id}},
                                        "doc": vec_doc,
                                        "text": vec_doc["vector_text_v2"],
                                        "hash": vec_doc["vector_text_hash"],
                                    }
                                )
                                if vector_dump is not None:
                                    text_v1 = build_vector_text(book_doc)
                                    vector_dump.add(
                                        record_id, text_v1, vec_doc["vector_text_v2"], vec_doc["vector_text_hash"]
                                    )
                        if ENABLE_CHUNK_INDEX:
                            fallback_text = vec_doc["vector_text_v2"] if vec_doc else build_vector_text_v2(
                                book_doc, node
                            )
                            if not fallback_text:
                                fallback_text = build_vector_text(book_doc)
                            chunk_docs = build_chunk_docs(record_id, book_doc, node, fallback_text)
                            for chunk_doc in chunk_docs:
                                chunk_candidates.append(
                                    {
                                        "meta": {"index": {"_id": chunk_doc["chunk_id"]}},
                                        "doc": chunk_doc,
                                        "text": chunk_doc["text"],
                                        "hash": hash_vector_text(chunk_doc["text"]),
                                    }
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

    if book_actions or vec_candidates or chunk_candidates or suggest_actions or author_actions:
        if format_type == "ndjson":
            flush({"offset": last_offset, "line": last_line})
        else:
            flush({"graph_index": last_index})


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest raw data into OpenSearch indices.")
    parser.add_argument("--dump-vector-text-v2", action="store_true")
    parser.add_argument(
        "--dump-vector-text-v2-path",
        default=os.environ.get("VECTOR_TEXT_V2_DUMP_PATH", "data/debug/vector_text_samples_v2.ndjson"),
    )
    parser.add_argument(
        "--dump-vector-text-v2-limit",
        type=int,
        default=int(os.environ.get("VECTOR_TEXT_V2_DUMP_LIMIT", "200")),
    )
    args = parser.parse_args()

    if not raw_dir().exists():
        print(f"Raw data directory not found: {raw_dir()}")
        return 1

    if not alias_exists(BOOKS_ALIAS):
        print(f"Missing alias: {BOOKS_ALIAS}. Run scripts/os_bootstrap_indices_v1_1.sh first.")
        return 1
    if ENABLE_VECTOR_INDEX and not alias_exists(VEC_ALIAS):
        print(f"Missing alias: {VEC_ALIAS}. Run scripts/os_bootstrap_indices_v1_1.sh first.")
        return 1
    global ENABLE_CHUNK_INDEX
    if ENABLE_CHUNK_INDEX and not alias_exists(CHUNK_ALIAS):
        print(f"Optional alias missing: {CHUNK_ALIAS}. Skipping chunk docs.")
        ENABLE_CHUNK_INDEX = False
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
    vec_deadletter = deadletter_dir() / "books_vec_deadletter.ndjson"
    chunk_deadletter = deadletter_dir() / "book_chunks_deadletter.ndjson"
    embed_deadletter = deadletter_dir() / "embed_fail_deadletter.ndjson"
    suggest_deadletter = deadletter_dir() / "ac_candidates_deadletter.ndjson"
    authors_deadletter = deadletter_dir() / "authors_doc_deadletter.ndjson"

    vector_dump = None
    if args.dump_vector_text_v2:
        vector_dump = VectorTextDump(Path(args.dump_vector_text_v2_path), args.dump_vector_text_v2_limit)

    cache: Optional[EmbeddingCache] = None
    if EMBED_CACHE == "sqlite":
        Path(EMBED_CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
        cache = SqliteEmbeddingCache(EMBED_CACHE_PATH, EMBED_CACHE_TTL_SEC)
    elif EMBED_CACHE == "redis":
        try:
            cache = RedisEmbeddingCache(EMBED_CACHE_REDIS_URL, EMBED_CACHE_TTL_SEC)
        except Exception as exc:
            print(f"[embed] redis cache unavailable: {exc}. disabling cache.")
            cache = None

    if EMBED_PROVIDER == "mis" and not MIS_URL:
        print("MIS_URL is required when EMBED_PROVIDER=mis")
        return 1

    embedder = Embedder(
        EMBED_PROVIDER,
        EMBED_MODEL,
        EMBED_TIMEOUT_SEC,
        EMBED_MAX_RETRY,
        EMBED_FALLBACK_TO_TOY,
        EMBED_NORMALIZE,
    )
    metrics = EmbedMetrics()
    kdc_node_map = load_kdc_node_map()
    print(f"[opensearch] kdc_node map loaded: {len(kdc_node_map)} codes")

    files = iter_input_files()
    if not files:
        print(f"No input files found in {raw_dir()}")
        return 1

    for file_path in files:
        print(f"[opensearch] ingesting {file_path.name}")
        process_file(
            checkpoint_store,
            file_path,
            books_deadletter,
            vec_deadletter,
            chunk_deadletter,
            embed_deadletter,
            suggest_deadletter,
            authors_deadletter,
            embedder,
            cache,
            metrics,
            vector_dump,
            kdc_node_map,
        )

    if vector_dump is not None:
        vector_dump.close()
    if ENABLE_VECTOR_INDEX or ENABLE_CHUNK_INDEX:
        print(
            "[embed] batches="
            f"{metrics.batch_count} calls={metrics.embed_calls} failed_batches={metrics.failed_batches} "
            f"cache_hit={metrics.cache_hit} cache_miss={metrics.cache_miss} fail_total={metrics.fail_total}"
        )

    print("[opensearch] ingestion complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
