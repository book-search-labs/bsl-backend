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
    assert data["llm_routing"]["mode"] == "json"
    assert isinstance(data["llm_routing"]["final_chain"], list)
    assert "REWRITE_APPLIED" in data["reason_codes"]
    assert "RAG_LOW_SCORE" in data["reason_codes"]


def test_internal_rag_explain_includes_provider_routing_debug(monkeypatch):
    chat._CACHE = CacheClient(None)

    async def fake_retrieve_with_optional_rewrite(request, query, canonical_key, locale, trace_id, request_id):
        return (
            {
                "top_n": 5,
                "top_k": 2,
                "lexical": [],
                "vector": [],
                "fused": [],
                "selected": [
                    {
                        "chunk_id": "chunk-1",
                        "doc_id": "doc-1",
                        "score": 0.9,
                        "title": "배송 안내",
                        "snippet": "배송",
                    }
                ],
                "reason_codes": [],
                "rerank": {"enabled": False, "applied": False},
                "took_ms": 5,
                "degraded": False,
            },
            {
                "rewrite_applied": False,
                "rewrite_reason": None,
                "rewritten_query": "배송 조회",
            },
        )

    monkeypatch.setattr(chat, "_retrieve_with_optional_rewrite", fake_retrieve_with_optional_rewrite)
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_PROVIDER_BLOCKLIST", "primary")
    monkeypatch.setenv("QS_LLM_FORCE_PROVIDER", "primary")
    monkeypatch.setenv("QS_LLM_PROVIDER_BY_INTENT_JSON", '{"SHIPPING":"fallback_1"}')
    monkeypatch.setenv("QS_LLM_HEALTH_ROUTING_ENABLED", "1")
    chat._CACHE.set_json(chat._provider_stats_cache_key("fallback_1"), {"ok": 8, "fail": 1, "streak_fail": 0}, ttl=300)

    client = TestClient(app)
    response = client.post(
        "/internal/rag/explain",
        json={
            "message": {"role": "user", "content": "배송 조회"},
            "client": {"locale": "ko-KR"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    routing = data["llm_routing"]
    assert routing["forced_blocked"] is True
    assert routing["intent_policy_selected"] == "fallback_1"
    assert "primary" in routing["blocked_providers"]
    assert routing["final_chain"][0] == "fallback_1"


def test_get_chat_provider_snapshot_contains_config_and_stats(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_PROVIDER_BLOCKLIST", "primary")
    chat._CACHE.set_json(chat._provider_stats_cache_key("fallback_1"), {"ok": 3, "fail": 1, "streak_fail": 0}, ttl=300)

    snapshot = chat.get_chat_provider_snapshot("trace_test", "req_test")

    assert "routing" in snapshot
    assert "providers" in snapshot
    assert snapshot["config"]["blocklist"] == ["primary"]
    assert any(item["name"] == "fallback_1" for item in snapshot["providers"])


def test_get_chat_session_state_contains_fallback_and_unresolved_context():
    chat._CACHE = CacheClient(None)
    session_id = "u:101:default"
    for _ in range(2):
        chat._increment_fallback_count(session_id)
    chat._save_unresolved_context(
        session_id,
        "환불 조건을 정리해줘. 주문번호는 1234입니다.",
        "LLM_NO_CITATIONS",
        trace_id="trace_prev",
        request_id="req_prev",
    )

    state = chat.get_chat_session_state(session_id, "trace_now", "req_now")

    assert state["session_id"] == session_id
    assert state["fallback_count"] == 2
    assert state["escalation_ready"] is False
    assert state["unresolved_context"]["reason_code"] == "LLM_NO_CITATIONS"
    assert "답변을 보류" in state["unresolved_context"]["reason_message"]
    assert state["unresolved_context"]["next_action"] == "RETRY"
    assert state["unresolved_context"]["query_preview"].startswith("환불 조건을 정리해줘.")


def test_reset_chat_session_state_clears_fallback_and_unresolved_context():
    chat._CACHE = CacheClient(None)
    session_id = "u:102:default"
    for _ in range(3):
        chat._increment_fallback_count(session_id)
    chat._save_unresolved_context(
        session_id,
        "배송 지연 문의",
        "PROVIDER_TIMEOUT",
        trace_id="trace_prev",
        request_id="req_prev",
    )

    reset = chat.reset_chat_session_state(session_id, "trace_now", "req_now")
    state = chat.get_chat_session_state(session_id, "trace_now2", "req_now2")

    assert reset["reset_applied"] is True
    assert reset["previous_fallback_count"] == 3
    assert reset["previous_unresolved_context"] is True
    assert state["fallback_count"] == 0
    assert state["unresolved_context"] is None


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


def test_run_chat_stream_guard_block_message_is_korean(monkeypatch):
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

    async def fake_stream_llm(payload, trace_id, request_id):
        async def generator():
            yield chat._sse_event("meta", {"trace_id": trace_id, "request_id": request_id})
            yield chat._sse_event("delta", {"delta": "해당 주문은 반드시 100% 환불됩니다."})

        return generator(), {
            "answer": "해당 주문은 반드시 100% 환불됩니다.",
            "citations": ["chunk-1"],
            "llm_error": None,
            "done_status": "ok",
        }

    monkeypatch.setattr(chat, "_prepare_chat", fake_prepare_chat)
    monkeypatch.setattr(chat, "_stream_llm", fake_stream_llm)
    monkeypatch.setattr(chat, "_llm_stream_enabled", lambda: True)
    monkeypatch.setattr(chat, "_answer_cache_enabled", lambda: False)
    monkeypatch.setenv("QS_CHAT_OUTPUT_GUARD_ENABLED", "1")
    monkeypatch.setenv("QS_CHAT_GUARD_FORBIDDEN_ANSWER_KEYWORDS", "반드시,100%")

    events = _collect_stream_events({"message": {"role": "user", "content": "환불 정책 알려줘"}, "options": {"stream": True}})

    assert any("event: error" in event and "OUTPUT_GUARD_FORBIDDEN_CLAIM" in event for event in events)
    assert any("응답 품질 검증에서 차단되었습니다." in event for event in events)


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


def test_fallback_emits_recovery_hint_metric(monkeypatch):
    chat._CACHE = CacheClient(None)
    before = dict(chat.metrics.snapshot())

    response = chat._fallback(
        "trace_test",
        "req_test",
        None,
        "PROVIDER_TIMEOUT",
        session_id="sess-metric-1",
        user_id="1",
    )

    after = chat.metrics.snapshot()
    assert response["next_action"] in {"RETRY", "OPEN_SUPPORT_TICKET"}
    expected_key = (
        f"chat_error_recovery_hint_total{{next_action={response['next_action']},"
        "reason_code=PROVIDER_TIMEOUT,source=rag}"
    )
    assert after.get(expected_key, 0) >= before.get(expected_key, 0) + 1


def test_run_chat_blocks_when_citation_coverage_is_too_low(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_MIN_CITATION_COVERAGE_RATIO", "0.8")

    async def fake_prepare_chat(request, trace_id, request_id, **kwargs):
        return {
            "ok": True,
            "query": "일반 문의",
            "canonical_key": "ck:coverage",
            "locale": "ko-KR",
            "selected": [
                {
                    "chunk_id": "chunk-1",
                    "citation_key": "chunk-1",
                    "doc_id": "doc-1",
                    "title": "문서 A",
                    "url": "https://example.com/a",
                    "snippet": "A",
                    "score": 0.9,
                },
                {
                    "chunk_id": "chunk-2",
                    "citation_key": "chunk-2",
                    "doc_id": "doc-2",
                    "title": "문서 B",
                    "url": "https://example.com/b",
                    "snippet": "B",
                    "score": 0.8,
                },
            ],
        }

    async def fake_call_llm_json(payload, trace_id, request_id):
        return {"content": "답변입니다.", "citations": ["chunk-1"]}

    async def fake_tool_chat(request, trace_id, request_id):
        return None

    monkeypatch.setattr(chat, "_prepare_chat", fake_prepare_chat)
    monkeypatch.setattr(chat, "_call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(chat, "run_tool_chat", fake_tool_chat)
    monkeypatch.setattr(chat, "_answer_cache_enabled", lambda: False)

    result = asyncio.run(
        chat.run_chat(
            {
                "session_id": "sess-coverage-1",
                "message": {"role": "user", "content": "질문"},
                "client": {"user_id": "1", "locale": "ko-KR"},
            },
            "trace_test",
            "req_test",
        )
    )

    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "LLM_LOW_CITATION_COVERAGE"
    assert result["next_action"] == "REFINE_QUERY"


def test_call_llm_json_fails_over_to_secondary_provider(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            if int(self.status_code) >= 400:
                raise RuntimeError(f"http_{self.status_code}")

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            if len(call_urls) == 1:
                return FakeResponse(500, {"error": "down"})
            return FakeResponse(200, {"content": "정상 응답", "citations": ["chunk-1"]})

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    data = asyncio.run(chat._call_llm_json({"model": "toy"}, "trace_test", "req_test"))

    assert data["content"] == "정상 응답"
    assert call_urls == [
        "http://llm-primary/v1/generate",
        "http://llm-secondary/v1/generate",
    ]
    after = chat.metrics.snapshot()
    route_fail_key = "chat_provider_route_total{mode=json,provider=primary,result=http_500}"
    failover_key = "chat_provider_failover_total{from=primary,mode=json,reason=http_500,to=fallback_1}"
    route_ok_key = "chat_provider_route_total{mode=json,provider=fallback_1,result=ok}"
    primary_health_key = "chat_provider_health_score{provider=primary}"
    fallback_health_key = "chat_provider_health_score{provider=fallback_1}"
    assert after.get(route_fail_key, 0) >= before.get(route_fail_key, 0) + 1
    assert after.get(failover_key, 0) >= before.get(failover_key, 0) + 1
    assert after.get(route_ok_key, 0) >= before.get(route_ok_key, 0) + 1
    assert isinstance(after.get(primary_health_key), float)
    assert isinstance(after.get(fallback_health_key), float)
    assert float(after.get(fallback_health_key, 0.0)) > float(after.get(primary_health_key, 0.0))


def test_call_llm_json_respects_forced_provider(monkeypatch):
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "강제 라우팅", "citations": ["chunk-1"]})

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_FORCE_PROVIDER", "fallback_1")
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    data = asyncio.run(chat._call_llm_json({"model": "toy"}, "trace_test", "req_test"))

    assert data["content"] == "강제 라우팅"
    assert call_urls == ["http://llm-secondary/v1/generate"]
    after = chat.metrics.snapshot()
    forced_key = "chat_provider_forced_route_total{mode=json,provider=fallback_1,reason=selected}"
    route_key = "chat_provider_route_total{mode=json,provider=fallback_1,result=ok}"
    assert after.get(forced_key, 0) >= before.get(forced_key, 0) + 1
    assert after.get(route_key, 0) >= before.get(route_key, 0) + 1


def test_call_llm_json_uses_low_cost_provider_for_low_risk_query(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "저비용 라우팅", "citations": ["chunk-1"]})

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_COST_STEERING_ENABLED", "1")
    monkeypatch.setenv("QS_LLM_LOW_COST_PROVIDER", "fallback_1")
    monkeypatch.setenv("QS_LLM_PROVIDER_COSTS_JSON", '{"fallback_1": 0.14}')
    monkeypatch.delenv("QS_LLM_FORCE_PROVIDER", raising=False)
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    payload = {
        "model": "toy",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "오늘 읽을 책 추천해줘"},
        ],
    }
    data = asyncio.run(chat._call_llm_json(payload, "trace_test", "req_test"))

    assert data["content"] == "저비용 라우팅"
    assert call_urls == ["http://llm-secondary/v1/generate"]
    after = chat.metrics.snapshot()
    steer_key = "chat_provider_cost_steer_total{mode=json,provider=fallback_1,reason=selected}"
    route_key = "chat_provider_route_total{mode=json,provider=fallback_1,result=ok}"
    cost_key = "chat_provider_cost_per_1k{provider=fallback_1}"
    assert after.get(steer_key, 0) >= before.get(steer_key, 0) + 1
    assert after.get(route_key, 0) >= before.get(route_key, 0) + 1
    assert float(after.get(cost_key, 0.0)) == 0.14


def test_call_llm_json_bypasses_cost_steering_for_high_risk_query(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "고위험 기본 라우팅", "citations": ["chunk-1"]})

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_COST_STEERING_ENABLED", "1")
    monkeypatch.setenv("QS_LLM_LOW_COST_PROVIDER", "fallback_1")
    monkeypatch.setenv("QS_CHAT_RISK_HIGH_KEYWORDS", "환불,배송")
    monkeypatch.delenv("QS_LLM_FORCE_PROVIDER", raising=False)
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    payload = {
        "model": "toy",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "환불 가능 여부 알려줘"},
        ],
    }
    data = asyncio.run(chat._call_llm_json(payload, "trace_test", "req_test"))

    assert data["content"] == "고위험 기본 라우팅"
    assert call_urls == ["http://llm-primary/v1/generate"]
    after = chat.metrics.snapshot()
    bypass_key = "chat_provider_cost_steer_total{mode=json,provider=none,reason=high_risk_bypass}"
    route_key = "chat_provider_route_total{mode=json,provider=primary,result=ok}"
    assert after.get(bypass_key, 0) >= before.get(bypass_key, 0) + 1
    assert after.get(route_key, 0) >= before.get(route_key, 0) + 1


