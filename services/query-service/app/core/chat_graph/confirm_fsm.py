from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from app.core.cache import get_cache

_CACHE = get_cache()

TERMINAL_STATES = {"EXECUTED", "EXPIRED", "ABORTED", "FAILED_FINAL"}


@dataclass
class ConfirmDecision:
    pending_action: dict[str, Any] | None
    reason_code: str
    allow_execute: bool
    user_message: str
    next_action: str
    retry_after_ms: int | None


def _pending_ttl_sec() -> int:
    return max(60, int(os.getenv("QS_CHAT_GRAPH_PENDING_TTL_SEC", "900")))


def _confirm_token_ttl_sec() -> int:
    return max(60, int(os.getenv("QS_CHAT_CONFIRM_TOKEN_TTL_SEC", "300")))


def _audit_ttl_sec() -> int:
    return max(600, int(os.getenv("QS_CHAT_GRAPH_AUDIT_TTL_SEC", "86400")))


def _audit_max_entries() -> int:
    return max(20, int(os.getenv("QS_CHAT_GRAPH_AUDIT_MAX_ENTRIES", "100")))


def _pending_key(session_id: str) -> str:
    return f"chat:graph:pending:{session_id}"


def _audit_key(session_id: str) -> str:
    return f"chat:graph:action-audit:{session_id}"


def _now() -> int:
    return int(time.time())


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _is_abort_message(query: str) -> bool:
    normalized = _normalize_text(query)
    return any(keyword in normalized for keyword in ("중단", "그만", "abort", "stop", "철회", "요청 취소"))


def _is_confirmation_message(query: str) -> bool:
    normalized = _normalize_text(query)
    return any(keyword in normalized for keyword in ("확인", "동의", "진행", "승인", "yes", "confirm"))


def _extract_confirmation_token(query: str) -> str | None:
    match = re.search(r"\b([A-Z0-9]{6})\b", (query or "").upper())
    if match is None:
        return None
    return match.group(1)


def _build_confirmation_token(trace_id: str, request_id: str, session_id: str) -> str:
    seed = f"{trace_id}:{request_id}:{session_id}:{time.time_ns()}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest().upper()
    return digest[:6]


def _build_idempotency_key(session_id: str, action_type: str, query: str) -> str:
    seed = f"{session_id}:{action_type}:{_normalize_text(query)}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"chat-graph:{action_type.lower()}:{digest}"


def _audit_transition(
    session_id: str,
    *,
    trace_id: str,
    request_id: str,
    action_type: str,
    from_state: str,
    to_state: str,
    reason_code: str,
    idempotency_key: str,
) -> None:
    cached = _CACHE.get_json(_audit_key(session_id))
    entries = []
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        entries = [event for event in cached["events"] if isinstance(event, dict)]
    entries.append(
        {
            "ts": _now(),
            "trace_id": trace_id,
            "request_id": request_id,
            "action_type": action_type,
            "from_state": from_state,
            "to_state": to_state,
            "reason_code": reason_code,
            "idempotency_key": idempotency_key,
        }
    )
    if len(entries) > _audit_max_entries():
        entries = entries[-_audit_max_entries():]
    _CACHE.set_json(_audit_key(session_id), {"events": entries}, ttl=_audit_ttl_sec())


def load_action_audit(session_id: str) -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_audit_key(session_id))
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        return [event for event in cached["events"] if isinstance(event, dict)]
    return []


def load_pending_action(session_id: str) -> dict[str, Any] | None:
    cached = _CACHE.get_json(_pending_key(session_id))
    if not isinstance(cached, dict):
        return None
    if cached.get("cleared") is True:
        return None
    return cached


def save_pending_action(session_id: str, pending_action: dict[str, Any]) -> None:
    ttl = _pending_ttl_sec()
    expires_at = pending_action.get("expires_at")
    if isinstance(expires_at, int):
        ttl = max(1, min(ttl, max(1, expires_at - _now())))
    _CACHE.set_json(_pending_key(session_id), pending_action, ttl=ttl)


