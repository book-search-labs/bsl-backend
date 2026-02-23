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

    async def fake_prepare_chat(request, trace_id, request_id, **kwargs):
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

    async def fake_prepare_chat(request, trace_id, request_id, **kwargs):
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


def test_run_chat_blocks_forbidden_claim_on_high_risk_query(monkeypatch):
    chat._CACHE = CacheClient(None)

    async def fake_prepare_chat(request, trace_id, request_id, **kwargs):
        return {
            "ok": True,
            "query": "환불 정책 알려줘",
            "canonical_key": "ck:test",
            "locale": "ko-KR",
            "selected": [
                {
                    "chunk_id": "chunk-1",
                    "citation_key": "chunk-1",
                    "doc_id": "doc-1",
                    "title": "환불 정책",
                    "url": "https://example.com/refund",
                    "snippet": "환불은 정책에 따라 달라집니다.",
                    "score": 0.9,
                }
            ],
        }

    async def fake_call_llm_json(payload, trace_id, request_id):
        return {"content": "해당 주문은 반드시 100% 환불됩니다.", "citations": ["chunk-1"]}

    monkeypatch.setattr(chat, "_prepare_chat", fake_prepare_chat)
    monkeypatch.setattr(chat, "_call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(chat, "_answer_cache_enabled", lambda: False)
    monkeypatch.setenv("QS_CHAT_OUTPUT_GUARD_ENABLED", "1")
    monkeypatch.setenv("QS_CHAT_GUARD_FORBIDDEN_ANSWER_KEYWORDS", "반드시,100%")

    result = asyncio.run(chat.run_chat({"message": {"role": "user", "content": "환불 정책 알려줘"}}, "trace_test", "req_test"))

    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "OUTPUT_GUARD_FORBIDDEN_CLAIM"
    assert result["next_action"] == "OPEN_SUPPORT_TICKET"
    assert "정책상" in result["answer"]["content"]


def test_compute_risk_band_high_risk_with_citations():
    band = chat._compute_risk_band("refund status", "ok", ["chunk-1"], None)
    assert band == "R2"


def test_compute_risk_band_error_path():
    band = chat._compute_risk_band("배송 상태", "error", [], "PROVIDER_TIMEOUT")
    assert band == "R3"


def test_fallback_escalates_after_repeated_failures(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_FALLBACK_ESCALATE_THRESHOLD", "2")

    first = chat._fallback(
        "trace_test",
        "req_1",
        None,
        "RAG_NO_CHUNKS",
        session_id="sess-escalate-1",
        user_id="1",
    )
    assert first["next_action"] == "REFINE_QUERY"
    assert first["fallback_count"] == 1
    assert first["escalated"] is False

    second = chat._fallback(
        "trace_test",
        "req_2",
        None,
        "RAG_NO_CHUNKS",
        session_id="sess-escalate-1",
        user_id="1",
    )
    assert second["next_action"] == "OPEN_SUPPORT_TICKET"
    assert second["fallback_count"] == 2
    assert second["escalated"] is True


def test_run_chat_rejects_too_long_message(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_MAX_MESSAGE_CHARS", "100")

    result = asyncio.run(
        chat.run_chat(
            {
                "session_id": "sess-limits-1",
                "message": {"role": "user", "content": "가" * 101},
                "client": {"user_id": "1", "locale": "ko-KR"},
            },
            "trace_test",
            "req_test",
        )
    )

    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "CHAT_MESSAGE_TOO_LONG"
    assert result["next_action"] == "REFINE_QUERY"
    assert result["recoverable"] is True


def test_run_chat_rejects_history_too_long(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_MAX_HISTORY_TURNS", "1")

    result = asyncio.run(
        chat.run_chat(
            {
                "session_id": "sess-limits-2",
                "message": {"role": "user", "content": "배송 상태 알려줘"},
                "history": [
                    {"role": "assistant", "content": "첫 번째"},
                    {"role": "user", "content": "두 번째"},
                ],
                "client": {"user_id": "1", "locale": "ko-KR"},
            },
            "trace_test",
            "req_test",
        )
    )

    assert result["reason_code"] == "CHAT_HISTORY_TOO_LONG"
    assert result["status"] == "insufficient_evidence"


def test_run_chat_stream_rejects_invalid_session_id():
    chat._CACHE = CacheClient(None)

    events = _collect_stream_events(
        {
            "session_id": "bad session!",
            "message": {"role": "user", "content": "주문 상태 알려줘"},
            "options": {"stream": True},
            "client": {"user_id": "1"},
        }
    )

    assert any("event: done" in event and '"CHAT_INVALID_SESSION_ID"' in event for event in events)


def test_run_chat_clears_unresolved_context_on_success(monkeypatch):
    chat._CACHE = CacheClient(None)
    session_id = "sess-clear-success-1"
    chat._CACHE.set_json(
        f"chat:unresolved:{session_id}",
        {"query": "이전 실패", "reason_code": "RAG_NO_CHUNKS"},
        ttl=300,
    )

    async def fake_prepare_chat(request, trace_id, request_id, **kwargs):
        return {
            "ok": True,
            "query": "환불 정책",
            "canonical_key": "ck:clear",
            "locale": "ko-KR",
            "selected": [
                {
                    "chunk_id": "chunk-1",
                    "citation_key": "chunk-1",
                    "doc_id": "doc-1",
                    "title": "환불 정책",
                    "url": "https://example.com/refund",
                    "snippet": "환불 정책 안내",
                    "score": 0.9,
                }
            ],
        }

    async def fake_call_llm_json(payload, trace_id, request_id):
        return {"content": "환불은 주문 상태에 따라 가능합니다.", "citations": ["chunk-1"]}

    async def fake_tool_chat(request, trace_id, request_id):
        return None

    monkeypatch.setattr(chat, "_prepare_chat", fake_prepare_chat)
    monkeypatch.setattr(chat, "_call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(chat, "run_tool_chat", fake_tool_chat)
    monkeypatch.setattr(chat, "_answer_cache_enabled", lambda: False)

    result = asyncio.run(
        chat.run_chat(
            {
                "session_id": session_id,
                "message": {"role": "user", "content": "환불 정책 알려줘"},
                "client": {"user_id": "1", "locale": "ko-KR"},
            },
            "trace_test",
            "req_test",
        )
    )

    assert result["status"] == "ok"
    cached = chat._CACHE.get_json(f"chat:unresolved:{session_id}")
    assert cached is None or cached.get("cleared") is True


def test_run_chat_clears_unresolved_context_on_tool_path(monkeypatch):
    chat._CACHE = CacheClient(None)
    session_id = "sess-clear-tool-1"
    chat._CACHE.set_json(
        f"chat:unresolved:{session_id}",
        {"query": "이전 실패", "reason_code": "PROVIDER_TIMEOUT"},
        ttl=300,
    )

    async def fake_tool_chat(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "주문 상태는 결제 완료입니다."},
            "sources": [],
            "citations": ["tool:order_lookup:1"],
        }

    monkeypatch.setattr(chat, "run_tool_chat", fake_tool_chat)

    result = asyncio.run(
        chat.run_chat(
            {
                "session_id": session_id,
                "message": {"role": "user", "content": "주문 상태 확인"},
                "client": {"user_id": "1", "locale": "ko-KR"},
            },
            "trace_test",
            "req_test",
        )
    )

    assert result["status"] == "ok"
    cached = chat._CACHE.get_json(f"chat:unresolved:{session_id}")
    assert cached is None or cached.get("cleared") is True
