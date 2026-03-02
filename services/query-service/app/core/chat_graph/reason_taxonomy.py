from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Mapping

from app.core.cache import get_cache
from app.core.metrics import metrics

_CACHE = get_cache()

_REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*(?::[A-Z0-9_]+)*$")
_FORBIDDEN_CODES = {"UNKNOWN", "NO_REASON"}

DEFAULT_INVALID_REASON_CODE = "CHAT_REASON_CODE_INVALID"
DEFAULT_UNSPECIFIED_REASON_CODE = "CHAT_REASON_UNSPECIFIED"

_GLOBAL_KNOWN_FAMILIES = {
    "ACTION",
    "AUTH",
    "CHAT",
    "CONFIRMATION",
    "CONFIRMED",
    "DENY",
    "EXECUTING",
    "IN",
    "INVALID",
    "LLM",
    "MISSING",
    "NO",
    "OK",
    "OUTPUT",
    "POLICY",
    "PROVIDER",
    "RAG",
    "RATE",
    "RESOURCE",
    "ROUTE",
    "TOOL",
    "UNSUPPORTED",
    "USER",
}

_GLOBAL_KNOWN_CODES = {
    "OK",
    "NO_MESSAGES",
    "IN_PROGRESS",
    "CONFIRMED",
    "EXECUTING",
    "CHAT_REASON_UNSPECIFIED",
    "CHAT_REASON_CODE_INVALID",
}

_SOURCE_ALLOWED_FAMILIES: dict[str, set[str]] = {
    "load_state": {"OK", "CHAT"},
    "understand": {"OK", "CHAT"},
    "policy_decide": {"OK", "NO", "CONFIRMATION", "INVALID", "ROUTE", "CHAT"},
    "authz_gate": {"OK", "AUTH", "ACTION", "DENY", "INVALID", "CHAT"},
    "execute": {
        "OK",
        "ACTION",
        "AUTH",
        "CHAT",
        "CONFIRMATION",
        "IN",
        "INVALID",
        "LLM",
        "MISSING",
        "OUTPUT",
        "PROVIDER",
        "RAG",
        "RATE",
        "RESOURCE",
        "TOOL",
        "UNSUPPORTED",
        "USER",
    },
    "compose": {"OK", "CHAT", "OUTPUT"},
    "verify": {"OK", "CHAT", "OUTPUT", "RAG", "LLM", "PROVIDER"},
    "persist": _GLOBAL_KNOWN_FAMILIES,
    "response": _GLOBAL_KNOWN_FAMILIES,
    "error_handler": _GLOBAL_KNOWN_FAMILIES,
}

_SOURCE_ALLOWED_CODES: dict[str, set[str]] = {
    "policy_decide": {"NO_MESSAGES", "CONFIRMATION_REQUIRED"},
    "authz_gate": {"ACTION_PROTOCOL_INVALID", "ACTION_IDEMPOTENCY_REQUIRED"},
    "execute": {"IN_PROGRESS"},
    "verify": {"OUTPUT_GUARD_EMPTY_ANSWER"},
}


@dataclass(frozen=True)
class ReasonCodeAssessment:
    raw_reason_code: str
    normalized_reason_code: str
    source: str
    family: str
    lane: str
    valid: bool
    invalid: bool
    unknown: bool
    source_policy_violation: bool


def _session_key(session_id: str) -> str:
    return f"chat:graph:reason-taxonomy:{session_id}"


def _global_key() -> str:
    return "chat:graph:reason-taxonomy:global"


def _stats_key() -> str:
    return "chat:graph:reason-taxonomy:stats"


def _ttl_sec() -> int:
    return 86400


def _max_entries() -> int:
    return 500


def _extract_family(code: str) -> str:
    normalized = str(code or "").strip().upper()
    if not normalized:
        return "CHAT"
    pivot = normalized.split(":", 1)[0]
    if "_" in pivot:
        return pivot.split("_", 1)[0]
    return pivot


def _resolve_lane(family: str) -> str:
    if family in {"NO", "CONFIRMATION", "ROUTE"}:
        return "ROUTE"
    if family in {"PROVIDER", "TOOL"}:
        return "TOOL_FAIL"
    if family in {"AUTH", "ACTION", "DENY", "INVALID", "USER", "UNSUPPORTED"}:
        return "DENY_EXECUTE"
    if family in {"OUTPUT", "LLM", "RAG"}:
        return "ANSWER_GUARD"
    if family in {"CHAT"}:
        return "SYSTEM"
    return "GENERAL"


