import asyncio

from app.core.cache import CacheClient
from app.core.chat_graph import authz_gate, confirm_fsm, domain_nodes, langsmith_trace
from app.core.chat_graph.runtime import run_chat_graph


def _run(coro):
    return asyncio.run(coro)


def test_run_chat_graph_happy_path_returns_legacy_response_shape():
    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {"session_id": "u:101:default", "message": {"role": "user", "content": "배송 상태 알려줘"}},
            "trace_1",
            "req_1",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert result.stage == "persist"
    assert result.response["status"] == "ok"
    assert result.response["reason_code"] == "OK"
    assert result.state["route"] == "ANSWER"
    assert result.state["state_version"] == 2


def test_run_chat_graph_routes_empty_query_to_ask_without_executor_call():
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {"session_id": "u:102:default", "message": {"role": "user", "content": ""}},
            "trace_2",
            "req_2",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert called["count"] == 0
    assert result.response["status"] == "insufficient_evidence"
    assert result.response["reason_code"] == "NO_MESSAGES"
    assert result.response["next_action"] == "PROVIDE_REQUIRED_INFO"


def test_run_chat_graph_fallbacks_when_legacy_response_is_not_object():
    async def fake_legacy_executor(request, trace_id, request_id):
        return "invalid"  # type: ignore[return-value]

    result = _run(
        run_chat_graph(
            {"session_id": "u:103:default", "message": {"role": "user", "content": "주문 상태"}},
            "trace_3",
            "req_3",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert result.response["status"] == "insufficient_evidence"
    assert result.response["reason_code"] == "CHAT_GRAPH_EXECUTION_ERROR"
    assert result.state["tool_result"]["source"] == "legacy_executor"


def test_run_chat_graph_sanitizes_forbidden_reason_code():
    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "insufficient_evidence",
            "reason_code": "UNKNOWN",
            "recoverable": True,
            "next_action": "RETRY",
            "retry_after_ms": 1000,
            "answer": {"role": "assistant", "content": "재시도해 주세요."},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {"session_id": "u:104:default", "message": {"role": "user", "content": "상태 알려줘"}},
            "trace_104",
            "req_104",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert result.response["reason_code"] == "CHAT_REASON_CODE_INVALID"
    assert result.state["reason_code"] == "CHAT_REASON_CODE_INVALID"


def test_run_chat_graph_emits_langsmith_audit_events_even_when_disabled(monkeypatch):
    langsmith_trace._CACHE = CacheClient(None)
    monkeypatch.delenv("QS_CHAT_LANGSMITH_ENABLED", raising=False)

    async def fake_legacy_executor(request, trace_id, request_id):
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    _run(
        run_chat_graph(
            {"session_id": "u:105:default", "message": {"role": "user", "content": "배송 상태 알려줘"}},
            "trace_105",
            "req_105",
            legacy_executor=fake_legacy_executor,
        )
    )

    rows = langsmith_trace.load_trace_audit("u:105:default")
    assert len(rows) >= 3
    assert rows[0]["event_type"] == "run_start"
    assert rows[-1]["event_type"] in {"run_end", "run_error"}


def test_run_chat_graph_routes_selection_reference_to_options():
    domain_nodes._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {"status": "ok", "reason_code": "OK", "answer": {"role": "assistant", "content": "응답"}, "sources": [], "citations": []}

    result = _run(
        run_chat_graph(
            {"session_id": "u:106:default", "message": {"role": "user", "content": "그거 자세히 알려줘"}},
            "trace_106",
            "req_106",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert called["count"] == 0
    assert result.response["reason_code"] == "ROUTE_OPTIONS_SELECTION_REQUIRED"
    assert result.response["status"] == "insufficient_evidence"


def test_run_chat_graph_policy_topic_cache_hit_skips_executor(monkeypatch):
    domain_nodes._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "환불 정책 안내"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    request = {"session_id": "u:107:default", "message": {"role": "user", "content": "환불 정책 안내해줘"}}
    _run(run_chat_graph(request, "trace_107a", "req_107a", legacy_executor=fake_legacy_executor))
    second = _run(run_chat_graph(request, "trace_107b", "req_107b", legacy_executor=fake_legacy_executor))

    assert called["count"] == 1
    assert second.response["status"] == "ok"
    assert second.state["tool_result"]["source"] == "policy_topic_cache"


def test_run_chat_graph_selection_memory_rewrites_second_turn_query():
    domain_nodes._CACHE = CacheClient(None)
    captured_queries: list[str] = []

    async def fake_legacy_executor(request, trace_id, request_id):
        message = request.get("message") if isinstance(request.get("message"), dict) else {}
        captured_queries.append(str(message.get("content") or ""))
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "추천 결과"},
            "sources": [
                {"title": "A Book", "doc_id": "a1"},
                {"title": "B Book", "doc_id": "b1"},
            ],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    first = {"session_id": "u:108:default", "message": {"role": "user", "content": "책 추천해줘"}}
    second = {"session_id": "u:108:default", "message": {"role": "user", "content": "2번째 자세히 알려줘"}}

    _run(run_chat_graph(first, "trace_108a", "req_108a", legacy_executor=fake_legacy_executor))
    _run(run_chat_graph(second, "trace_108b", "req_108b", legacy_executor=fake_legacy_executor))

    assert len(captured_queries) == 2
    assert captured_queries[1].startswith("B Book")


def test_run_chat_graph_denies_sensitive_action_without_auth_context():
    confirm_fsm._CACHE = CacheClient(None)
    authz_gate._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {
                "session_id": "u:301:default",
                "message": {"role": "user", "content": "주문 취소해줘"},
                "client": {"user_id": "301"},
            },
            "trace_4",
            "req_4",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert called["count"] == 0
    assert result.response["reason_code"] == "AUTH_CONTEXT_MISSING"
    assert result.response["next_action"] == "OPEN_SUPPORT_TICKET"


def test_run_chat_graph_denies_cross_user_sensitive_action():
    confirm_fsm._CACHE = CacheClient(None)
    authz_gate._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "reason_code": "OK",
            "recoverable": False,
            "next_action": "NONE",
            "retry_after_ms": None,
            "answer": {"role": "assistant", "content": "정상 응답"},
            "sources": [],
            "citations": [],
            "fallback_count": 0,
            "escalated": False,
        }

    result = _run(
        run_chat_graph(
            {
                "session_id": "u:401:default",
                "message": {"role": "user", "content": "주문 취소해줘"},
                "client": {
                    "user_id": "401",
                    "tenant_id": "tenant-a",
                    "auth_context": {"scopes": ["chat:write"]},
                },
            },
            "trace_5",
            "req_5",
            legacy_executor=fake_legacy_executor,
        )
    )
    pending = confirm_fsm.load_pending_action("u:401:default")
    assert isinstance(pending, dict)
    protocol = pending.get("action_protocol")
    if isinstance(protocol, dict):
        protocol.setdefault("args", {})["target_user_id"] = "999"
        pending["action_protocol"] = protocol
        confirm_fsm.save_pending_action("u:401:default", pending)

    denied = _run(
        run_chat_graph(
            {
                "session_id": "u:401:default",
                "message": {"role": "user", "content": "확인 000000"},
                "client": {
                    "user_id": "401",
                    "tenant_id": "tenant-a",
                    "auth_context": {"scopes": ["chat:write"]},
                },
            },
            "trace_6",
            "req_6",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert called["count"] == 0
    assert denied.response["reason_code"] == "AUTH_FORBIDDEN"
