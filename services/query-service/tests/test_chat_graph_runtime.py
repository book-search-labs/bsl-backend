import asyncio

from app.core.cache import CacheClient
from app.core.chat_graph import authz_gate, confirm_fsm
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
