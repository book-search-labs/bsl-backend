import asyncio
import time

from app.core.cache import CacheClient
from app.core.chat_graph import confirm_fsm
from app.core.chat_graph.runtime import run_chat_graph


def _run(coro):
    return asyncio.run(coro)


def _ok_response(trace_id: str, request_id: str) -> dict:
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "ok",
        "reason_code": "OK",
        "recoverable": False,
        "next_action": "NONE",
        "retry_after_ms": None,
        "answer": {"role": "assistant", "content": "완료"},
        "sources": [],
        "citations": [],
        "fallback_count": 0,
        "escalated": False,
    }


def test_confirm_fsm_handles_mismatch_then_confirm_and_exec_success():
    confirm_fsm._CACHE = CacheClient(None)
    session_id = "u:501:default"
    pending = confirm_fsm.init_pending_action(
        session_id,
        action_type="REFUND_REQUEST",
        query="환불해줘",
        trace_id="trace_1",
        request_id="req_1",
    )

    mismatch = confirm_fsm.evaluate_confirmation(
        session_id,
        pending,
        query="확인 ABC123",
        trace_id="trace_2",
        request_id="req_2",
    )
    assert mismatch.allow_execute is False
    assert mismatch.reason_code == "CONFIRMATION_TOKEN_MISMATCH"

    confirmed = confirm_fsm.evaluate_confirmation(
        session_id,
        mismatch.pending_action,
        query=f"확인 {pending['confirmation_token']}",
        trace_id="trace_3",
        request_id="req_3",
    )
    assert confirmed.allow_execute is True
    assert confirmed.reason_code == "CONFIRMED"

    executing = confirm_fsm.mark_execution_start(
        session_id,
        confirmed.pending_action,
        trace_id="trace_4",
        request_id="req_4",
    )
    assert executing["state"] == "EXECUTING"

    executed = confirm_fsm.mark_execution_result(
        session_id,
        executing,
        trace_id="trace_5",
        request_id="req_5",
        success=True,
        final_reason_code="OK",
        final_retryable=False,
    )
    assert executed["state"] == "EXECUTED"
    assert confirm_fsm.load_pending_action(session_id) is None

    audit = confirm_fsm.load_action_audit(session_id)
    transitions = [(event["from_state"], event["to_state"]) for event in audit]
    assert ("INIT", "AWAITING_CONFIRMATION") in transitions
    assert ("AWAITING_CONFIRMATION", "CONFIRMED") in transitions
    assert ("CONFIRMED", "EXECUTING") in transitions
    assert ("EXECUTING", "EXECUTED") in transitions


def test_confirm_fsm_expires_pending_action():
    confirm_fsm._CACHE = CacheClient(None)
    session_id = "u:502:default"
    pending = confirm_fsm.init_pending_action(
        session_id,
        action_type="ORDER_CANCEL",
        query="주문 취소",
        trace_id="trace_1",
        request_id="req_1",
    )
    pending["expires_at"] = int(time.time()) - 1

    decision = confirm_fsm.evaluate_confirmation(
        session_id,
        pending,
        query=f"확인 {pending['confirmation_token']}",
        trace_id="trace_2",
        request_id="req_2",
    )

    assert decision.allow_execute is False
    assert decision.reason_code == "CONFIRMATION_EXPIRED"
    assert confirm_fsm.load_pending_action(session_id) is None


def test_runtime_confirm_interrupt_resume_flow():
    confirm_fsm._CACHE = CacheClient(None)
    called = {"count": 0}

    async def fake_legacy_executor(request, trace_id, request_id):
        called["count"] += 1
        return _ok_response(trace_id, request_id)

    session_id = "u:601:default"
    first = _run(
        run_chat_graph(
            {"session_id": session_id, "message": {"role": "user", "content": "주문 취소해줘"}},
            "trace_a",
            "req_a",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert first.response["status"] == "pending_confirmation"
    assert first.response["reason_code"] == "CONFIRMATION_REQUIRED"
    assert called["count"] == 0

    pending = confirm_fsm.load_pending_action(session_id)
    assert isinstance(pending, dict)
    token = pending["confirmation_token"]

    second = _run(
        run_chat_graph(
            {"session_id": session_id, "message": {"role": "user", "content": f"확인 {token}"}},
            "trace_b",
            "req_b",
            legacy_executor=fake_legacy_executor,
        )
    )

    assert called["count"] == 1
    assert second.response["status"] == "ok"
    assert second.response["reason_code"] == "OK"
    assert confirm_fsm.load_pending_action(session_id) is None
