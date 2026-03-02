from __future__ import annotations

import re
from typing import Any, Mapping, TypedDict

CHAT_GRAPH_SCHEMA_VERSION = "v1"
CHAT_GRAPH_INITIAL_STATE_VERSION = 1

_ALLOWED_ROUTES = {"ASK", "OPTIONS", "CONFIRM", "EXECUTE", "ANSWER", "FALLBACK"}
_ALLOWED_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}


class ChatGraphSelection(TypedDict):
    last_candidates: list[dict[str, Any]]
    selected_index: int | None
    selected_book: dict[str, Any] | None


class ChatGraphPendingAction(TypedDict, total=False):
    action_type: str
    state: str
    payload: dict[str, Any]
    requires_confirmation: bool
    risk_level: str
    confirmation_token: str
    expires_at: int
    idempotency_key: str


class ChatGraphToolResult(TypedDict, total=False):
    status: str
    reason_code: str
    source: str
    data: dict[str, Any]


class ChatGraphResponse(TypedDict, total=False):
    status: str
    reason_code: str
    recoverable: bool
    next_action: str
    retry_after_ms: int | None
    answer: dict[str, Any]
    citations: list[str]
    sources: list[dict[str, Any]]
    fallback_count: int
    escalated: bool


class ChatGraphSessionMeta(TypedDict):
    fallback_count: int
    fallback_escalation_threshold: int
    escalation_ready: bool
    recommended_action: str
    recommended_message: str
    unresolved_context: dict[str, Any] | None


class ChatGraphState(TypedDict):
    schema_version: str
    state_version: int
    trace_id: str
    request_id: str
    session_id: str
    query: str
    user_id: str | None
    intent: str | None
    route: str | None
    reason_code: str | None
    selection: ChatGraphSelection
    pending_action: ChatGraphPendingAction | None
    tool_result: ChatGraphToolResult | None
    response: ChatGraphResponse | None
    session: ChatGraphSessionMeta


class ChatGraphStateValidationError(ValueError):
    def __init__(self, stage: str, issues: list[str]) -> None:
        self.stage = stage
        self.issues = issues
        self.reason_code = "CHAT_GRAPH_STATE_INVALID"
        super().__init__(f"{self.reason_code}@{stage}: {'; '.join(issues)}")


def build_chat_graph_state(
    *,
    trace_id: str,
    request_id: str,
    session_id: str,
    query: str,
    user_id: str | None = None,
    state_version: int = CHAT_GRAPH_INITIAL_STATE_VERSION,
) -> ChatGraphState:
    return {
        "schema_version": CHAT_GRAPH_SCHEMA_VERSION,
        "state_version": max(1, int(state_version)),
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "query": query,
        "user_id": user_id,
        "intent": None,
        "route": None,
        "reason_code": None,
        "selection": {
            "last_candidates": [],
            "selected_index": None,
            "selected_book": None,
        },
        "pending_action": None,
        "tool_result": None,
        "response": None,
        "session": {
            "fallback_count": 0,
            "fallback_escalation_threshold": 3,
            "escalation_ready": False,
            "recommended_action": "NONE",
            "recommended_message": "",
            "unresolved_context": None,
        },
    }


