from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from app.core.cache import get_cache
from app.core.chat_graph.canary_controller import current_force_legacy_override

_CACHE = get_cache()
_ALLOWED_MODES = {"legacy", "shadow", "canary", "agent"}


@dataclass
class EngineRouteDecision:
    mode: str
    reason: str
    source: str
    force_legacy: bool


def _audit_key(session_id: str) -> str:
    return f"chat:graph:routing-audit:{session_id}"


def _global_audit_key() -> str:
    return "chat:graph:routing-audit:global"


def _audit_ttl_sec() -> int:
    return 86400


def _audit_max_entries() -> int:
    return 200


def _global_audit_max_entries() -> int:
    return 1000


def _bool_from_env(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_flag_payload() -> dict[str, Any]:
    raw = os.getenv("QS_CHAT_OPENFEATURE_FLAGS_JSON", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_flag_value(payload: dict[str, Any], key: str, context: dict[str, str]) -> Any:
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    value = defaults.get(key)

    tenants = payload.get("tenants") if isinstance(payload.get("tenants"), dict) else {}
    tenant_cfg = tenants.get(context.get("tenant_id", "")) if isinstance(tenants.get(context.get("tenant_id", "")), dict) else {}
    if key in tenant_cfg:
        value = tenant_cfg.get(key)

    users = payload.get("users") if isinstance(payload.get("users"), dict) else {}
    user_cfg = users.get(context.get("user_id", "")) if isinstance(users.get(context.get("user_id", "")), dict) else {}
    if key in user_cfg:
        value = user_cfg.get(key)

    return value


def _flag_bool(payload: dict[str, Any], key: str, context: dict[str, str], fallback: bool) -> bool:
    value = _resolve_flag_value(payload, key, context)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return fallback


def _flag_mode(payload: dict[str, Any], key: str, context: dict[str, str], fallback: str) -> str:
    value = _resolve_flag_value(payload, key, context)
    if isinstance(value, str) and value.strip().lower() in _ALLOWED_MODES:
        return value.strip().lower()
    return fallback


def _legacy_decommission_enabled(payload: dict[str, Any], context: dict[str, str]) -> bool:
    enabled = _bool_from_env("QS_CHAT_LEGACY_DECOMMISSION_ENABLED", False)
    return _flag_bool(payload, "chat.legacy.decommission.enabled", context, enabled)


def _legacy_emergency_recovery(payload: dict[str, Any], context: dict[str, str]) -> bool:
    enabled = _bool_from_env("QS_CHAT_LEGACY_EMERGENCY_RECOVERY", False)
    return _flag_bool(payload, "chat.legacy.emergency_recovery", context, enabled)


def resolve_engine_mode(
    *,
    default_mode: str,
    context: dict[str, str],
) -> EngineRouteDecision:
    override = current_force_legacy_override()
    if isinstance(override, dict):
        return EngineRouteDecision(mode="legacy", reason="auto_rollback_override", source="canary", force_legacy=True)

    payload = _load_flag_payload()

    force_legacy = _bool_from_env("QS_CHAT_FORCE_LEGACY", False)
    if not force_legacy:
        force_legacy = _flag_bool(payload, "chat.force_legacy", context, False)
    if force_legacy:
        return EngineRouteDecision(mode="legacy", reason="force_legacy", source="flag", force_legacy=True)

    langgraph_enabled = _bool_from_env("QS_CHAT_LANGGRAPH_ENABLED", True)
    langgraph_enabled = _flag_bool(payload, "chat.langgraph.enabled", context, langgraph_enabled)
    if not langgraph_enabled:
        return EngineRouteDecision(mode="legacy", reason="langgraph_disabled", source="flag", force_legacy=False)

    mode = _flag_mode(payload, "chat.engine.mode", context, fallback=default_mode)
    if mode not in _ALLOWED_MODES:
        mode = "legacy"

    high_risk = context.get("risk_band") == "high"
    allow_high_risk = _flag_bool(payload, "chat.agent.high_risk.enabled", context, False)
    if high_risk and mode in {"agent", "canary"} and not allow_high_risk:
        decision = EngineRouteDecision(mode="legacy", reason="high_risk_fallback", source="policy", force_legacy=False)
    else:
        decision = EngineRouteDecision(mode=mode, reason="ok", source="flag", force_legacy=False)

    if decision.mode == "legacy" and _legacy_decommission_enabled(payload, context):
        if _legacy_emergency_recovery(payload, context):
            return EngineRouteDecision(mode="legacy", reason="legacy_emergency_recovery", source="policy", force_legacy=True)
        return EngineRouteDecision(mode="agent", reason="legacy_decommissioned", source="policy", force_legacy=False)

    return decision


def append_routing_audit(
    session_id: str,
    *,
    trace_id: str,
    request_id: str,
    context: dict[str, str],
    decision: EngineRouteDecision,
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
            "context": context,
            "mode": decision.mode,
            "reason": decision.reason,
            "source": decision.source,
            "force_legacy": decision.force_legacy,
        }
    )
    if len(events) > _audit_max_entries():
        events = events[-_audit_max_entries():]
    _CACHE.set_json(_audit_key(session_id), {"events": events}, ttl=_audit_ttl_sec())

    global_cached = _CACHE.get_json(_global_audit_key())
    global_events: list[dict[str, Any]] = []
    if isinstance(global_cached, dict) and isinstance(global_cached.get("events"), list):
        global_events = [event for event in global_cached.get("events", []) if isinstance(event, dict)]
    global_events.append(
        {
            "ts": int(time.time()),
            "trace_id": trace_id,
            "request_id": request_id,
            "session_id": session_id,
            "context": context,
            "mode": decision.mode,
            "reason": decision.reason,
            "source": decision.source,
            "force_legacy": decision.force_legacy,
        }
    )
    if len(global_events) > _global_audit_max_entries():
        global_events = global_events[-_global_audit_max_entries():]
    _CACHE.set_json(_global_audit_key(), {"events": global_events}, ttl=_audit_ttl_sec())


def load_routing_audit(session_id: str) -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_audit_key(session_id))
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        return [event for event in cached.get("events", []) if isinstance(event, dict)]
    return []


def load_global_routing_audit(*, limit: int = 200) -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_global_audit_key())
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        rows = [event for event in cached.get("events", []) if isinstance(event, dict)]
        return rows[-max(1, int(limit)) :]
    return []


def build_legacy_mode_summary(*, limit: int = 500) -> dict[str, Any]:
    rows = load_global_routing_audit(limit=max(1, int(limit)))
    total = len(rows)
    legacy_rows = [row for row in rows if str(row.get("mode") or "") == "legacy"]
    legacy_count = len(legacy_rows)
    reason_counts: dict[str, int] = {}
    for row in legacy_rows:
        reason = str(row.get("reason") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "window_size": total,
        "legacy_count": legacy_count,
        "legacy_ratio": 0.0 if total == 0 else float(legacy_count) / float(total),
        "legacy_reason_counts": reason_counts,
        "samples": rows[-20:],
    }