def test_call_llm_json_skips_provider_on_cooldown(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "쿨다운 우회", "citations": ["chunk-1"]})

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_PROVIDER_COOLDOWN_SEC", "60")
    monkeypatch.delenv("QS_LLM_FORCE_PROVIDER", raising=False)
    monkeypatch.delenv("QS_LLM_COST_STEERING_ENABLED", raising=False)
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    chat._mark_provider_unhealthy("primary", "timeout")
    data = asyncio.run(chat._call_llm_json({"model": "toy"}, "trace_test", "req_test"))

    assert data["content"] == "쿨다운 우회"
    assert call_urls == ["http://llm-secondary/v1/generate"]
    after = chat.metrics.snapshot()
    skip_key = "chat_provider_route_total{mode=json,provider=primary,result=cooldown_skip}"
    route_key = "chat_provider_route_total{mode=json,provider=fallback_1,result=ok}"
    assert after.get(skip_key, 0) >= before.get(skip_key, 0) + 1
    assert after.get(route_key, 0) >= before.get(route_key, 0) + 1


def test_call_llm_json_applies_provider_blocklist(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "blocklist 우회", "citations": ["chunk-1"]})

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_PROVIDER_BLOCKLIST", "primary")
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    data = asyncio.run(chat._call_llm_json({"model": "toy"}, "trace_test", "req_test"))

    assert data["content"] == "blocklist 우회"
    assert call_urls == ["http://llm-secondary/v1/generate"]
    after = chat.metrics.snapshot()
    blocked_key = "chat_provider_block_total{mode=json,provider=primary,reason=blocklist}"
    route_key = "chat_provider_route_total{mode=json,provider=fallback_1,result=ok}"
    assert after.get(blocked_key, 0) >= before.get(blocked_key, 0) + 1
    assert after.get(route_key, 0) >= before.get(route_key, 0) + 1