def validate_chat_graph_state(raw: Mapping[str, Any], *, stage: str) -> ChatGraphState:
    issues: list[str] = []
    if not isinstance(raw, Mapping):
        raise ChatGraphStateValidationError(stage, ["state must be an object"])

    schema_version = _require_str(raw, "schema_version", issues)
    state_version = _require_int(raw, "state_version", issues, minimum=1)
    trace_id = _require_str(raw, "trace_id", issues)
    request_id = _require_str(raw, "request_id", issues)
    session_id = _require_str(raw, "session_id", issues)
    query = _require_required_string(raw, "query", issues)

    user_id = _optional_str(raw.get("user_id"), "user_id", issues)
    intent = _optional_str(raw.get("intent"), "intent", issues)
    route = _optional_str(raw.get("route"), "route", issues)
    reason_code = _optional_str(raw.get("reason_code"), "reason_code", issues)

    if route is not None and route.upper() not in _ALLOWED_ROUTES:
        issues.append(f"route must be one of {_ALLOWED_ROUTES}")

    selection = _normalize_selection(raw.get("selection"), issues)
    pending_action = _normalize_pending_action(raw.get("pending_action"), issues)
    tool_result = _normalize_tool_result(raw.get("tool_result"), issues)
    response = _normalize_response(raw.get("response"), issues)
    session = _normalize_session_meta(raw.get("session"), issues)

    if schema_version and schema_version != CHAT_GRAPH_SCHEMA_VERSION:
        issues.append(f"schema_version must be {CHAT_GRAPH_SCHEMA_VERSION}")
    if session_id and not _is_valid_session_id(session_id):
        issues.append("session_id is invalid")

    if issues:
        raise ChatGraphStateValidationError(stage, issues)

    return {
        "schema_version": CHAT_GRAPH_SCHEMA_VERSION,
        "state_version": int(state_version),
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "query": query,
        "user_id": user_id,
        "intent": intent,
        "route": route.upper() if route else None,
        "reason_code": reason_code,
        "selection": selection,
        "pending_action": pending_action,
        "tool_result": tool_result,
        "response": response,
        "session": session,
    }


def legacy_session_snapshot_to_graph_state(
    legacy: Mapping[str, Any],
    *,
    trace_id: str,
    request_id: str,
    query: str = "",
) -> ChatGraphState:
    session_id = str(legacy.get("session_id") or "anon:default")
    state_version = legacy.get("state_version")
    unresolved = legacy.get("unresolved_context")
    unresolved_ctx = unresolved if isinstance(unresolved, Mapping) else None
    unresolved_reason = str(unresolved_ctx.get("reason_code") or "") if unresolved_ctx else ""
    route = "FALLBACK" if unresolved_ctx else None
    reason_code = unresolved_reason or ("OK" if not unresolved_ctx else None)

    base = build_chat_graph_state(
        trace_id=trace_id,
        request_id=request_id,
        session_id=session_id,
        query=query,
        user_id=_extract_user_id_from_session_id(session_id),
        state_version=int(state_version) if isinstance(state_version, int) and state_version > 0 else 1,
    )

    selection_input = legacy.get("selection")
    if not isinstance(selection_input, Mapping):
        selection_input = {
            "last_candidates": legacy.get("last_candidates"),
            "selected_book": legacy.get("selected_book"),
            "selected_index": legacy.get("selected_index"),
        }

    pending_input = legacy.get("pending_action")
    response_payload: dict[str, Any] | None = None
    recommended_message = str(legacy.get("recommended_message") or "")
    if recommended_message or unresolved_reason:
        response_payload = {
            "status": "insufficient_evidence" if unresolved_ctx else "ok",
            "reason_code": unresolved_reason or "OK",
            "next_action": str(legacy.get("recommended_action") or "NONE"),
            "recoverable": bool(unresolved_ctx is not None),
            "answer": {"role": "assistant", "content": recommended_message},
        }

    base.update(
        {
            "route": route,
            "reason_code": reason_code,
            "selection": _normalize_selection(selection_input, []),
            "pending_action": _normalize_pending_action(pending_input, []),
            "response": response_payload,
            "session": {
                "fallback_count": _as_non_negative_int(legacy.get("fallback_count"), default=0),
                "fallback_escalation_threshold": _as_non_negative_int(
                    legacy.get("fallback_escalation_threshold"), default=3, minimum=1
                ),
                "escalation_ready": bool(legacy.get("escalation_ready")),
                "recommended_action": str(legacy.get("recommended_action") or "NONE"),
                "recommended_message": recommended_message,
                "unresolved_context": dict(unresolved_ctx) if unresolved_ctx else None,
            },
        }
    )
    return validate_chat_graph_state(base, stage="legacy_to_graph")


