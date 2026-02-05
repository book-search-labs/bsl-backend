import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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


def _rag_rerank_enabled() -> bool:
    return str(os.getenv("QS_RAG_RERANK_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _rag_rerank_top_n() -> int:
    return int(os.getenv("QS_RAG_RERANK_TOP_N", "20"))


def _rag_rerank_timeout_sec() -> float:
    return float(os.getenv("QS_RAG_RERANK_TIMEOUT_SEC", "1.0"))


def _rag_rerank_task() -> str:
    return os.getenv("QS_RAG_RERANK_TASK", "rerank")


def _rag_rerank_model() -> str:
    return os.getenv("QS_RAG_RERANK_MODEL", "")


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


def _clone_chunk(chunk: RagChunk, score: Optional[float] = None, source: Optional[str] = None) -> RagChunk:
    return RagChunk(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        citation_key=chunk.citation_key,
        title=chunk.title,
        url=chunk.url,
        content=chunk.content,
        score=chunk.score if score is None else float(score),
        source=chunk.source if source is None else source,
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
    fused: List[RagChunk] = []
    for chunk_id, score in ordered:
        chunk = by_id[chunk_id]
        fused.append(_clone_chunk(chunk, score=score, source="fused"))
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


async def _search_lexical(client: httpx.AsyncClient, query: str, top_n: int) -> List[RagChunk]:
    payload = {
        "size": top_n,
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


async def _search_vector(client: httpx.AsyncClient, embedding: List[float], top_n: int) -> List[RagChunk]:
    payload = {
        "size": top_n,
        "query": {"knn": {"embedding": {"vector": embedding, "k": top_n}}},
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

    results: List[RagChunk] = []
    for hit in hits:
        chunk_id = hit.get("_id")
        doc = docs_by_id.get(chunk_id)
        if not doc:
            continue
        hit_copy = {"_id": chunk_id, "_score": hit.get("_score"), "_source": doc.get("_source")}
        results.append(_build_chunk(hit_copy, "vector"))
    return results


def _chunk_to_trace(chunk: RagChunk, rank: int) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "citation_key": chunk.citation_key,
        "source_title": chunk.title,
        "title": chunk.title,
        "url": chunk.url,
        "snippet": chunk.content,
        "score": chunk.score,
        "rank": rank,
        "source": chunk.source,
    }


async def _rerank_chunks(
    client: httpx.AsyncClient,
    query: str,
    chunks: List[RagChunk],
    trace_id: str,
    request_id: str,
    timeout_sec: float,
) -> tuple[List[RagChunk], str]:
    if not chunks:
        return [], "RAG_RERANK_NO_CANDIDATES"

    pairs: list[dict[str, Any]] = []
    for chunk in chunks:
        pairs.append(
            {
                "pair_id": chunk.chunk_id,
                "query": query,
                "doc_id": chunk.chunk_id,
                "doc": f"{chunk.title} {chunk.content}".strip(),
                "features": {
                    "rrf_score": chunk.score,
                },
            }
        )

    payload: dict[str, Any] = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "task": _rag_rerank_task(),
        "pairs": pairs,
        "options": {
            "timeout_ms": max(1, int(timeout_sec * 1000)),
            "return_debug": False,
        },
    }
    model = _rag_rerank_model()
    if model:
        payload["model"] = model

    response = await client.post(f"{_mis_url()}/v1/score", json=payload, timeout=timeout_sec)
    response.raise_for_status()
    data = response.json()
    scores = data.get("scores") or []
    if len(scores) != len(chunks):
        raise ValueError("rerank_score_size_mismatch")

    ranked: list[RagChunk] = []
    for idx, chunk in enumerate(chunks):
        try:
            score = float(scores[idx])
        except Exception:
            score = 0.0
        ranked.append(_clone_chunk(chunk, score=score, source="rerank"))
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked, str(data.get("model") or model or "rerank")


async def retrieve_chunks_with_trace(
    query: str,
    trace_id: str,
    request_id: str,
    top_k: Optional[int] = None,
    top_n: Optional[int] = None,
    rerank_enabled: Optional[bool] = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    resolved_top_n = max(1, top_n if top_n is not None else _rag_top_n())
    resolved_top_k = max(1, top_k if top_k is not None else _rag_top_k())
    use_rerank = _rag_rerank_enabled() if rerank_enabled is None else bool(rerank_enabled)

    lexical: list[RagChunk] = []
    vector: list[RagChunk] = []
    fused: list[RagChunk] = []
    selected: list[RagChunk] = []
    reason_codes: list[str] = []
    rerank_info: dict[str, Any] = {
        "enabled": use_rerank,
        "applied": False,
        "model": None,
        "skip_reason": None,
        "error": None,
    }

    try:
        async with httpx.AsyncClient() as client:
            lexical = await _search_lexical(client, query, resolved_top_n)
            embedding = await _embed_query(client, query, trace_id, request_id)
            if embedding:
                vector = await _search_vector(client, embedding, resolved_top_n)
            else:
                reason_codes.append("RAG_VECTOR_SKIPPED")

            fused = _rrf_fuse(lexical, vector, _rrf_k()) if vector else list(lexical)
            rerank_candidates = fused[: min(len(fused), _rag_rerank_top_n())]

            if use_rerank:
                if rerank_candidates:
                    try:
                        reranked, rerank_model = await _rerank_chunks(
                            client,
                            query,
                            rerank_candidates,
                            trace_id,
                            request_id,
                            _rag_rerank_timeout_sec(),
                        )
                        rerank_info["applied"] = True
                        rerank_info["model"] = rerank_model
                        reason_codes.append("RAG_RERANK_APPLIED")
                        selected = reranked[:resolved_top_k]
                    except httpx.TimeoutException:
                        rerank_info["skip_reason"] = "PROVIDER_TIMEOUT"
                        rerank_info["error"] = "timeout"
                        reason_codes.append("RAG_RERANK_TIMEOUT")
                        selected = fused[:resolved_top_k]
                    except Exception as exc:
                        rerank_info["skip_reason"] = "PROVIDER_ERROR"
                        rerank_info["error"] = str(exc)
                        reason_codes.append("RAG_RERANK_ERROR")
                        selected = fused[:resolved_top_k]
                else:
                    rerank_info["skip_reason"] = "NO_CANDIDATES"
                    reason_codes.append("RAG_RERANK_NO_CANDIDATES")
                    selected = []
            else:
                rerank_info["skip_reason"] = "DISABLED"
                reason_codes.append("RAG_RERANK_DISABLED")
                selected = fused[:resolved_top_k]

        took_ms = int((time.perf_counter() - started) * 1000)
        metrics.inc("qs_rag_retrieve_total")
        metrics.inc("rag_retrieve_latency_ms", value=max(0, took_ms))
        metrics.inc("rag_chunks_found_count", value=max(0, len(selected)))

        return {
            "query": query,
            "top_n": resolved_top_n,
            "top_k": resolved_top_k,
            "lexical": [_chunk_to_trace(chunk, idx + 1) for idx, chunk in enumerate(lexical)],
            "vector": [_chunk_to_trace(chunk, idx + 1) for idx, chunk in enumerate(vector)],
            "fused": [_chunk_to_trace(chunk, idx + 1) for idx, chunk in enumerate(fused)],
            "selected": [_chunk_to_trace(chunk, idx + 1) for idx, chunk in enumerate(selected)],
            "reason_codes": reason_codes,
            "rerank": rerank_info,
            "took_ms": took_ms,
            "degraded": bool(rerank_info.get("skip_reason") and rerank_info.get("skip_reason") != "DISABLED"),
        }
    except Exception as exc:
        metrics.inc("qs_rag_retrieve_error_total")
        metrics.inc("chat_fallback_total", {"reason": "RAG_RETRIEVE_ERROR"})
        return {
            "query": query,
            "top_n": resolved_top_n,
            "top_k": resolved_top_k,
            "lexical": [],
            "vector": [],
            "fused": [],
            "selected": [],
            "reason_codes": ["RAG_RETRIEVE_ERROR"],
            "rerank": {
                "enabled": use_rerank,
                "applied": False,
                "model": None,
                "skip_reason": "RETRIEVE_ERROR",
                "error": str(exc),
            },
            "took_ms": int((time.perf_counter() - started) * 1000),
            "degraded": True,
        }


async def retrieve_chunks(query: str, trace_id: str, request_id: str, top_k: Optional[int] = None) -> List[RagChunk]:
    trace = await retrieve_chunks_with_trace(query, trace_id, request_id, top_k=top_k)
    selected: list[RagChunk] = []
    for item in trace.get("selected", []):
        selected.append(
            RagChunk(
                chunk_id=str(item.get("chunk_id") or ""),
                doc_id=str(item.get("doc_id") or ""),
                citation_key=str(item.get("citation_key") or ""),
                title=str(item.get("title") or item.get("source_title") or ""),
                url=str(item.get("url") or ""),
                content=str(item.get("snippet") or ""),
                score=float(item.get("score") or 0.0),
                source=str(item.get("source") or "fused"),
            )
        )
    return selected
