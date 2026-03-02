from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.core.cache import get_cache

_CACHE = get_cache()

_ALLOWED_ACTION_TYPES = {
    "ORDER_CANCEL",
    "REFUND_REQUEST",
    "ADDRESS_CHANGE",
    "ORDER_UPDATE",
    "SENSITIVE_ACTION",
}
_ALLOWED_RISK_LEVELS = {"READ", "WRITE_SENSITIVE"}


@dataclass
class AuthzDecision:
    allowed: bool
    reason_code: str
    next_action: str
    policy_rule: str
    message: str


def _audit_key(session_id: str) -> str:
    return f"chat:graph:authz-audit:{session_id}"


def _audit_ttl_sec() -> int:
    return 86400


def _audit_max_entries() -> int:
    return 100


def build_action_protocol(
    *,
    action_type: str,
    args: dict[str, Any],
    idempotency_key: str,
    risk_level: str = "WRITE_SENSITIVE",
    requires_confirmation: bool = True,
) -> dict[str, Any]:
    return {
        "action_type": action_type,
        "args": args,
        "risk_level": risk_level,
        "requires_confirmation": requires_confirmation,
        "idempotency_key": idempotency_key,
    }


def validate_action_protocol(protocol: dict[str, Any] | None) -> AuthzDecision:
    if not isinstance(protocol, dict):
        return AuthzDecision(
            allowed=False,
            reason_code="ACTION_PROTOCOL_INVALID",
            next_action="OPEN_SUPPORT_TICKET",
            policy_rule="action_protocol.required",
            message="액션 실행 형식이 올바르지 않습니다.",
        )

    action_type = str(protocol.get("action_type") or "").strip().upper()
    if action_type not in _ALLOWED_ACTION_TYPES:
        return AuthzDecision(
            allowed=False,
            reason_code="ACTION_PROTOCOL_INVALID",
            next_action="OPEN_SUPPORT_TICKET",
            policy_rule="action_protocol.action_type",
            message="지원되지 않는 액션 타입입니다.",
        )

    args = protocol.get("args")
    if not isinstance(args, dict):
        return AuthzDecision(
            allowed=False,
            reason_code="ACTION_PROTOCOL_INVALID",
            next_action="PROVIDE_REQUIRED_INFO",
            policy_rule="action_protocol.args",
            message="액션 입력값이 올바르지 않습니다.",
        )

    risk_level = str(protocol.get("risk_level") or "").strip().upper()
    if risk_level not in _ALLOWED_RISK_LEVELS:
        return AuthzDecision(
            allowed=False,
            reason_code="ACTION_PROTOCOL_INVALID",
            next_action="OPEN_SUPPORT_TICKET",
            policy_rule="action_protocol.risk_level",
            message="리스크 레벨이 올바르지 않습니다.",
        )

    requires_confirmation = protocol.get("requires_confirmation")
    if not isinstance(requires_confirmation, bool):
        return AuthzDecision(
            allowed=False,
            reason_code="ACTION_PROTOCOL_INVALID",
            next_action="OPEN_SUPPORT_TICKET",
            policy_rule="action_protocol.requires_confirmation",
            message="확인 정책 형식이 올바르지 않습니다.",
        )

    idempotency_key = str(protocol.get("idempotency_key") or "").strip()
    if risk_level == "WRITE_SENSITIVE" and not idempotency_key:
        return AuthzDecision(
            allowed=False,
            reason_code="ACTION_IDEMPOTENCY_REQUIRED",
            next_action="OPEN_SUPPORT_TICKET",
            policy_rule="action_protocol.idempotency_key",
            message="민감 액션에는 멱등성 키가 필요합니다.",
        )

    return AuthzDecision(
        allowed=True,
        reason_code="OK",
        next_action="NONE",
        policy_rule="action_protocol.allow",
        message="",
    )


def authorize_request(request: dict[str, Any], protocol: dict[str, Any] | None) -> AuthzDecision:
    protocol_check = validate_action_protocol(protocol)
    if not protocol_check.allowed:
        return protocol_check

    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    user_id = client.get("user_id") if isinstance(client, dict) else None
    tenant_id = client.get("tenant_id") if isinstance(client, dict) else None
    auth_context = client.get("auth_context") if isinstance(client, dict) else None

    if not isinstance(user_id, str) or not user_id.strip():
        return AuthzDecision(
            allowed=False,
            reason_code="AUTH_REQUIRED",
            next_action="LOGIN_REQUIRED",
            policy_rule="auth.user.required",
            message="로그인이 필요합니다.",
        )

    if not isinstance(tenant_id, str) or not tenant_id.strip():
        return AuthzDecision(
            allowed=False,
            reason_code="AUTH_CONTEXT_MISSING",
            next_action="OPEN_SUPPORT_TICKET",
            policy_rule="auth.tenant.required",
            message="권한 컨텍스트가 누락되었습니다.",
        )

    if not isinstance(auth_context, dict):
        return AuthzDecision(
            allowed=False,
            reason_code="AUTH_CONTEXT_MISSING",
            next_action="OPEN_SUPPORT_TICKET",
            policy_rule="auth.context.required",
            message="권한 컨텍스트가 누락되었습니다.",
        )

    scopes = auth_context.get("scopes")
    if isinstance(scopes, list) and "chat:write" not in {str(scope) for scope in scopes}:
        return AuthzDecision(
            allowed=False,
            reason_code="AUTH_FORBIDDEN",
            next_action="OPEN_SUPPORT_TICKET",
            policy_rule="auth.scope.chat_write",
            message="민감 액션 권한이 없습니다.",
        )

    args = protocol.get("args") if isinstance(protocol, dict) else {}
    target_user_id = args.get("target_user_id") if isinstance(args, dict) else None
    if isinstance(target_user_id, str) and target_user_id.strip() and target_user_id.strip() != user_id.strip():
        return AuthzDecision(
            allowed=False,
            reason_code="AUTH_FORBIDDEN",
            next_action="OPEN_SUPPORT_TICKET",
            policy_rule="auth.actor_target_mismatch",
            message="본인 계정 요청만 처리할 수 있습니다.",
        )

    return AuthzDecision(
        allowed=True,
        reason_code="OK",
        next_action="NONE",
        policy_rule="auth.allow",
        message="",
    )


def append_authz_audit(
    session_id: str,
    *,
    trace_id: str,
    request_id: str,
    actor: str,
    target: str,
    decision: AuthzDecision,
) -> None:
    cached = _CACHE.get_json(_audit_key(session_id))
    events: list[dict[str, Any]] = []
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        events = [event for event in cached.get("events", []) if isinstance(event, dict)]

    events.append(
        {
            "ts": int(time.time()),
            "trace_id": trace_id,
            "request_id": request_id,
            "actor": actor,
            "target": target,
            "decision": "ALLOW" if decision.allowed else "DENY",
            "policy_rule": decision.policy_rule,
            "reason_code": decision.reason_code,
        }
    )
    if len(events) > _audit_max_entries():
        events = events[-_audit_max_entries():]
    _CACHE.set_json(_audit_key(session_id), {"events": events}, ttl=_audit_ttl_sec())


def load_authz_audit(session_id: str) -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_audit_key(session_id))
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        return [event for event in cached.get("events", []) if isinstance(event, dict)]
    return []