def graph_state_to_legacy_session_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_chat_graph_state(state, stage="graph_to_legacy")

    session = validated.get("session") or {}
    response = validated.get("response") or {}
    session_action = str(session.get("recommended_action") or "").strip()
    if not session_action or session_action == "NONE":
        session_action = str(response.get("next_action") or "NONE")
    session_message = str(session.get("recommended_message") or "").strip()
    if not session_message:
        answer = response.get("answer")
        if isinstance(answer, Mapping):
            session_message = str(answer.get("content") or "").strip()
    unresolved_context = session.get("unresolved_context")
    unresolved = dict(unresolved_context) if isinstance(unresolved_context, Mapping) else None

    reason_code = str(validated.get("reason_code") or response.get("reason_code") or "OK")
    if unresolved is None and reason_code and reason_code != "OK":
        unresolved = {
            "reason_code": reason_code,
            "reason_message": session_message,
            "next_action": session_action or "RETRY",
            "trace_id": validated.get("trace_id"),
            "request_id": validated.get("request_id"),
            "updated_at": 0,
            "query_preview": _query_preview(str(validated.get("query") or "")),
        }

    snapshot: dict[str, Any] = {
        "session_id": validated["session_id"],
        "state_version": validated["state_version"],
        "schema_version": validated["schema_version"],
        "fallback_count": _as_non_negative_int(session.get("fallback_count"), default=0),
        "fallback_escalation_threshold": _as_non_negative_int(
            session.get("fallback_escalation_threshold"), default=3, minimum=1
        ),
        "escalation_ready": bool(session.get("escalation_ready")),
        "recommended_action": session_action or "NONE",
        "recommended_message": session_message or "현재 챗봇 세션 상태는 정상입니다.",
        "unresolved_context": unresolved,
        "selection": validated.get("selection"),
        "pending_action": validated.get("pending_action"),
        "trace_id": validated["trace_id"],
        "request_id": validated["request_id"],
    }

    threshold = int(snapshot["fallback_escalation_threshold"])
    if int(snapshot["fallback_count"]) >= threshold:
        snapshot["escalation_ready"] = True
        snapshot["recommended_action"] = "OPEN_SUPPORT_TICKET"
    return snapshot


def _normalize_selection(raw: Any, issues: list[str]) -> ChatGraphSelection:
    if raw is None:
        return {"last_candidates": [], "selected_index": None, "selected_book": None}
    if not isinstance(raw, Mapping):
        issues.append("selection must be an object")
        return {"last_candidates": [], "selected_index": None, "selected_book": None}

    last_candidates: list[dict[str, Any]] = []
    candidates = raw.get("last_candidates")
    if candidates is None:
        candidates = []
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, Mapping):
                last_candidates.append(dict(item))
            else:
                issues.append("selection.last_candidates entries must be objects")
                break
    else:
        issues.append("selection.last_candidates must be a list")

    selected_index = _optional_int(raw.get("selected_index"), "selection.selected_index", issues, minimum=0)
    selected_book_raw = raw.get("selected_book")
    selected_book = dict(selected_book_raw) if isinstance(selected_book_raw, Mapping) else None
    if selected_book_raw is not None and not isinstance(selected_book_raw, Mapping):
        issues.append("selection.selected_book must be an object or null")

    return {
        "last_candidates": last_candidates,
        "selected_index": selected_index,
        "selected_book": selected_book,
    }