def test_call_llm_json_prefers_higher_health_score_provider(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "health 우선 라우팅", "citations": ["chunk-1"]})

    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_HEALTH_ROUTING_ENABLED", "1")
    monkeypatch.setenv("QS_LLM_HEALTH_MIN_SAMPLE", "3")
    monkeypatch.delenv("QS_LLM_PROVIDER_BLOCKLIST", raising=False)
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    chat._CACHE.set_json(chat._provider_stats_cache_key("primary"), {"ok": 1, "fail": 8}, ttl=300)
    chat._CACHE.set_json(chat._provider_stats_cache_key("fallback_1"), {"ok": 8, "fail": 1}, ttl=300)

    data = asyncio.run(chat._call_llm_json({"model": "toy"}, "trace_test", "req_test"))

    assert data["content"] == "health 우선 라우팅"
    assert call_urls == ["http://llm-secondary/v1/generate"]


def test_call_llm_json_penalizes_recent_failure_streak(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "streak penalty routing", "citations": ["chunk-1"]})

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_HEALTH_ROUTING_ENABLED", "1")
    monkeypatch.setenv("QS_LLM_HEALTH_MIN_SAMPLE", "3")
    monkeypatch.setenv("QS_LLM_HEALTH_STREAK_PENALTY_STEP", "0.1")
    monkeypatch.setenv("QS_LLM_HEALTH_STREAK_PENALTY_MAX", "0.5")
    monkeypatch.delenv("QS_LLM_PROVIDER_BLOCKLIST", raising=False)
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    # primary has better base ratio but severe recent failure streak.
    chat._CACHE.set_json(chat._provider_stats_cache_key("primary"), {"ok": 20, "fail": 1, "streak_fail": 5}, ttl=300)
    chat._CACHE.set_json(chat._provider_stats_cache_key("fallback_1"), {"ok": 10, "fail": 1, "streak_fail": 0}, ttl=300)

    data = asyncio.run(chat._call_llm_json({"model": "toy"}, "trace_test", "req_test"))

    assert data["content"] == "streak penalty routing"
    assert call_urls == ["http://llm-secondary/v1/generate"]
    after = chat.metrics.snapshot()
    penalty_key = "chat_provider_health_penalty{provider=primary}"
    assert float(after.get(penalty_key, 0.0)) >= float(before.get(penalty_key, 0.0))


