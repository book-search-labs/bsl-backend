from app.core.chat_action_protocol import build_action_draft
from app.core.chat_action_protocol import validate_action_draft


def test_action_protocol_build_and_validate_order_cancel():
    draft = build_action_draft(
        action_type="ORDER_CANCEL",
        args={"order_id": 12, "order_no": "ORD202602220001"},
        conversation_id="sess-1",
        user_id="1",
        tenant_id="books",
        trace_id="trace-1",
        request_id="req-1",
        confirm_ttl_sec=300,
        dry_run=False,
        compensation_hint="open_support_ticket",
    )

    result = validate_action_draft(draft)

    assert result.ok is True
    assert result.reason_code == "OK"
    assert draft["risk_level"] == "WRITE_SENSITIVE"
    assert draft["requires_confirmation"] is True
    assert draft["idempotency_key"].startswith("chat:order_cancel:")


def test_action_protocol_rejects_unknown_action_type():
    result = validate_action_draft(
        {
            "action_type": "UNKNOWN_ACTION",
            "args": {},
            "risk_level": "LOW",
            "requires_confirmation": False,
            "idempotency_key": "x",
            "expires_at": 1,
            "audit_fields": {"actor_user_id": "1", "tenant_id": "books", "conversation_id": "sess", "trace_id": "t", "request_id": "r"},
        }
    )

    assert result.ok is False
    assert result.reason_code == "UNKNOWN_ACTION_TYPE"


def test_action_protocol_rejects_missing_idempotency_for_write():
    draft = build_action_draft(
        action_type="REFUND_CREATE",
        args={"order_id": 12, "order_no": "ORD202602220001"},
        conversation_id="sess-2",
        user_id="1",
        tenant_id="books",
        trace_id="trace-2",
        request_id="req-2",
        confirm_ttl_sec=300,
    )
    draft["idempotency_key"] = ""

    result = validate_action_draft(draft)

    assert result.ok is False
    assert result.reason_code == "IDEMPOTENCY_REQUIRED"


def test_action_protocol_rejects_invalid_args():
    draft = build_action_draft(
        action_type="REFUND_CREATE",
        args={"order_id": 0, "order_no": ""},
        conversation_id="sess-3",
        user_id="1",
        tenant_id="books",
        trace_id="trace-3",
        request_id="req-3",
        confirm_ttl_sec=300,
    )

    result = validate_action_draft(draft)

    assert result.ok is False
    assert result.reason_code == "BAD_ACTION_SCHEMA"


def test_action_protocol_rejects_missing_audit_field():
    draft = build_action_draft(
        action_type="ORDER_CANCEL",
        args={"order_id": 12, "order_no": "ORD202602220001"},
        conversation_id="sess-4",
        user_id="1",
        tenant_id="books",
        trace_id="trace-4",
        request_id="req-4",
        confirm_ttl_sec=300,
    )
    draft["audit_fields"]["tenant_id"] = ""

    result = validate_action_draft(draft)

    assert result.ok is False
    assert result.reason_code == "BAD_ACTION_SCHEMA"