def _normalize_pending_action(raw: Any, issues: list[str]) -> ChatGraphPendingAction | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        issues.append("pending_action must be an object or null")
        return None

    action_type = _optional_str(raw.get("action_type") or raw.get("workflow_type") or raw.get("type"), "pending_action.action_type", issues)
    state = _optional_str(raw.get("state") or raw.get("step"), "pending_action.state", issues)
    payload_raw = raw.get("payload")
    payload = dict(payload_raw) if isinstance(payload_raw, Mapping) else {}
    if payload_raw is not None and not isinstance(payload_raw, Mapping):
        issues.append("pending_action.payload must be an object")

    if "order_id" in raw and "order_id" not in payload:
        payload["order_id"] = raw.get("order_id")
    if "order_no" in raw and "order_no" not in payload:
        payload["order_no"] = raw.get("order_no")

    pending: ChatGraphPendingAction = {
        "action_type": action_type or "",
        "state": state or "",
        "payload": payload,
    }

    requires_confirmation = raw.get("requires_confirmation")
    if isinstance(requires_confirmation, bool):
        pending["requires_confirmation"] = requires_confirmation

    risk_level = _optional_str(raw.get("risk_level") or raw.get("risk"), "pending_action.risk_level", issues)
    if risk_level:
        normalized_risk = risk_level.upper()
        if normalized_risk not in _ALLOWED_RISK_LEVELS:
            issues.append(f"pending_action.risk_level must be one of {_ALLOWED_RISK_LEVELS}")
        else:
            pending["risk_level"] = normalized_risk

    confirmation_token = _optional_str(raw.get("confirmation_token"), "pending_action.confirmation_token", issues)
    if confirmation_token:
        pending["confirmation_token"] = confirmation_token

    expires_at = _optional_int(raw.get("expires_at"), "pending_action.expires_at", issues, minimum=0)
    if expires_at is not None:
        pending["expires_at"] = expires_at

    idempotency_key = _optional_str(
        raw.get("idempotency_key") or raw.get("idempotencyKey") or raw.get("workflow_id"),
        "pending_action.idempotency_key",
        issues,
    )
    if idempotency_key:
        pending["idempotency_key"] = idempotency_key

    return pending


def _normalize_tool_result(raw: Any, issues: list[str]) -> ChatGraphToolResult | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        issues.append("tool_result must be an object or null")
        return None

    normalized: ChatGraphToolResult = {}
    status = _optional_str(raw.get("status"), "tool_result.status", issues)
    reason_code = _optional_str(raw.get("reason_code"), "tool_result.reason_code", issues)
    source = _optional_str(raw.get("source"), "tool_result.source", issues)
    data = raw.get("data")

    if status:
        normalized["status"] = status
    if reason_code:
        normalized["reason_code"] = reason_code
    if source:
        normalized["source"] = source
    if data is not None:
        if isinstance(data, Mapping):
            normalized["data"] = dict(data)
        else:
            issues.append("tool_result.data must be an object")
    return normalized


def _normalize_response(raw: Any, issues: list[str]) -> ChatGraphResponse | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        issues.append("response must be an object or null")
        return None

    normalized: ChatGraphResponse = {}
    status = _optional_str(raw.get("status"), "response.status", issues)
    reason_code = _optional_str(raw.get("reason_code"), "response.reason_code", issues)
    next_action = _optional_str(raw.get("next_action"), "response.next_action", issues)
    recoverable = raw.get("recoverable")
    retry_after_ms = _optional_int(raw.get("retry_after_ms"), "response.retry_after_ms", issues, minimum=0)

    if status:
        normalized["status"] = status
    if reason_code:
        normalized["reason_code"] = reason_code
    if next_action:
        normalized["next_action"] = next_action
    if isinstance(recoverable, bool):
        normalized["recoverable"] = recoverable
    elif recoverable is not None:
        issues.append("response.recoverable must be a boolean")
    if retry_after_ms is not None:
        normalized["retry_after_ms"] = retry_after_ms

    answer = raw.get("answer")
    if answer is not None:
        if isinstance(answer, Mapping):
            normalized["answer"] = dict(answer)
        else:
            issues.append("response.answer must be an object")

    citations = raw.get("citations")
    if citations is not None:
        if isinstance(citations, list) and all(isinstance(item, str) for item in citations):
            normalized["citations"] = list(citations)
        else:
            issues.append("response.citations must be a list of strings")

    sources = raw.get("sources")
    if sources is not None:
        if isinstance(sources, list) and all(isinstance(item, Mapping) for item in sources):
            normalized["sources"] = [dict(item) for item in sources]
        else:
            issues.append("response.sources must be a list of objects")

    fallback_count = _optional_int(raw.get("fallback_count"), "response.fallback_count", issues, minimum=0)
    if fallback_count is not None:
        normalized["fallback_count"] = fallback_count

    escalated = raw.get("escalated")
    if isinstance(escalated, bool):
        normalized["escalated"] = escalated
    elif escalated is not None:
        issues.append("response.escalated must be a boolean")

    return normalized


