from app.core.cache import CacheClient
from app.core.chat_graph import authz_gate


def test_validate_action_protocol_requires_idempotency_for_write():
    decision = authz_gate.validate_action_protocol(
        {
            "action_type": "REFUND_REQUEST",
            "args": {"order_id": 12},
            "risk_level": "WRITE_SENSITIVE",
            "requires_confirmation": True,
            "idempotency_key": "",
        }
    )

    assert decision.allowed is False
    assert decision.reason_code == "ACTION_IDEMPOTENCY_REQUIRED"


def test_authorize_request_rejects_missing_tenant_or_context():
    request = {"client": {"user_id": "101"}}
    protocol = {
        "action_type": "ORDER_CANCEL",
        "args": {"target_user_id": "101"},
        "risk_level": "WRITE_SENSITIVE",
        "requires_confirmation": True,
        "idempotency_key": "k1",
    }

    decision = authz_gate.authorize_request(request, protocol)

    assert decision.allowed is False
    assert decision.reason_code == "AUTH_CONTEXT_MISSING"


def test_authorize_request_rejects_actor_target_mismatch():
    request = {
        "client": {
            "user_id": "101",
            "tenant_id": "tenant-a",
            "auth_context": {"scopes": ["chat:write"]},
        }
    }
    protocol = {
        "action_type": "ORDER_CANCEL",
        "args": {"target_user_id": "202"},
        "risk_level": "WRITE_SENSITIVE",
        "requires_confirmation": True,
        "idempotency_key": "k2",
    }

    decision = authz_gate.authorize_request(request, protocol)

    assert decision.allowed is False
    assert decision.reason_code == "AUTH_FORBIDDEN"


def test_authz_audit_append_and_load():
    authz_gate._CACHE = CacheClient(None)
    decision = authz_gate.AuthzDecision(
        allowed=False,
        reason_code="AUTH_FORBIDDEN",
        next_action="OPEN_SUPPORT_TICKET",
        policy_rule="auth.actor_target_mismatch",
        message="denied",
    )

    authz_gate.append_authz_audit(
        "u:101:default",
        trace_id="trace_1",
        request_id="req_1",
        actor="101",
        target="202",
        decision=decision,
    )

    rows = authz_gate.load_authz_audit("u:101:default")
    assert len(rows) == 1
    assert rows[0]["decision"] == "DENY"
    assert rows[0]["reason_code"] == "AUTH_FORBIDDEN"
