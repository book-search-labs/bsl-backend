import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.core import chat
from app.core.cache import CacheClient


def _collect_stream_events(payload):
    async def _run():
        events = []
        async for event in chat.run_chat_stream(payload, "trace_test", "req_test"):
            events.append(event)
        return events

    return asyncio.run(_run())


def test_internal_rag_explain_returns_trace(monkeypatch):
    async def fake_retrieve_with_optional_rewrite(request, query, canonical_key, locale, trace_id, request_id):
        return (
            {
                "top_n": 5,
                "top_k": 2,
                "lexical": [{"chunk_id": "chunk-1", "score": 0.7, "rank": 1}],
                "vector": [{"chunk_id": "chunk-2", "score": 0.6, "rank": 1}],
                "fused": [{"chunk_id": "chunk-1", "score": 0.8, "rank": 1}],
                "selected": [{"chunk_id": "chunk-1", "score": 0.8, "rank": 1}],
                "reason_codes": ["RAG_RERANK_DISABLED"],
                "rerank": {"enabled": False, "applied": False, "skip_reason": "DISABLED"},
                "took_ms": 12,
                "degraded": False,
            },
            {
                "rewrite_applied": True,
                "rewrite_reason": "RAG_LOW_SCORE",
                "rewritten_query": "harry potter and the chamber of secrets",
            },
        )

    monkeypatch.setattr(chat, "_retrieve_with_optional_rewrite", fake_retrieve_with_optional_rewrite)

    client = TestClient(app)
    response = client.post(
        "/internal/rag/explain",
        json={
            "message": {"role": "user", "content": "harry potter"},
            "client": {"locale": "en-US"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["retrieval"]["lexical"][0]["chunk_id"] == "chunk-1"
    assert data["retrieval"]["selected"][0]["chunk_id"] == "chunk-1"
    assert "REWRITE_APPLIED" in data["reason_codes"]
    assert "RAG_LOW_SCORE" in data["reason_codes"]


def test_run_chat_stream_emits_done_with_validated_citations(monkeypatch):
    chat._CACHE = CacheClient(None)

    async def fake_prepare_chat(request, trace_id, request_id):
        return {
            "ok": True,
            "query": "harry potter",
            "canonical_key": "ck:test",
            "locale": "en-US",
            "selected": [
                {
                    "chunk_id": "chunk-1",
                    "citation_key": "citation-1",
                    "doc_id": "doc-1",
                    "title": "Book A",
                    "url": "https://example.com/a",
                    "snippet": "snippet",
                    "score": 0.9,
                }
            ],
        }

    async def fake_stream_llm(payload, trace_id, request_id):
        async def generator():
            yield chat._sse_event("meta", {"trace_id": trace_id, "request_id": request_id})
            yield chat._sse_event("delta", {"delta": "hello"})

        return generator(), {"answer": "hello", "citations": ["chunk-1"], "llm_error": None, "done_status": "ok"}

    monkeypatch.setattr(chat, "_prepare_chat", fake_prepare_chat)
    monkeypatch.setattr(chat, "_stream_llm", fake_stream_llm)
    monkeypatch.setattr(chat, "_llm_stream_enabled", lambda: True)
    monkeypatch.setattr(chat, "_answer_cache_enabled", lambda: False)

    events = _collect_stream_events({"message": {"role": "user", "content": "hi"}, "options": {"stream": True}})

    assert any("event: done" in event and '"chunk-1"' in event for event in events)
    assert not any("LLM_NO_CITATIONS" in event for event in events)


def test_run_chat_stream_emits_error_when_citation_mapping_fails(monkeypatch):
    chat._CACHE = CacheClient(None)

    async def fake_prepare_chat(request, trace_id, request_id):
        return {
            "ok": True,
            "query": "harry potter",
            "canonical_key": "ck:test",
            "locale": "en-US",
            "selected": [
                {
                    "chunk_id": "chunk-1",
                    "citation_key": "citation-1",
                    "doc_id": "doc-1",
                    "title": "Book A",
                    "url": "https://example.com/a",
                    "snippet": "snippet",
                    "score": 0.9,
                }
            ],
        }

    async def fake_stream_llm(payload, trace_id, request_id):
        async def generator():
            yield chat._sse_event("meta", {"trace_id": trace_id, "request_id": request_id})
            yield chat._sse_event("delta", {"delta": "hello"})

        return generator(), {
            "answer": "hello",
            "citations": ["missing-chunk"],
            "llm_error": None,
            "done_status": "ok",
        }

    monkeypatch.setattr(chat, "_prepare_chat", fake_prepare_chat)
    monkeypatch.setattr(chat, "_stream_llm", fake_stream_llm)
    monkeypatch.setattr(chat, "_llm_stream_enabled", lambda: True)
    monkeypatch.setattr(chat, "_answer_cache_enabled", lambda: False)

    events = _collect_stream_events({"message": {"role": "user", "content": "hi"}, "options": {"stream": True}})

    assert any("event: error" in event and "LLM_NO_CITATIONS" in event for event in events)
    assert any("event: done" in event and "insufficient_evidence" in event for event in events)
