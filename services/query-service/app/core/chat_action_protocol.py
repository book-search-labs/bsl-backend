from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

WRITE_SENSITIVE = "WRITE_SENSITIVE"

_ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "ORDER_CANCEL": {
        "risk_level": WRITE_SENSITIVE,
        "requires_confirmation": True,
        "required_args": ("order_id", "order_no"),
    },
    "REFUND_CREATE": {
        "risk_level": WRITE_SENSITIVE,
        "requires_confirmation": True,
        "required_args": ("order_id", "order_no"),
    },
}


@dataclass(frozen=True)
class ActionValidationResult:
    ok: bool
    reason_code: str
    message: str


def registered_actions() -> tuple[str, ...]:
    return tuple(sorted(_ACTION_SCHEMAS.keys()))


def action_schema(action_type: str) -> dict[str, Any] | None:
    normalized = str(action_type or "").upper().strip()
    schema = _ACTION_SCHEMAS.get(normalized)
    if not isinstance(schema, dict):
        return None
    return dict(schema)


def build_action_draft(
    *,
    action_type: str,
    args: dict[str, Any],
    conversation_id: str,
    user_id: str,
    tenant_id: str,
    trace_id: str,
    request_id: str,
    confirm_ttl_sec: int,
    dry_run: bool = False,
    compensation_hint: str | None = None,
) -> dict[str, Any]:
    normalized_action = str(action_type or "").upper().strip()
    schema = action_schema(normalized_action) or {}
    expires_at = int(time.time()) + max(1, int(confirm_ttl_sec))
    idempotency_key = f"chat:{normalized_action.lower()}:{conversation_id}:{request_id}"
    return {
        "action_type": normalized_action,
        "args": args,
        "risk_level": str(schema.get("risk_level") or "LOW"),
        "requires_confirmation": bool(schema.get("requires_confirmation", False)),
        "idempotency_key": idempotency_key,
        "expires_at": expires_at,
        "dry_run": bool(dry_run),
        "compensation_hint": str(compensation_hint or "").strip() or None,
        "audit_fields": {
            "actor_user_id": str(user_id or "").strip(),
            "tenant_id": str(tenant_id or "").strip(),
            "conversation_id": str(conversation_id or "").strip(),
            "trace_id": str(trace_id or "").strip(),
            "request_id": str(request_id or "").strip(),
        },
    }


def validate_action_draft(action_draft: Any) -> ActionValidationResult:
    if not isinstance(action_draft, dict):
        return ActionValidationResult(False, "BAD_ACTION_SCHEMA", "action_draft must be an object")

    action_type = str(action_draft.get("action_type") or "").upper().strip()
    schema = action_schema(action_type)
    if schema is None:
        return ActionValidationResult(False, "UNKNOWN_ACTION_TYPE", "unsupported action type")

    args = action_draft.get("args")
    if not isinstance(args, dict):
        return ActionValidationResult(False, "BAD_ACTION_SCHEMA", "args must be an object")
    for required_name in schema.get("required_args", ()):
        value = args.get(required_name)
        if required_name == "order_id":
            try:
                numeric = int(value)
            except Exception:
                numeric = 0
            if numeric <= 0:
                return ActionValidationResult(False, "BAD_ACTION_SCHEMA", "order_id must be positive integer")
            continue
        if not isinstance(value, str) or not value.strip():
            return ActionValidationResult(False, "BAD_ACTION_SCHEMA", f"{required_name} is required")

    risk_level = str(action_draft.get("risk_level") or "").upper().strip()
    if risk_level != str(schema.get("risk_level") or ""):
        return ActionValidationResult(False, "BAD_ACTION_SCHEMA", "risk_level mismatch")

    requires_confirmation = bool(action_draft.get("requires_confirmation"))
    if requires_confirmation != bool(schema.get("requires_confirmation")):
        return ActionValidationResult(False, "BAD_ACTION_SCHEMA", "requires_confirmation mismatch")

    idempotency_key = str(action_draft.get("idempotency_key") or "").strip()
    if risk_level == WRITE_SENSITIVE and not idempotency_key:
        return ActionValidationResult(False, "IDEMPOTENCY_REQUIRED", "idempotency_key is required")

    expires_at_raw = action_draft.get("expires_at")
    try:
        expires_at = int(expires_at_raw)
    except Exception:
        expires_at = 0
    if expires_at <= 0:
        return ActionValidationResult(False, "BAD_ACTION_SCHEMA", "expires_at must be positive epoch second")

    dry_run = action_draft.get("dry_run")
    if dry_run is not None and not isinstance(dry_run, bool):
        return ActionValidationResult(False, "BAD_ACTION_SCHEMA", "dry_run must be boolean")

    compensation_hint = action_draft.get("compensation_hint")
    if compensation_hint is not None and not isinstance(compensation_hint, str):
        return ActionValidationResult(False, "BAD_ACTION_SCHEMA", "compensation_hint must be string")

    audit_fields = action_draft.get("audit_fields")
    if not isinstance(audit_fields, dict):
        return ActionValidationResult(False, "BAD_ACTION_SCHEMA", "audit_fields must be an object")
    required_audit_fields = ("actor_user_id", "tenant_id", "conversation_id", "trace_id", "request_id")
    for field_name in required_audit_fields:
        value = audit_fields.get(field_name)
        if not isinstance(value, str) or not value.strip():
            return ActionValidationResult(False, "BAD_ACTION_SCHEMA", f"{field_name} is required")

    return ActionValidationResult(True, "OK", "valid action draft")