def _normalize_session_meta(raw: Any, issues: list[str]) -> ChatGraphSessionMeta:
    if raw is None:
        return {
            "fallback_count": 0,
            "fallback_escalation_threshold": 3,
            "escalation_ready": False,
            "recommended_action": "NONE",
            "recommended_message": "",
            "unresolved_context": None,
        }
    if not isinstance(raw, Mapping):
        issues.append("session must be an object")
        return {
            "fallback_count": 0,
            "fallback_escalation_threshold": 3,
            "escalation_ready": False,
            "recommended_action": "NONE",
            "recommended_message": "",
            "unresolved_context": None,
        }

    unresolved_raw = raw.get("unresolved_context")
    unresolved: dict[str, Any] | None
    if unresolved_raw is None:
        unresolved = None
    elif isinstance(unresolved_raw, Mapping):
        unresolved = dict(unresolved_raw)
    else:
        unresolved = None
        issues.append("session.unresolved_context must be an object or null")

    return {
        "fallback_count": _as_non_negative_int(raw.get("fallback_count"), default=0),
        "fallback_escalation_threshold": _as_non_negative_int(raw.get("fallback_escalation_threshold"), default=3, minimum=1),
        "escalation_ready": bool(raw.get("escalation_ready")),
        "recommended_action": str(raw.get("recommended_action") or "NONE"),
        "recommended_message": str(raw.get("recommended_message") or ""),
        "unresolved_context": unresolved,
    }


def _optional_str(value: Any, field: str, issues: list[str]) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    issues.append(f"{field} must be a string or null")
    return None


def _optional_int(value: Any, field: str, issues: list[str], minimum: int = 0) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        issues.append(f"{field} must be an integer or null")
        return None
    if value < minimum:
        issues.append(f"{field} must be >= {minimum}")
        return None
    return value


def _require_str(raw: Mapping[str, Any], field: str, issues: list[str]) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{field} is required and must be a non-empty string")
        return ""
    return value.strip()


def _require_required_string(raw: Mapping[str, Any], field: str, issues: list[str]) -> str:
    value = raw.get(field)
    if not isinstance(value, str):
        issues.append(f"{field} is required and must be a string")
        return ""
    return value


def _require_int(raw: Mapping[str, Any], field: str, issues: list[str], minimum: int = 0) -> int:
    value = raw.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        issues.append(f"{field} is required and must be an integer")
        return minimum
    if value < minimum:
        issues.append(f"{field} must be >= {minimum}")
        return minimum
    return value


def _as_non_negative_int(value: Any, *, default: int, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return max(minimum, default)
    if value < minimum:
        return max(minimum, default)
    return value


def _is_valid_session_id(session_id: str) -> bool:
    if not session_id:
        return False
    if len(session_id) > 64:
        return False
    return re.fullmatch(r"^[A-Za-z0-9:_-]+$", session_id) is not None


def _extract_user_id_from_session_id(session_id: str) -> str | None:
    match = re.match(r"^u:([^:]+)(?::|$)", session_id)
    if match is None:
        return None
    user_id = match.group(1).strip()
    return user_id or None


def _query_preview(text: str, *, max_len: int = 120) -> str:
    normalized = " ".join((text or "").split()).strip()
    if len(normalized) <= max_len:
        return normalized
    return f"{normalized[: max_len - 1]}..."