def _normalize_source(source: str) -> str:
    value = str(source or "").strip().lower()
    return value or "response"


def assess_reason_code(reason_code: Any, *, source: str) -> ReasonCodeAssessment:
    raw = str(reason_code or "").strip()
    normalized = raw.upper()
    source_key = _normalize_source(source)
    family = _extract_family(normalized)
    lane = _resolve_lane(family)

    invalid = False
    unknown = False
    source_violation = False

    if not normalized:
        invalid = True
        normalized = DEFAULT_INVALID_REASON_CODE
        family = _extract_family(normalized)
        lane = _resolve_lane(family)
    elif normalized in _FORBIDDEN_CODES:
        invalid = True
        normalized = DEFAULT_INVALID_REASON_CODE
        family = _extract_family(normalized)
        lane = _resolve_lane(family)
    elif _REASON_CODE_PATTERN.match(raw) is None:
        invalid = True
        normalized = DEFAULT_INVALID_REASON_CODE
        family = _extract_family(normalized)
        lane = _resolve_lane(family)

    if not invalid:
        known = normalized in _GLOBAL_KNOWN_CODES or family in _GLOBAL_KNOWN_FAMILIES
        allowed_families = _SOURCE_ALLOWED_FAMILIES.get(source_key, _GLOBAL_KNOWN_FAMILIES)
        allowed_codes = _SOURCE_ALLOWED_CODES.get(source_key, set())
        source_violation = normalized not in allowed_codes and family not in allowed_families
        unknown = (not known) or source_violation

    return ReasonCodeAssessment(
        raw_reason_code=raw,
        normalized_reason_code=normalized,
        source=source_key,
        family=family,
        lane=lane,
        valid=not invalid,
        invalid=invalid,
        unknown=unknown,
        source_policy_violation=source_violation,
    )


def normalize_reason_code(
    reason_code: Any,
    *,
    source: str,
    fallback: str = DEFAULT_INVALID_REASON_CODE,
    sanitize_unknown: bool = False,
) -> str:
    assessment = assess_reason_code(reason_code, source=source)
    if assessment.invalid:
        fallback_assessment = assess_reason_code(fallback, source=source)
        return fallback_assessment.normalized_reason_code
    if assessment.unknown and sanitize_unknown:
        fallback_assessment = assess_reason_code(DEFAULT_UNSPECIFIED_REASON_CODE, source=source)
        return fallback_assessment.normalized_reason_code
    return assessment.normalized_reason_code


def _append_event(key: str, event: dict[str, Any]) -> None:
    cached = _CACHE.get_json(key)
    events: list[dict[str, Any]] = []
    if isinstance(cached, Mapping) and isinstance(cached.get("events"), list):
        events = [item for item in cached.get("events", []) if isinstance(item, Mapping)]
    events.append(dict(event))
    if len(events) > _max_entries():
        events = events[-_max_entries() :]
    _CACHE.set_json(key, {"events": events}, ttl=_ttl_sec())


def _inc_stats(source: str, *, invalid: bool, unknown: bool) -> None:
    cached = _CACHE.get_json(_stats_key())
    payload: dict[str, Any] = dict(cached) if isinstance(cached, Mapping) else {}
    per_source = payload.get(source) if isinstance(payload.get(source), Mapping) else {}
    total = int(per_source.get("total") or 0) + 1
    invalid_total = int(per_source.get("invalid_total") or 0) + (1 if invalid else 0)
    unknown_total = int(per_source.get("unknown_total") or 0) + (1 if unknown else 0)
    payload[source] = {
        "total": total,
        "invalid_total": invalid_total,
        "unknown_total": unknown_total,
        "invalid_ratio": 0.0 if total == 0 else float(invalid_total) / float(total),
        "unknown_ratio": 0.0 if total == 0 else float(unknown_total) / float(total),
    }
    _CACHE.set_json(_stats_key(), payload, ttl=_ttl_sec())

    metrics.set("chat_reason_code_invalid_ratio", {"source": source}, payload[source]["invalid_ratio"])
    metrics.set("chat_reason_code_unknown_ratio", {"source": source}, payload[source]["unknown_ratio"])