def test_call_llm_json_marks_forced_provider_blocked(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "강제 차단 우회", "citations": ["chunk-1"]})

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_PROVIDER_BLOCKLIST", "primary")
    monkeypatch.setenv("QS_LLM_FORCE_PROVIDER", "primary")
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    data = asyncio.run(chat._call_llm_json({"model": "toy"}, "trace_test", "req_test"))

    assert data["content"] == "강제 차단 우회"
    assert call_urls == ["http://llm-secondary/v1/generate"]
    after = chat.metrics.snapshot()
    blocked_key = "chat_provider_forced_route_total{mode=json,provider=primary,reason=blocked}"
    assert after.get(blocked_key, 0) >= before.get(blocked_key, 0) + 1


def test_call_llm_json_applies_intent_provider_policy(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "인텐트 라우팅", "citations": ["chunk-1"]})

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_PROVIDER_BY_INTENT_JSON", '{"SHIPPING":"fallback_1"}')
    monkeypatch.delenv("QS_LLM_FORCE_PROVIDER", raising=False)
    monkeypatch.delenv("QS_LLM_PROVIDER_BLOCKLIST", raising=False)
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    payload = {
        "model": "toy",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "배송 현황 알려줘"},
        ],
    }
    data = asyncio.run(chat._call_llm_json(payload, "trace_test", "req_test"))

    assert data["content"] == "인텐트 라우팅"
    assert call_urls == ["http://llm-secondary/v1/generate"]
    after = chat.metrics.snapshot()
    key = "chat_provider_intent_route_total{intent=SHIPPING,mode=json,provider=fallback_1,reason=selected}"
    assert after.get(key, 0) >= before.get(key, 0) + 1


