from __future__ import annotations

from typing import Any, Mapping

from app.core.cache import get_cache
from app.core.metrics import metrics

_CACHE = get_cache()

_COMMERCE_TOKENS = ("ORDER", "SHIPPING", "REFUND", "RETURN", "PAYMENT", "CANCEL")
_POLICY_TOKENS = ("POLICY", "FAQ", "GUIDE", "TERMS")


def _global_key() -> str:
    return "chat:graph:launch-metrics:global"


def _ttl_sec() -> int:
    return 86400


def _normalize_intent(intent: Any) -> str:
    text = str(intent or "").strip().upper()
    return text or "UNKNOWN"


def _resolve_domain(intent: str) -> str:
    normalized = _normalize_intent(intent)
    if any(token in normalized for token in _COMMERCE_TOKENS):
        return "commerce"
    if any(token in normalized for token in _POLICY_TOKENS):
        return "policy"
    if normalized in {"BOOK_SEARCH", "BOOK_RECOMMEND", "BOOK_LOOKUP"}:
        return "catalog"
    return "general"


def _is_completed(status: Any, next_action: Any) -> bool:
    normalized_status = str(status or "").strip().lower()
    normalized_action = str(next_action or "").strip().upper()
    return normalized_status == "ok" and normalized_action in {"", "NONE"}


def _is_insufficient(status: Any) -> bool:
    return str(status or "").strip().lower() == "insufficient_evidence"


def _row() -> dict[str, Any]:
    return {
        "total": 0,
        "completed_total": 0,
        "insufficient_total": 0,
        "completion_rate": 0.0,
        "insufficient_ratio": 0.0,
    }


def _update_row(row: Mapping[str, Any], *, completed: bool, insufficient: bool) -> dict[str, Any]:
    updated = dict(row) if isinstance(row, Mapping) else _row()
    updated["total"] = int(updated.get("total") or 0) + 1
    if completed:
        updated["completed_total"] = int(updated.get("completed_total") or 0) + 1
    if insufficient:
        updated["insufficient_total"] = int(updated.get("insufficient_total") or 0) + 1
    total = int(updated.get("total") or 0)
    completed_total = int(updated.get("completed_total") or 0)
    insufficient_total = int(updated.get("insufficient_total") or 0)
    updated["completion_rate"] = 0.0 if total == 0 else float(completed_total) / float(total)
    updated["insufficient_ratio"] = 0.0 if total == 0 else float(insufficient_total) / float(total)
    return updated


def load_launch_metrics_summary() -> dict[str, Any]:
    cached = _CACHE.get_json(_global_key())
    if isinstance(cached, Mapping):
        payload = dict(cached)
        payload.setdefault("by_intent", {})
        payload.setdefault("by_domain", {})
        payload.setdefault("total", 0)
        payload.setdefault("completed_total", 0)
        payload.setdefault("insufficient_total", 0)
        payload.setdefault("completion_rate", 0.0)
        payload.setdefault("insufficient_ratio", 0.0)
        return payload
    return {
        "total": 0,
        "completed_total": 0,
        "insufficient_total": 0,
        "completion_rate": 0.0,
        "insufficient_ratio": 0.0,
        "by_intent": {},
        "by_domain": {},
    }


def record_launch_metrics(
    *,
    intent: Any,
    status: Any,
    next_action: Any,
    reason_code: Any,
) -> None:
    normalized_intent = _normalize_intent(intent)
    domain = _resolve_domain(normalized_intent)
    completed = _is_completed(status, next_action)
    insufficient = _is_insufficient(status)
    normalized_status = str(status or "").strip().lower() or "unknown"
    normalized_reason = str(reason_code or "").strip().upper() or "CHAT_REASON_UNSPECIFIED"

    payload = load_launch_metrics_summary()
    payload["total"] = int(payload.get("total") or 0) + 1
    if completed:
        payload["completed_total"] = int(payload.get("completed_total") or 0) + 1
    if insufficient:
        payload["insufficient_total"] = int(payload.get("insufficient_total") or 0) + 1

    total = int(payload.get("total") or 0)
    completed_total = int(payload.get("completed_total") or 0)
    insufficient_total = int(payload.get("insufficient_total") or 0)
    payload["completion_rate"] = 0.0 if total == 0 else float(completed_total) / float(total)
    payload["insufficient_ratio"] = 0.0 if total == 0 else float(insufficient_total) / float(total)

    by_intent = payload.get("by_intent") if isinstance(payload.get("by_intent"), Mapping) else {}
    by_domain = payload.get("by_domain") if isinstance(payload.get("by_domain"), Mapping) else {}
    intent_row = _update_row(by_intent.get(normalized_intent) if isinstance(by_intent, Mapping) else {}, completed=completed, insufficient=insufficient)
    domain_row = _update_row(by_domain.get(domain) if isinstance(by_domain, Mapping) else {}, completed=completed, insufficient=insufficient)
    payload["by_intent"] = dict(by_intent)
    payload["by_intent"][normalized_intent] = intent_row
    payload["by_domain"] = dict(by_domain)
    payload["by_domain"][domain] = domain_row

    _CACHE.set_json(_global_key(), payload, ttl=_ttl_sec())

    metrics.inc(
        "chat_launch_samples_total",
        {
            "intent": normalized_intent,
            "domain": domain,
            "status": normalized_status,
            "reason_code": normalized_reason,
        },
    )
    metrics.inc(
        "chat_completion_total",
        {
            "intent": normalized_intent,
            "result": "completed" if completed else "unresolved",
        },
    )
    if insufficient:
        metrics.inc(
            "chat_insufficient_evidence_total",
            {
                "intent": normalized_intent,
                "domain": domain,
            },
        )

    metrics.set("chat_completion_rate", {"intent": normalized_intent}, float(intent_row["completion_rate"]))
    metrics.set("chat_insufficient_evidence_rate", {"domain": domain}, float(domain_row["insufficient_ratio"]))