def record_reason_code_event(
    *,
    session_id: str,
    trace_id: str,
    request_id: str,
    source: str,
    reason_code: Any,
) -> ReasonCodeAssessment:
    assessment = assess_reason_code(reason_code, source=source)

    metrics.inc(
        "chat_reason_code_total",
        {"source": assessment.source, "reason_code": assessment.normalized_reason_code},
    )
    metrics.inc(
        "chat_reason_code_lane_total",
        {"source": assessment.source, "lane": assessment.lane},
    )
    if assessment.invalid:
        metrics.inc("chat_reason_code_invalid_total", {"source": assessment.source})
    if assessment.unknown:
        metrics.inc("chat_reason_code_unknown_total", {"source": assessment.source})

    _inc_stats(
        assessment.source,
        invalid=assessment.invalid,
        unknown=assessment.unknown,
    )

    event = {
        "ts": int(time.time()),
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "source": assessment.source,
        "lane": assessment.lane,
        "family": assessment.family,
        "raw_reason_code": assessment.raw_reason_code,
        "reason_code": assessment.normalized_reason_code,
        "valid": assessment.valid,
        "invalid": assessment.invalid,
        "unknown": assessment.unknown,
        "source_policy_violation": assessment.source_policy_violation,
    }
    _append_event(_session_key(session_id), event)
    _append_event(_global_key(), event)
    return assessment


def load_reason_code_audit(session_id: str) -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_session_key(session_id))
    if isinstance(cached, Mapping) and isinstance(cached.get("events"), list):
        return [dict(item) for item in cached.get("events", []) if isinstance(item, Mapping)]
    return []


def _global_events() -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_global_key())
    if isinstance(cached, Mapping) and isinstance(cached.get("events"), list):
        return [dict(item) for item in cached.get("events", []) if isinstance(item, Mapping)]
    return []


def build_reason_code_summary(*, limit: int = 200) -> dict[str, Any]:
    events = _global_events()
    sliced = events[-max(1, int(limit)) :]
    total = len(sliced)
    invalid_total = sum(1 for item in sliced if bool(item.get("invalid")))
    unknown_total = sum(1 for item in sliced if bool(item.get("unknown")))

    by_source: dict[str, dict[str, float | int]] = {}
    by_lane: dict[str, int] = {}
    by_reason_code: dict[str, int] = {}
    for item in sliced:
        source = str(item.get("source") or "response")
        lane = str(item.get("lane") or "GENERAL")
        reason_code = str(item.get("reason_code") or DEFAULT_INVALID_REASON_CODE)
        src_row = by_source.get(source)
        if src_row is None:
            src_row = {"total": 0, "invalid_total": 0, "unknown_total": 0, "invalid_ratio": 0.0, "unknown_ratio": 0.0}
            by_source[source] = src_row
        src_row["total"] = int(src_row["total"]) + 1
        if bool(item.get("invalid")):
            src_row["invalid_total"] = int(src_row["invalid_total"]) + 1
        if bool(item.get("unknown")):
            src_row["unknown_total"] = int(src_row["unknown_total"]) + 1
        src_total = int(src_row["total"])
        src_row["invalid_ratio"] = 0.0 if src_total == 0 else float(src_row["invalid_total"]) / float(src_total)
        src_row["unknown_ratio"] = 0.0 if src_total == 0 else float(src_row["unknown_total"]) / float(src_total)
        by_lane[lane] = by_lane.get(lane, 0) + 1
        by_reason_code[reason_code] = by_reason_code.get(reason_code, 0) + 1

    invalid_ratio = 0.0 if total == 0 else float(invalid_total) / float(total)
    unknown_ratio = 0.0 if total == 0 else float(unknown_total) / float(total)
    return {
        "window_size": total,
        "invalid_total": invalid_total,
        "unknown_total": unknown_total,
        "invalid_ratio": invalid_ratio,
        "unknown_ratio": unknown_ratio,
        "by_source": by_source,
        "by_lane": by_lane,
        "by_reason_code": by_reason_code,
        "samples": sliced[-20:],
    }