def clear_pending_action(session_id: str) -> None:
    _CACHE.set_json(_pending_key(session_id), {"cleared": True}, ttl=1)


def init_pending_action(
    session_id: str,
    *,
    action_type: str,
    query: str,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    now = _now()
    pending = {
        "action_type": action_type,
        "state": "AWAITING_CONFIRMATION",
        "payload": {"query": query},
        "requires_confirmation": True,
        "risk_level": "HIGH",
        "confirmation_token": _build_confirmation_token(trace_id, request_id, session_id),
        "expires_at": now + _confirm_token_ttl_sec(),
        "idempotency_key": _build_idempotency_key(session_id, action_type, query),
        "created_at": now,
        "last_transition_at": now,
    }
    save_pending_action(session_id, pending)
    _audit_transition(
        session_id,
        trace_id=trace_id,
        request_id=request_id,
        action_type=action_type,
        from_state="INIT",
        to_state="AWAITING_CONFIRMATION",
        reason_code="CONFIRMATION_REQUIRED",
        idempotency_key=str(pending["idempotency_key"]),
    )
    return pending


def evaluate_confirmation(
    session_id: str,
    pending_action: dict[str, Any],
    *,
    query: str,
    trace_id: str,
    request_id: str,
    now_ts: int | None = None,
) -> ConfirmDecision:
    now = _now() if now_ts is None else int(now_ts)
    action_type = str(pending_action.get("action_type") or "UNKNOWN")
    current_state = str(pending_action.get("state") or "AWAITING_CONFIRMATION").upper()
    idempotency_key = str(pending_action.get("idempotency_key") or "")

    if current_state in TERMINAL_STATES:
        clear_pending_action(session_id)
        _audit_transition(
            session_id,
            trace_id=trace_id,
            request_id=request_id,
            action_type=action_type,
            from_state=current_state,
            to_state=current_state,
            reason_code="CONFIRMATION_REPLAYED",
            idempotency_key=idempotency_key,
        )
        return ConfirmDecision(
            pending_action=None,
            reason_code="CONFIRMATION_REPLAYED",
            allow_execute=False,
            user_message="이미 종료된 요청입니다. 다시 요청해 주세요.",
            next_action="RETRY",
            retry_after_ms=None,
        )

    expires_at = pending_action.get("expires_at")
    if isinstance(expires_at, int) and now > expires_at:
        expired = dict(pending_action)
        expired["state"] = "EXPIRED"
        expired["last_transition_at"] = now
        _audit_transition(
            session_id,
            trace_id=trace_id,
            request_id=request_id,
            action_type=action_type,
            from_state=current_state,
            to_state="EXPIRED",
            reason_code="CONFIRMATION_EXPIRED",
            idempotency_key=idempotency_key,
        )
        clear_pending_action(session_id)
        return ConfirmDecision(
            pending_action=expired,
            reason_code="CONFIRMATION_EXPIRED",
            allow_execute=False,
            user_message="확인 시간이 만료되었습니다. 요청을 다시 시작해 주세요.",
            next_action="RETRY",
            retry_after_ms=None,
        )

    if _is_abort_message(query):
        aborted = dict(pending_action)
        aborted["state"] = "ABORTED"
        aborted["last_transition_at"] = now
        _audit_transition(
            session_id,
            trace_id=trace_id,
            request_id=request_id,
            action_type=action_type,
            from_state=current_state,
            to_state="ABORTED",
            reason_code="USER_ABORTED",
            idempotency_key=idempotency_key,
        )
        clear_pending_action(session_id)
        return ConfirmDecision(
            pending_action=aborted,
            reason_code="USER_ABORTED",
            allow_execute=False,
            user_message="요청이 취소되었습니다.",
            next_action="NONE",
            retry_after_ms=None,
        )

    if not _is_confirmation_message(query):
        save_pending_action(session_id, pending_action)
        return ConfirmDecision(
            pending_action=pending_action,
            reason_code="CONFIRMATION_REQUIRED",
            allow_execute=False,
            user_message="민감 작업입니다. 확인 코드를 포함해 '확인 <코드>'로 응답해 주세요.",
            next_action="CONFIRM_ACTION",
            retry_after_ms=None,
        )

    provided_token = _extract_confirmation_token(query)
    expected_token = str(pending_action.get("confirmation_token") or "")
    if not provided_token or provided_token != expected_token:
        save_pending_action(session_id, pending_action)
        _audit_transition(
            session_id,
            trace_id=trace_id,
            request_id=request_id,
            action_type=action_type,
            from_state=current_state,
            to_state=current_state,
            reason_code="CONFIRMATION_TOKEN_MISMATCH",
            idempotency_key=idempotency_key,
        )
        return ConfirmDecision(
            pending_action=pending_action,
            reason_code="CONFIRMATION_TOKEN_MISMATCH",
            allow_execute=False,
            user_message="확인 코드가 올바르지 않습니다. 코드를 다시 확인해 주세요.",
            next_action="CONFIRM_ACTION",
            retry_after_ms=None,
        )

    confirmed = dict(pending_action)
    confirmed["state"] = "CONFIRMED"
    confirmed["confirmed_at"] = now
    confirmed["last_transition_at"] = now
    save_pending_action(session_id, confirmed)
    _audit_transition(
        session_id,
        trace_id=trace_id,
        request_id=request_id,
        action_type=action_type,
        from_state=current_state,
        to_state="CONFIRMED",
        reason_code="CONFIRMED",
        idempotency_key=idempotency_key,
    )
    return ConfirmDecision(
        pending_action=confirmed,
        reason_code="CONFIRMED",
        allow_execute=True,
        user_message="확인이 완료되었습니다. 요청을 실행합니다.",
        next_action="NONE",
        retry_after_ms=None,
    )


def mark_execution_start(
    session_id: str,
    pending_action: dict[str, Any],
    *,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    now = _now()
    updated = dict(pending_action)
    from_state = str(updated.get("state") or "CONFIRMED")
    updated["state"] = "EXECUTING"
    updated["last_transition_at"] = now
    save_pending_action(session_id, updated)
    _audit_transition(
        session_id,
        trace_id=trace_id,
        request_id=request_id,
        action_type=str(updated.get("action_type") or "UNKNOWN"),
        from_state=from_state,
        to_state="EXECUTING",
        reason_code="EXECUTING",
        idempotency_key=str(updated.get("idempotency_key") or ""),
    )
    return updated


def mark_execution_result(
    session_id: str,
    pending_action: dict[str, Any],
    *,
    trace_id: str,
    request_id: str,
    success: bool,
    final_reason_code: str,
    final_retryable: bool,
) -> dict[str, Any]:
    now = _now()
    updated = dict(pending_action)
    from_state = str(updated.get("state") or "EXECUTING")
    if success:
        updated["state"] = "EXECUTED"
        updated["executed_at"] = now
        updated["last_transition_at"] = now
        _audit_transition(
            session_id,
            trace_id=trace_id,
            request_id=request_id,
            action_type=str(updated.get("action_type") or "UNKNOWN"),
            from_state=from_state,
            to_state="EXECUTED",
            reason_code=final_reason_code,
            idempotency_key=str(updated.get("idempotency_key") or ""),
        )
        clear_pending_action(session_id)
        return updated

    to_state = "FAILED_RETRYABLE" if final_retryable else "FAILED_FINAL"
    updated["state"] = to_state
    updated["last_transition_at"] = now
    _audit_transition(
        session_id,
        trace_id=trace_id,
        request_id=request_id,
        action_type=str(updated.get("action_type") or "UNKNOWN"),
        from_state=from_state,
        to_state=to_state,
        reason_code=final_reason_code,
        idempotency_key=str(updated.get("idempotency_key") or ""),
    )
    if final_retryable:
        save_pending_action(session_id, updated)
    else:
        clear_pending_action(session_id)
    return updated
