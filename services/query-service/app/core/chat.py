import os
import re
from typing import Dict, List

import httpx

from app.core.metrics import metrics
from app.core.rag import RagChunk, retrieve_chunks


def _llm_url() -> str:
    return os.getenv("QS_LLM_URL", "http://localhost:8010").rstrip("/")


def _extract_citations(text: str) -> List[str]:
    matches = re.findall(r"\[([a-zA-Z0-9_\-:#]+)\]", text or "")
    return list({match for match in matches})


def _build_context(chunks: List[RagChunk]) -> Dict:
    return {
        "chunks": [
            {
                "citation_key": chunk.citation_key,
                "title": chunk.title,
                "url": chunk.url,
                "content": chunk.content,
            }
            for chunk in chunks
        ]
    }


def _format_sources(chunks: List[RagChunk]) -> List[Dict]:
    sources = []
    for chunk in chunks:
        sources.append(
            {
                "citation_key": chunk.citation_key,
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "title": chunk.title,
                "url": chunk.url,
                "snippet": chunk.content,
            }
        )
    return sources


def _fallback(trace_id: str, request_id: str, message: str) -> Dict:
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "answer": {
            "role": "assistant",
            "content": message,
        },
        "sources": [],
        "citations": [],
        "status": "insufficient_evidence",
    }


def _validate_citations(answer: str, allowed: List[str]) -> List[str]:
    found = _extract_citations(answer)
    return [cite for cite in found if cite in allowed]


async def run_chat(request: Dict, trace_id: str, request_id: str) -> Dict:
    message = request.get("message") or {}
    query = message.get("content") or ""
    if not query:
        return _fallback(trace_id, request_id, "Missing user message.")

    options = request.get("options") or {}
    top_k = options.get("top_k") if isinstance(options, dict) else None
    chunks = await retrieve_chunks(query, trace_id, request_id, top_k=top_k if isinstance(top_k, int) else None)
    if not chunks:
        metrics.inc("qs_rag_no_sources_total")
        return _fallback(trace_id, request_id, "Insufficient evidence to answer with citations.")

    messages = [{"role": "system", "content": "Answer using provided sources and cite them."}]
    history = request.get("history") or []
    if isinstance(history, list):
        for item in history[-6:]:
            if isinstance(item, dict) and item.get("role") and item.get("content"):
                messages.append({"role": item.get("role"), "content": item.get("content")})
    messages.append({"role": "user", "content": query})

    payload = {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "model": os.getenv("QS_LLM_MODEL", "toy-rag-v1"),
        "messages": messages,
        "context": _build_context(chunks),
        "citations_required": True,
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{_llm_url()}/v1/generate", json=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            metrics.inc("qs_rag_llm_error_total")
            return _fallback(trace_id, request_id, "LLM gateway unavailable.")

    answer_text = data.get("content") or ""
    allowed = [chunk.citation_key for chunk in chunks]
    citations = _validate_citations(answer_text, allowed)
    if not citations:
        metrics.inc("qs_rag_citation_missing_total")
        return _fallback(trace_id, request_id, "Insufficient evidence to answer with citations.")

    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "answer": {"role": "assistant", "content": answer_text},
        "sources": _format_sources(chunks),
        "citations": citations,
        "status": "ok",
    }
