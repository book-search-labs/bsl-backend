from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.core.cache import get_cache

_CACHE = get_cache()


@dataclass
class ShadowDiffResult:
    matched: bool
    diff_types: list[str]
    severity: str
    detail: dict[str, Any]


def _session_key(session_id: str) -> str:
    return f"chat:graph:shadow-diff:{session_id}"


def _global_key() -> str:
    return "chat:graph:shadow-diff:global"


def _ttl_sec() -> int:
    return 86400


def _max_entries() -> int:
    return 400


def _citations_count(payload: dict[str, Any]) -> int:
    value = payload.get("citations")
    if isinstance(value, list):
        return len(value)
    return 0


def compare_shadow_response(legacy: dict[str, Any], graph: dict[str, Any]) -> ShadowDiffResult:
    diff_types: list[str] = []
    detail: dict[str, Any] = {}

    status_legacy = str(legacy.get("status") or "")
    status_graph = str(graph.get("status") or "")
    if status_legacy != status_graph:
        diff_types.append("ROUTE_DIFF")
        detail["status"] = {"legacy": status_legacy, "graph": status_graph}

    reason_legacy = str(legacy.get("reason_code") or "")
    reason_graph = str(graph.get("reason_code") or "")
    if reason_legacy != reason_graph:
        diff_types.append("REASON_DIFF")
        detail["reason_code"] = {"legacy": reason_legacy, "graph": reason_graph}

    next_action_legacy = str(legacy.get("next_action") or "")
    next_action_graph = str(graph.get("next_action") or "")
    recoverable_legacy = bool(legacy.get("recoverable", True))
    recoverable_graph = bool(graph.get("recoverable", True))
    if next_action_legacy != next_action_graph or recoverable_legacy != recoverable_graph:
        diff_types.append("ACTION_DIFF")
        detail["action"] = {
            "next_action": {"legacy": next_action_legacy, "graph": next_action_graph},
            "recoverable": {"legacy": recoverable_legacy, "graph": recoverable_graph},
        }

    citations_legacy = _citations_count(legacy)
    citations_graph = _citations_count(graph)
    if citations_legacy != citations_graph:
        diff_types.append("CITATION_DIFF")
        detail["citations_count"] = {"legacy": citations_legacy, "graph": citations_graph}

    severity = "INFO"
    if "ACTION_DIFF" in diff_types:
        severity = "BLOCKER"
    elif "ROUTE_DIFF" in diff_types or "REASON_DIFF" in diff_types:
        severity = "WARN"
    elif "CITATION_DIFF" in diff_types:
        severity = "INFO"

    return ShadowDiffResult(
        matched=len(diff_types) == 0,
        diff_types=diff_types,
        severity=severity,
        detail=detail,
    )


def _append_event(key: str, event: dict[str, Any]) -> None:
    cached = _CACHE.get_json(key)
    events: list[dict[str, Any]] = []
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        events = [item for item in cached.get("events", []) if isinstance(item, dict)]
    events.append(event)
    if len(events) > _max_entries():
        events = events[-_max_entries():]
    _CACHE.set_json(key, {"events": events}, ttl=_ttl_sec())


def append_shadow_diff(
    *,
    session_id: str,
    trace_id: str,
    request_id: str,
    intent: str,
    topic: str,
    result: ShadowDiffResult,
) -> None:
    event = {
        "ts": int(time.time()),
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "intent": intent,
        "topic": topic,
        "matched": result.matched,
        "severity": result.severity,
        "diff_types": result.diff_types,
        "detail": result.detail,
    }
    _append_event(_session_key(session_id), event)
    _append_event(_global_key(), event)


def load_shadow_diffs(session_id: str) -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_session_key(session_id))
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        return [item for item in cached.get("events", []) if isinstance(item, dict)]
    return []


def _global_events() -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_global_key())
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        return [item for item in cached.get("events", []) if isinstance(item, dict)]
    return []


def build_shadow_summary(*, limit: int = 200) -> dict[str, Any]:
    events = _global_events()
    sliced = events[-max(1, limit) :]
    total = len(sliced)
    matched = sum(1 for event in sliced if bool(event.get("matched")))
    mismatched = total - matched

    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_intent: dict[str, int] = {}
    by_topic: dict[str, int] = {}
    for event in sliced:
        severity = str(event.get("severity") or "INFO")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        intent = str(event.get("intent") or "UNKNOWN")
        by_intent[intent] = by_intent.get(intent, 0) + 1
        topic = str(event.get("topic") or "")
        if topic:
            by_topic[topic] = by_topic.get(topic, 0) + 1
        for diff_type in event.get("diff_types") or []:
            code = str(diff_type)
            by_type[code] = by_type.get(code, 0) + 1

    blocker_count = by_severity.get("BLOCKER", 0)
    blocker_ratio = 0.0 if total == 0 else float(blocker_count) / float(total)
    mismatch_ratio = 0.0 if total == 0 else float(mismatched) / float(total)

    return {
        "window_size": total,
        "matched": matched,
        "mismatched": mismatched,
        "mismatch_ratio": mismatch_ratio,
        "blocker_ratio": blocker_ratio,
        "by_type": by_type,
        "by_severity": by_severity,
        "by_intent": by_intent,
        "by_topic": by_topic,
        "samples": sliced[-20:],
    }


def build_gate_payload(*, limit: int = 200) -> dict[str, Any]:
    summary = build_shadow_summary(limit=limit)
    blocker_ratio = float(summary.get("blocker_ratio") or 0.0)
    mismatch_ratio = float(summary.get("mismatch_ratio") or 0.0)
    gate_status = "PASS"
    if blocker_ratio > 0.02:
        gate_status = "BLOCK"
    elif mismatch_ratio > 0.1:
        gate_status = "WARN"
    return {
        "gate_status": gate_status,
        "blocker_ratio": blocker_ratio,
        "mismatch_ratio": mismatch_ratio,
        "summary": summary,
    }
