import asyncio

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
