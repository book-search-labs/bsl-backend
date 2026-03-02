from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

from app.core.cache import get_cache
from app.core.metrics import metrics

_CACHE = get_cache()

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\-\s]{7,}\d)(?!\d)")
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")


@dataclass(frozen=True)
class TraceDecision:
    enabled: bool
    sampled: bool
    reason: str
    sample_rate: float


@dataclass(frozen=True)
class TraceEmitResult:
    exported: bool
    status: str
    event_id: str
    run_url: str | None


def _session_key(session_id: str) -> str:
    return f"chat:graph:langsmith-audit:{session_id}"


def _global_key() -> str:
    return "chat:graph:langsmith-audit:global"


def _ttl_sec() -> int:
    return 86400


def _max_entries() -> int:
    return 400


def _bool_env(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _redaction_mode() -> str:
    mode = str(os.getenv("QS_CHAT_LANGSMITH_REDACTION_MODE", "hash_summary")).strip().lower()
    if mode in {"masked_raw", "hash_summary"}:
        return mode
    return "hash_summary"


def _sample_rate_default() -> float:
    return min(1.0, max(0.0, float(os.getenv("QS_CHAT_LANGSMITH_SAMPLE_RATE", "0.1"))))


def _sample_overrides() -> dict[str, Any]:
    raw = os.getenv("QS_CHAT_LANGSMITH_SAMPLE_OVERRIDES_JSON", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_sample_rate(context: Mapping[str, str]) -> float:
    rate = _sample_rate_default()
    payload = _sample_overrides()
    tenant_id = str(context.get("tenant_id") or "")
    channel = str(context.get("channel") or "")
    if isinstance(payload.get("tenants"), Mapping) and tenant_id:
        tenant_raw = payload.get("tenants")
        tenant_cfg = tenant_raw.get(tenant_id) if isinstance(tenant_raw, Mapping) else None
        if isinstance(tenant_cfg, (int, float)):
            rate = float(tenant_cfg)
    if isinstance(payload.get("channels"), Mapping) and channel:
        channel_raw = payload.get("channels")
        channel_cfg = channel_raw.get(channel) if isinstance(channel_raw, Mapping) else None
        if isinstance(channel_cfg, (int, float)):
            rate = float(channel_cfg)
    return min(1.0, max(0.0, rate))


def _deterministic_bucket(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    value = int(digest, 16)
    return float(value) / float(0xFFFFFFFF)


def resolve_trace_decision(
    *,
    trace_id: str,
    session_id: str,
    context: Mapping[str, str],
) -> TraceDecision:
    if _bool_env("QS_CHAT_LANGSMITH_KILL_SWITCH", False):
        decision = TraceDecision(enabled=False, sampled=False, reason="kill_switch", sample_rate=0.0)
        _record_decision_metric(decision)
        return decision

    enabled = _bool_env("QS_CHAT_LANGSMITH_ENABLED", False)
    if not enabled:
        decision = TraceDecision(enabled=False, sampled=False, reason="disabled", sample_rate=0.0)
        _record_decision_metric(decision)
        return decision

    rate = _resolve_sample_rate(context)
    if rate <= 0.0:
        decision = TraceDecision(enabled=True, sampled=False, reason="sample_rate_zero", sample_rate=rate)
        _record_decision_metric(decision)
        return decision

    if rate >= 1.0:
        decision = TraceDecision(enabled=True, sampled=True, reason="sample_all", sample_rate=rate)
        _record_decision_metric(decision)
        return decision

    bucket = _deterministic_bucket(f"{trace_id}:{session_id}:{context.get('tenant_id','')}:{context.get('channel','')}")
    sampled = bucket < rate
    reason = "sampled" if sampled else "sampled_out"
    decision = TraceDecision(enabled=True, sampled=sampled, reason=reason, sample_rate=rate)
    _record_decision_metric(decision)
    return decision


def _record_decision_metric(decision: TraceDecision) -> None:
    metrics.inc(
        "chat_langsmith_trace_decision_total",
        {
            "enabled": "true" if decision.enabled else "false",
            "sampled": "true" if decision.sampled else "false",
            "reason": decision.reason,
        },
    )


def _redact_text(value: str, mode: str) -> str | dict[str, Any]:
    masked = _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    masked = _PHONE_RE.sub("[REDACTED_PHONE]", masked)
    masked = _CARD_RE.sub("[REDACTED_CARD]", masked)
    masked = _ZIP_RE.sub("[REDACTED_ZIP]", masked)
    if mode == "masked_raw":
        return masked
    return {
        "hash": hashlib.sha256(masked.encode("utf-8")).hexdigest()[:16],
        "summary": masked[:96],
        "length": len(value),
    }


_SENSITIVE_KEYS = {
    "session_id",
    "user_id",
    "query",
    "message",
    "content",
    "answer",
    "body",
    "address",
    "email",
    "phone",
    "name",
}


def redact_payload(payload: Any, *, mode: str | None = None, field_name: str | None = None) -> Any:
    resolved_mode = mode or _redaction_mode()
    if isinstance(payload, Mapping):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            out[str(key)] = redact_payload(value, mode=resolved_mode, field_name=str(key))
        return out
    if isinstance(payload, list):
        return [redact_payload(item, mode=resolved_mode, field_name=field_name) for item in payload]
    if isinstance(payload, str) and str(field_name or "").lower() in _SENSITIVE_KEYS:
        return _redact_text(payload, resolved_mode)
    return payload


def _endpoint() -> str:
    raw = os.getenv("QS_CHAT_LANGSMITH_ENDPOINT", "https://api.smith.langchain.com/runs").strip()
    if raw.endswith("/runs"):
        return raw
    return raw.rstrip("/") + "/runs"


def _request_timeout_sec() -> float:
    return min(2.0, max(0.05, float(os.getenv("QS_CHAT_LANGSMITH_TIMEOUT_SEC", "0.2"))))


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = os.getenv("QS_CHAT_LANGSMITH_API_KEY", "").strip()
    if key:
        headers["x-api-key"] = key
    return headers


def _project_name() -> str:
    return str(os.getenv("QS_CHAT_LANGSMITH_PROJECT", "bsl-query-chat-graph")).strip()


def _event_name(event_type: str, node: str | None) -> str:
    if node:
        return f"chat_graph.{event_type}.{node}"
    return f"chat_graph.{event_type}"


def _append_event(key: str, event: dict[str, Any]) -> None:
    cached = _CACHE.get_json(key)
    rows: list[dict[str, Any]] = []
    if isinstance(cached, Mapping) and isinstance(cached.get("events"), list):
        rows = [dict(item) for item in cached.get("events", []) if isinstance(item, Mapping)]
    rows.append(event)
    if len(rows) > _max_entries():
        rows = rows[-_max_entries() :]
    _CACHE.set_json(key, {"events": rows}, ttl=_ttl_sec())


def load_trace_audit(session_id: str) -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_session_key(session_id))
    if isinstance(cached, Mapping) and isinstance(cached.get("events"), list):
        return [dict(item) for item in cached.get("events", []) if isinstance(item, Mapping)]
    return []


async def emit_trace_event(
    *,
    decision: TraceDecision,
    run_id: str,
    trace_id: str,
    request_id: str,
    session_id: str,
    event_type: str,
    node: str | None,
    metadata: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> TraceEmitResult:
    event_id = f"{run_id}:{event_type}:{node or 'run'}:{request_id}"
    redacted_metadata = redact_payload(dict(metadata))
    redacted_payload = redact_payload(dict(payload))

    base_event = {
        "ts": int(time.time()),
        "event_id": event_id,
        "event_type": event_type,
        "node": node,
        "run_id": run_id,
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "decision": {
            "enabled": decision.enabled,
            "sampled": decision.sampled,
            "reason": decision.reason,
            "sample_rate": decision.sample_rate,
        },
        "metadata": redacted_metadata,
        "payload": redacted_payload,
    }

    if not decision.enabled:
        event = dict(base_event)
        event["status"] = "skipped_disabled"
        _append_event(_session_key(session_id), event)
        _append_event(_global_key(), event)
        metrics.inc("chat_langsmith_trace_event_total", {"event": event_type, "status": "skipped_disabled"})
        return TraceEmitResult(exported=False, status="skipped_disabled", event_id=event_id, run_url=None)

    if not decision.sampled:
        event = dict(base_event)
        event["status"] = "skipped_sampled_out"
        _append_event(_session_key(session_id), event)
        _append_event(_global_key(), event)
        metrics.inc("chat_langsmith_trace_event_total", {"event": event_type, "status": "skipped_sampled_out"})
        return TraceEmitResult(exported=False, status="skipped_sampled_out", event_id=event_id, run_url=None)

    body = {
        "id": event_id,
        "name": _event_name(event_type, node),
        "run_type": "chain",
        "project_name": _project_name(),
        "trace_id": trace_id,
        "session_name": session_id,
        "inputs": {"payload": redacted_payload},
        "outputs": {"metadata": redacted_metadata},
        "extra": {
            "metadata": {
                "trace_id": trace_id,
                "request_id": request_id,
                "run_id": run_id,
                "event_type": event_type,
                "node": node,
            }
        },
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
    }

    start = time.time()
    status = "ok"
    run_url: str | None = None
    try:
        async with httpx.AsyncClient(timeout=_request_timeout_sec()) as client:
            response = await client.post(_endpoint(), headers=_headers(), json=body)
        if response.status_code >= 400:
            status = f"http_{response.status_code}"
        else:
            parsed = {}
            try:
                parsed = response.json() if response.content else {}
            except Exception:
                parsed = {}
            run_ref = str(parsed.get("id") or event_id)
            run_url = f"{_endpoint().rsplit('/runs', 1)[0]}/runs/{run_ref}"
    except Exception:
        status = "export_error"
    elapsed_ms = int((time.time() - start) * 1000)
    metrics.inc("chat_langsmith_trace_export_latency_ms", value=max(1, elapsed_ms))
    metrics.inc("chat_langsmith_trace_event_total", {"event": event_type, "status": status})

    event = dict(base_event)
    event["status"] = status
    event["run_url"] = run_url
    _append_event(_session_key(session_id), event)
    _append_event(_global_key(), event)
    return TraceEmitResult(exported=status == "ok", status=status, event_id=event_id, run_url=run_url)
