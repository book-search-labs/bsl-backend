from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

ROUTE_ASK = "ASK"
ROUTE_OPTIONS = "OPTIONS"
ROUTE_CONFIRM = "CONFIRM"
ROUTE_EXECUTE = "EXECUTE"
ROUTE_ANSWER = "ANSWER"

_WRITE_SENSITIVE_INTENTS = {"ORDER_CANCEL", "REFUND_CREATE"}
_LOOKUP_EXECUTE_INTENTS = {
    "ORDER_LOOKUP",
    "SHIPMENT_LOOKUP",
    "REFUND_LOOKUP",
    "TICKET_CREATE",
    "TICKET_STATUS",
    "TICKET_LIST",
    "CART_RECOMMEND",
}
_ANSWER_INTENTS = {"REFUND_POLICY", "SHIPPING_POLICY", "ORDER_POLICY", "BOOK_RECOMMEND"}
_REQUIRED_SLOTS: dict[str, tuple[str, ...]] = {
    "ORDER_CANCEL": ("order_ref",),
    "REFUND_CREATE": ("order_ref",),
    "ORDER_LOOKUP": ("order_ref",),
    "SHIPMENT_LOOKUP": ("order_ref",),
    "REFUND_LOOKUP": ("order_ref",),
    "TICKET_STATUS": ("ticket_no",),
}


@dataclass(frozen=True)
class ToolUnderstanding:
    intent: str
    slots: dict[str, Any]
    standalone_query: str
    risk_level: str
    q_key: str


@dataclass(frozen=True)
class PolicyDecision:
    route: str
    reason_code: str
    policy_rule_id: str
    missing_slots: list[str]
    decision_snapshot: dict[str, Any]


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def canonical_q_key(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def required_slots(intent: str) -> tuple[str, ...]:
    return _REQUIRED_SLOTS.get(str(intent or "").upper().strip(), ())


def infer_risk_level(intent: str) -> str:
    normalized_intent = str(intent or "").upper().strip()
    if normalized_intent in _WRITE_SENSITIVE_INTENTS:
        return "WRITE_SENSITIVE"
    if normalized_intent in _LOOKUP_EXECUTE_INTENTS:
        return "READ"
    return "LOW"


def build_understanding(
    *,
    query: str,
    intent: str,
    slots: dict[str, Any] | None,
    standalone_query: str | None = None,
    risk_level: str | None = None,
    q_key: str | None = None,
) -> ToolUnderstanding:
    normalized_query = _normalize_text(query)
    normalized_intent = str(intent or "").upper().strip()
    resolved_standalone = str(standalone_query or query or "").strip()
    resolved_q_key = str(q_key or "").strip() or canonical_q_key(resolved_standalone or normalized_query)
    resolved_risk = str(risk_level or "").strip().upper() or infer_risk_level(normalized_intent)
    return ToolUnderstanding(
        intent=normalized_intent,
        slots=slots or {},
        standalone_query=resolved_standalone,
        risk_level=resolved_risk,
        q_key=resolved_q_key,
    )


def missing_slots(understanding: ToolUnderstanding) -> list[str]:
    missing: list[str] = []
    for name in required_slots(understanding.intent):
        value = understanding.slots.get(name)
        if value is None:
            missing.append(name)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(name)
            continue
        if isinstance(value, dict) and not any(bool(v) for v in value.values()):
            missing.append(name)
    return missing


def decide_route(
    understanding: ToolUnderstanding,
    *,
    has_user: bool,
    has_pending_action: bool,
    pending_state: str | None,
    is_reference_query: bool,
    has_selection_state: bool,
) -> PolicyDecision:
    normalized_pending_state = str(pending_state or "").upper().strip()
    missing = missing_slots(understanding)
    snapshot = {
        "intent": understanding.intent,
        "risk_level": understanding.risk_level,
        "missing_slots": missing,
        "has_user": has_user,
        "has_pending_action": has_pending_action,
        "pending_state": normalized_pending_state,
        "is_reference_query": is_reference_query,
        "has_selection_state": has_selection_state,
        "q_key": understanding.q_key,
    }

    if has_pending_action:
        return PolicyDecision(
            route=ROUTE_CONFIRM,
            reason_code="ROUTE:CONFIRM:PENDING_ACTION",
            policy_rule_id="PE-001-PENDING-ACTION",
            missing_slots=[],
            decision_snapshot=snapshot,
        )

    if is_reference_query and not has_selection_state:
        return PolicyDecision(
            route=ROUTE_OPTIONS,
            reason_code="ROUTE:OPTIONS:DISAMBIGUATE:BOOK",
            policy_rule_id="PE-002-BOOK-DISAMBIGUATE",
            missing_slots=[],
            decision_snapshot=snapshot,
        )

    if understanding.intent in _WRITE_SENSITIVE_INTENTS:
        if not has_user:
            return PolicyDecision(
                route=ROUTE_ASK,
                reason_code="NEED_AUTH:USER_LOGIN",
                policy_rule_id="PE-003-AUTH-REQUIRED",
                missing_slots=[],
                decision_snapshot=snapshot,
            )
        if missing:
            return PolicyDecision(
                route=ROUTE_ASK,
                reason_code=f"NEED_SLOT:{missing[0].upper()}",
                policy_rule_id="PE-004-MISSING-SLOT",
                missing_slots=missing,
                decision_snapshot=snapshot,
            )
        return PolicyDecision(
            route=ROUTE_CONFIRM,
            reason_code=f"ROUTE:CONFIRM:{understanding.intent}",
            policy_rule_id="PE-005-WRITE-CONFIRM",
            missing_slots=[],
            decision_snapshot=snapshot,
        )

    if understanding.intent in _LOOKUP_EXECUTE_INTENTS:
        if not has_user:
            return PolicyDecision(
                route=ROUTE_ASK,
                reason_code="NEED_AUTH:USER_LOGIN",
                policy_rule_id="PE-003-AUTH-REQUIRED",
                missing_slots=[],
                decision_snapshot=snapshot,
            )
        if missing and understanding.intent in {"ORDER_LOOKUP", "SHIPMENT_LOOKUP", "REFUND_LOOKUP"}:
            return PolicyDecision(
                route=ROUTE_ASK,
                reason_code=f"NEED_SLOT:{missing[0].upper()}",
                policy_rule_id="PE-004-MISSING-SLOT",
                missing_slots=missing,
                decision_snapshot=snapshot,
            )
        return PolicyDecision(
            route=ROUTE_EXECUTE,
            reason_code=f"ROUTE:EXECUTE:{understanding.intent}",
            policy_rule_id="PE-006-EXECUTE",
            missing_slots=[],
            decision_snapshot=snapshot,
        )

    if understanding.intent in _ANSWER_INTENTS:
        return PolicyDecision(
            route=ROUTE_ANSWER,
            reason_code=f"ROUTE:ANSWER:{understanding.intent}",
            policy_rule_id="PE-007-ANSWER",
            missing_slots=[],
            decision_snapshot=snapshot,
        )

    if understanding.intent == "NONE":
        return PolicyDecision(
            route=ROUTE_ANSWER,
            reason_code="ROUTE:ANSWER:NO_INTENT",
            policy_rule_id="PE-008-NO-INTENT",
            missing_slots=[],
            decision_snapshot=snapshot,
        )

    return PolicyDecision(
        route=ROUTE_OPTIONS,
        reason_code=f"ROUTE:OPTIONS:{understanding.intent or 'UNKNOWN'}",
        policy_rule_id="PE-009-FALLBACK-OPTIONS",
        missing_slots=missing,
        decision_snapshot=snapshot,
    )