def test_stream_llm_fails_over_before_first_token(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeStreamResponse:
        def __init__(self, status_code, lines):
            self.status_code = status_code
            self._lines = lines

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_lines(self):
            for line in self._lines:
                yield line

        def raise_for_status(self):
            if int(self.status_code) >= 400:
                raise RuntimeError(f"http_{self.status_code}")

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            if len(call_urls) == 1:
                return FakeStreamResponse(503, [])
            return FakeStreamResponse(
                200,
                [
                    "event: delta",
                    'data: {"delta":"안녕하세요"}',
                    "",
                    "event: done",
                    'data: {"status":"ok","citations":["chunk-1"]}',
                    "",
                ],
            )

    async def _run():
        stream_iter, state = await chat._stream_llm(
            {
                "model": "toy",
                "messages": [{"role": "user", "content": "배송 안내 알려줘"}],
            },
            "trace_test",
            "req_test",
        )
        events = []
        async for event in stream_iter:
            events.append(event)
        return events, state

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    events, state = asyncio.run(_run())

    assert call_urls == [
        "http://llm-primary/v1/generate?stream=true",
        "http://llm-secondary/v1/generate?stream=true",
    ]
    assert state["llm_error"] is None
    assert state["answer"] == "안녕하세요"
    assert state["citations"] == ["chunk-1"]
    assert any("event: delta" in event for event in events)

    after = chat.metrics.snapshot()
    failover_key = "chat_provider_failover_total{from=primary,mode=stream,reason=http_503,to=fallback_1}"
    route_key = "chat_provider_route_total{mode=stream,provider=fallback_1,result=ok}"
    assert after.get(failover_key, 0) >= before.get(failover_key, 0) + 1
    assert after.get(route_key, 0) >= before.get(route_key, 0) + 1


def test_stream_llm_applies_intent_provider_policy(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeStreamResponse:
        def __init__(self):
            self.status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_lines(self):
            lines = [
                "event: delta",
                'data: {"delta":"배송 안내"}',
                "",
                "event: done",
                'data: {"status":"ok","citations":["chunk-1"]}',
                "",
            ]
            for line in lines:
                yield line

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeStreamResponse()

    async def _run():
        stream_iter, state = await chat._stream_llm(
            {
                "model": "toy",
                "messages": [{"role": "user", "content": "배송 도착 언제야?"}],
            },
            "trace_test",
            "req_test",
        )
        events = []
        async for event in stream_iter:
            events.append(event)
        return events, state

    before = dict(chat.metrics.snapshot())
    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_PROVIDER_BY_INTENT_JSON", '{"SHIPPING":"fallback_1"}')
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    events, state = asyncio.run(_run())

    assert call_urls == ["http://llm-secondary/v1/generate?stream=true"]
    assert state["answer"] == "배송 안내"
    assert state["citations"] == ["chunk-1"]
    assert any("event: delta" in event for event in events)
    after = chat.metrics.snapshot()
    key = "chat_provider_intent_route_total{intent=SHIPPING,mode=stream,provider=fallback_1,reason=selected}"
    assert after.get(key, 0) >= before.get(key, 0) + 1


def test_call_llm_json_keeps_availability_when_all_blocked(monkeypatch):
    chat._CACHE = CacheClient(None)
    call_urls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            call_urls.append(url)
            return FakeResponse({"content": "가용성 유지", "citations": ["chunk-1"]})

    monkeypatch.setenv("QS_LLM_URL", "http://llm-primary")
    monkeypatch.setenv("QS_LLM_FALLBACK_URLS", "http://llm-secondary")
    monkeypatch.setenv("QS_LLM_PROVIDER_BLOCKLIST", "primary,fallback_1")
    monkeypatch.setattr(chat.httpx, "AsyncClient", FakeAsyncClient)

    data = asyncio.run(chat._call_llm_json({"model": "toy"}, "trace_test", "req_test"))

    assert data["content"] == "가용성 유지"
    assert call_urls == ["http://llm-primary/v1/generate"]


def test_run_chat_provider_timeout_emits_timeout_metric(monkeypatch):
    chat._CACHE = CacheClient(None)
    before = dict(chat.metrics.snapshot())

    async def fake_prepare_chat(request, trace_id, request_id, **kwargs):
        return {
            "ok": True,
            "query": "배송 조회",
            "canonical_key": "ck:timeout",
            "locale": "ko-KR",
            "selected": [
                {
                    "chunk_id": "chunk-1",
                    "citation_key": "chunk-1",
                    "doc_id": "doc-1",
                    "title": "배송 안내",
                    "url": "https://example.com/ship",
                    "snippet": "배송 정보",
                    "score": 0.9,
                }
            ],
        }

    async def fake_call_llm_json(payload, trace_id, request_id):
        raise TimeoutError("llm timeout")

    async def fake_tool_chat(request, trace_id, request_id):
        return None

    monkeypatch.setattr(chat, "_prepare_chat", fake_prepare_chat)
    monkeypatch.setattr(chat, "_call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(chat, "run_tool_chat", fake_tool_chat)
    monkeypatch.setattr(chat, "_answer_cache_enabled", lambda: False)

    result = asyncio.run(
        chat.run_chat(
            {
                "session_id": "sess-timeout-1",
                "message": {"role": "user", "content": "배송 상태 알려줘"},
                "client": {"user_id": "1", "locale": "ko-KR"},
            },
            "trace_test",
            "req_test",
        )
    )

    assert result["reason_code"] == "PROVIDER_TIMEOUT"
    after = chat.metrics.snapshot()
    key = "chat_timeout_total{stage=llm_generate}"
    assert after.get(key, 0) >= before.get(key, 0) + 1
