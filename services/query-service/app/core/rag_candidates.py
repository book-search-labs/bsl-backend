from __future__ import annotations

import os
from typing import Any, List

import httpx

from app.core.metrics import metrics


def _os_url() -> str:
    return os.getenv("QS_OS_URL", "http://localhost:9200").rstrip("/")


def _books_alias() -> str:
    return os.getenv("QS_BOOKS_DOC_ALIAS", "books_doc_read")


def _rag_top_k() -> int:
    return int(os.getenv("QS_RAG_REWRITE_TOP_K", "5"))


def _timeout() -> float:
    return float(os.getenv("QS_RAG_REWRITE_TIMEOUT_SEC", "2.0"))


def _build_candidate(hit: dict[str, Any]) -> dict[str, Any]:
    source = hit.get("_source") or {}
    title = source.get("title_ko") or source.get("title_en") or ""
    authors = source.get("authors") or []
    author = None
    if authors:
        first = authors[0]
        if isinstance(first, dict):
            author = first.get("name_ko") or first.get("name_en")
    isbn = None
    identifiers = source.get("identifiers")
    if isinstance(identifiers, dict):
        isbn = identifiers.get("isbn13")
    return {
        "doc_id": source.get("doc_id"),
        "title": title,
        "author": author,
        "isbn": isbn,
        "score": hit.get("_score"),
    }


async def retrieve_candidates(query: str, trace_id: str, request_id: str, top_k: int | None = None) -> List[dict[str, Any]]:
    if not query:
        return []
    payload = {
        "size": top_k or _rag_top_k(),
        "query": {
            "bool": {
                "filter": [{"term": {"is_hidden": False}}],
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": [
                            "title_ko^3",
                            "title_en^2.5",
                            "series_name^1.8",
                            "author_names_ko^1.6",
                            "author_names_en^1.4",
                            "publisher_name^1.2",
                        ],
                        "operator": "and",
                    }
                },
            }
        },
        "_source": ["doc_id", "title_ko", "title_en", "authors", "author_names_ko", "author_names_en", "identifiers"],
    }
    headers = {"x-trace-id": trace_id, "x-request-id": request_id}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_os_url()}/{_books_alias()}/_search",
                json=payload,
                headers=headers,
                timeout=_timeout(),
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", {}).get("hits", [])
        return [_build_candidate(hit) for hit in hits]
    except Exception:
        metrics.inc("qs_rag_rewrite_error_total")
        return []
