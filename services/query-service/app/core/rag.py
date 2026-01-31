import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

from app.core.metrics import metrics


@dataclass
class RagChunk:
    chunk_id: str
    doc_id: str
    citation_key: str
    title: str
    url: str
    content: str
    score: float
    source: str


def _os_url() -> str:
    return os.getenv("QS_OS_URL", "http://localhost:9200").rstrip("/")


def _docs_doc_alias() -> str:
    return os.getenv("QS_DOCS_DOC_ALIAS", "docs_doc_read")


def _docs_vec_alias() -> str:
    return os.getenv("QS_DOCS_VEC_ALIAS", "docs_vec_read")


def _embed_mode() -> str:
    return os.getenv("QS_EMBEDDING_MODE", "mis")


def _mis_url() -> str:
    return os.getenv("QS_MIS_URL", "http://localhost:8005").rstrip("/")


def _rag_top_n() -> int:
    return int(os.getenv("QS_RAG_TOP_N", "40"))


def _rag_top_k() -> int:
    return int(os.getenv("QS_RAG_TOP_K", "6"))


def _rrf_k() -> int:
    return int(os.getenv("QS_RRF_K", "60"))


def _snippet(source: dict, highlight: dict | None) -> str:
    if highlight:
        fragments = highlight.get("content") or highlight.get("content_en")
        if fragments:
            return " ".join(fragments)[:260]
    content = source.get("content") or source.get("content_en") or ""
    return content[:260]


def _build_chunk(hit: dict, origin: str) -> RagChunk:
    source = hit.get("_source") or {}
    return RagChunk(
        chunk_id=hit.get("_id", ""),
        doc_id=str(source.get("doc_id") or ""),
        citation_key=str(source.get("citation_key") or ""),
        title=str(source.get("title") or ""),
        url=str(source.get("url") or ""),
        content=_snippet(source, hit.get("highlight")),
        score=float(hit.get("_score") or 0.0),
        source=origin,
    )


def _rrf_fuse(lex: List[RagChunk], vec: List[RagChunk], k: int) -> List[RagChunk]:
    scores: Dict[str, float] = {}
    by_id: Dict[str, RagChunk] = {}

    for rank, chunk in enumerate(lex, start=1):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
        by_id.setdefault(chunk.chunk_id, chunk)
    for rank, chunk in enumerate(vec, start=1):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
        by_id.setdefault(chunk.chunk_id, chunk)

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    fused = []
    for chunk_id, score in ordered:
        chunk = by_id[chunk_id]
        fused.append(
            RagChunk(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                citation_key=chunk.citation_key,
                title=chunk.title,
                url=chunk.url,
                content=chunk.content,
                score=score,
                source=chunk.source,
            )
        )
    return fused


async def _embed_query(client: httpx.AsyncClient, text: str, trace_id: str, request_id: str) -> Optional[List[float]]:
    if _embed_mode() != "mis":
        return None
    payload = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "model": os.getenv("QS_EMBED_MODEL", "toy_embed_v1"),
        "texts": [text],
    }
    try:
        resp = await client.post(f"{_mis_url()}/embed", json=payload, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        vectors = data.get("vectors", [])
        if vectors:
            return vectors[0]
    except Exception:
        metrics.inc("qs_rag_embed_error_total")
    return None


async def _search_lexical(client: httpx.AsyncClient, query: str) -> List[RagChunk]:
    payload = {
        "size": _rag_top_n(),
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title^2", "content", "content_en"],
                "operator": "and",
            }
        },
        "highlight": {
            "fields": {
                "content": {"fragment_size": 160, "number_of_fragments": 1},
                "content_en": {"fragment_size": 160, "number_of_fragments": 1},
            }
        },
    }
    resp = await client.post(f"{_os_url()}/{_docs_doc_alias()}/_search", json=payload, timeout=5.0)
    resp.raise_for_status()
    hits = resp.json().get("hits", {}).get("hits", [])
    return [_build_chunk(hit, "lexical") for hit in hits]


async def _search_vector(client: httpx.AsyncClient, embedding: List[float]) -> List[RagChunk]:
    payload = {
        "size": _rag_top_n(),
        "query": {"knn": {"embedding": {"vector": embedding, "k": _rag_top_n()}}},
    }
    resp = await client.post(f"{_os_url()}/{_docs_vec_alias()}/_search", json=payload, timeout=5.0)
    resp.raise_for_status()
    hits = resp.json().get("hits", {}).get("hits", [])
    chunk_ids = [hit.get("_id") for hit in hits if hit.get("_id")]
    if not chunk_ids:
        return []

    mget_payload = {"ids": chunk_ids}
    mget_resp = await client.post(f"{_os_url()}/{_docs_doc_alias()}/_mget", json=mget_payload, timeout=5.0)
    mget_resp.raise_for_status()
    docs = mget_resp.json().get("docs", [])
    docs_by_id = {doc.get("_id"): doc for doc in docs if doc.get("_id")}

    results = []
    for hit in hits:
        chunk_id = hit.get("_id")
        doc = docs_by_id.get(chunk_id)
        if not doc:
            continue
        hit_copy = {"_id": chunk_id, "_score": hit.get("_score"), "_source": doc.get("_source")}
        results.append(_build_chunk(hit_copy, "vector"))
    return results


async def retrieve_chunks(query: str, trace_id: str, request_id: str, top_k: Optional[int] = None) -> List[RagChunk]:
    try:
        async with httpx.AsyncClient() as client:
            lexical = await _search_lexical(client, query)
            embedding = await _embed_query(client, query, trace_id, request_id)
            vector = []
            if embedding:
                vector = await _search_vector(client, embedding)
        fused = _rrf_fuse(lexical, vector, _rrf_k()) if vector else lexical
        limit = top_k if top_k is not None else _rag_top_k()
        top_k = fused[: limit]
        metrics.inc("qs_rag_retrieve_total")
        return top_k
    except Exception:
        metrics.inc("qs_rag_retrieve_error_total")
        return []
