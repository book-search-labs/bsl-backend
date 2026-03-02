import pytest

from app.core.chat_graph.state import (
    ChatGraphStateValidationError,
    build_chat_graph_state,
    graph_state_to_legacy_session_snapshot,
    legacy_session_snapshot_to_graph_state,
    validate_chat_graph_state,
)


def test_validate_chat_graph_state_accepts_minimum_state():
    state = build_chat_graph_state(
        trace_id="trace_01",
        request_id="req_01",
        session_id="u:101:default",
        query="배송 상태 알려줘",
        user_id="101",
    )

    validated = validate_chat_graph_state(state, stage="unit_test")

    assert validated["schema_version"] == "v1"
    assert validated["state_version"] == 1
    assert validated["session_id"] == "u:101:default"
    assert validated["selection"]["last_candidates"] == []


def test_validate_chat_graph_state_rejects_missing_required_field():
    with pytest.raises(ChatGraphStateValidationError) as exc_info:
        validate_chat_graph_state({"trace_id": "trace_01"}, stage="unit_test")

    assert exc_info.value.reason_code == "CHAT_GRAPH_STATE_INVALID"
    assert "request_id" in str(exc_info.value)


def test_legacy_to_graph_mapping_carries_selection_and_pending_action():
    legacy = {
        "session_id": "u:777:default",
        "state_version": 3,
        "fallback_count": 1,
        "fallback_escalation_threshold": 3,
        "escalation_ready": False,
        "recommended_action": "RETRY",
        "recommended_message": "근거를 다시 확인해 주세요.",
        "unresolved_context": {
            "reason_code": "LLM_NO_CITATIONS",
            "reason_message": "근거가 부족합니다.",
            "next_action": "RETRY",
            "trace_id": "trace_prev",
            "request_id": "req_prev",
            "updated_at": 1760000000,
            "query_preview": "환불 조건 문의",
        },
        "selection": {
            "last_candidates": [{"doc_id": "b1", "title": "도서1"}, {"doc_id": "b2", "title": "도서2"}],
            "selected_index": 1,
            "selected_book": {"doc_id": "b2", "title": "도서2"},
        },
        "pending_action": {
            "workflow_type": "REFUND_REQUEST",
            "step": "AWAITING_CONFIRMATION",
            "order_id": 1201,
            "requires_confirmation": True,
            "risk": "high",
            "confirmation_token": "ABC123",
            "idempotencyKey": "refund-req-1201",
        },
    }

    graph_state = legacy_session_snapshot_to_graph_state(
        legacy,
        trace_id="trace_now",
        request_id="req_now",
        query="2번째 도서 환불해줘",
    )

    assert graph_state["state_version"] == 3
    assert graph_state["route"] == "FALLBACK"
    assert graph_state["reason_code"] == "LLM_NO_CITATIONS"
    assert graph_state["selection"]["selected_book"]["doc_id"] == "b2"
    assert graph_state["pending_action"]["action_type"] == "REFUND_REQUEST"
    assert graph_state["pending_action"]["state"] == "AWAITING_CONFIRMATION"
    assert graph_state["pending_action"]["payload"]["order_id"] == 1201
    assert graph_state["pending_action"]["risk_level"] == "HIGH"


def test_graph_to_legacy_mapping_synthesizes_unresolved_context_for_non_ok_reason():
    state = build_chat_graph_state(
        trace_id="trace_01",
        request_id="req_01",
        session_id="u:321:default",
        query="환불 상태 조회",
        user_id="321",
    )
    state["route"] = "FALLBACK"
    state["reason_code"] = "PROVIDER_TIMEOUT"
    state["response"] = {
        "status": "insufficient_evidence",
        "reason_code": "PROVIDER_TIMEOUT",
        "recoverable": True,
        "next_action": "RETRY",
        "answer": {"role": "assistant", "content": "잠시 후 다시 시도해 주세요."},
    }

    snapshot = graph_state_to_legacy_session_snapshot(state)

    assert snapshot["session_id"] == "u:321:default"
    assert snapshot["unresolved_context"]["reason_code"] == "PROVIDER_TIMEOUT"
    assert snapshot["recommended_action"] == "RETRY"
    assert snapshot["schema_version"] == "v1"


def test_graph_to_legacy_escalates_when_fallback_count_reaches_threshold():
    state = build_chat_graph_state(
        trace_id="trace_01",
        request_id="req_01",
        session_id="u:999:default",
        query="배송이 계속 실패해",
        user_id="999",
    )
    state["session"] = {
        "fallback_count": 4,
        "fallback_escalation_threshold": 3,
        "escalation_ready": False,
        "recommended_action": "RETRY",
        "recommended_message": "일시 오류",
        "unresolved_context": None,
    }

    snapshot = graph_state_to_legacy_session_snapshot(state)

    assert snapshot["escalation_ready"] is True
    assert snapshot["recommended_action"] == "OPEN_SUPPORT_TICKET"
