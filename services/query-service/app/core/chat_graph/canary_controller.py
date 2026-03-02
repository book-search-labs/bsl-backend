from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.core.cache import get_cache

_CACHE = get_cache()


def _override_key() -> str:
    return "chat:graph:force-legacy:override"


def _audit_key() -> str:
    return "chat:graph:rollback-audit"


def _cooldown_sec() -> int:
    return max(60, int(__import__("os").getenv("QS_CHAT_CANARY_COOLDOWN_SEC", "600")))


def _audit_ttl_sec() -> int:
    return 86400


def _audit_max_entries() -> int:
    return 200


@dataclass
class CanaryGateDecision:
    passed: bool
    gate_status: str
    reason: str
    blocker_ratio: float
    mismatch_ratio: float


@dataclass
class RollbackResult:
    applied: bool
    mode: str
    reason: str
    cooldown_until: int | None


def evaluate_canary_gate(summary_payload: dict[str, Any]) -> CanaryGateDecision:
    blocker_ratio = float(summary_payload.get("blocker_ratio") or 0.0)
    mismatch_ratio = float(summary_payload.get("mismatch_ratio") or 0.0)

    blocker_threshold = float(__import__("os").getenv("QS_CHAT_CANARY_BLOCKER_THRESHOLD", "0.02"))
    mismatch_threshold = float(__import__("os").getenv("QS_CHAT_CANARY_MISMATCH_THRESHOLD", "0.10"))

    if blocker_ratio > blocker_threshold:
        return CanaryGateDecision(
            passed=False,
            gate_status="BLOCK",
            reason="blocker_ratio_exceeded",
            blocker_ratio=blocker_ratio,
            mismatch_ratio=mismatch_ratio,
        )

    if mismatch_ratio > mismatch_threshold:
        return CanaryGateDecision(
            passed=False,
            gate_status="WARN",
            reason="mismatch_ratio_exceeded",
            blocker_ratio=blocker_ratio,
            mismatch_ratio=mismatch_ratio,
        )

    return CanaryGateDecision(
        passed=True,
        gate_status="PASS",
        reason="within_threshold",
        blocker_ratio=blocker_ratio,
        mismatch_ratio=mismatch_ratio,
    )


def current_force_legacy_override() -> dict[str, Any] | None:
    payload = _CACHE.get_json(_override_key())
    if not isinstance(payload, dict):
        return None
    if payload.get("cleared") is True:
        return None
    cooldown_until = payload.get("cooldown_until")
    if isinstance(cooldown_until, int) and int(time.time()) > cooldown_until:
        return None
    return payload


def _append_audit(event: dict[str, Any]) -> None:
    cached = _CACHE.get_json(_audit_key())
    rows: list[dict[str, Any]] = []
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        rows = [item for item in cached.get("events", []) if isinstance(item, dict)]
    rows.append(event)
    if len(rows) > _audit_max_entries():
        rows = rows[-_audit_max_entries():]
    _CACHE.set_json(_audit_key(), {"events": rows}, ttl=_audit_ttl_sec())


def load_rollback_audit() -> list[dict[str, Any]]:
    cached = _CACHE.get_json(_audit_key())
    if isinstance(cached, dict) and isinstance(cached.get("events"), list):
        return [item for item in cached.get("events", []) if isinstance(item, dict)]
    return []


def apply_auto_rollback(
    decision: CanaryGateDecision,
    *,
    trace_id: str,
    request_id: str,
    source: str,
) -> RollbackResult:
    now = int(time.time())
    active = current_force_legacy_override()

    if decision.passed:
        if active is None:
            _append_audit(
                {
                    "ts": now,
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "source": source,
                    "action": "noop",
                    "reason": decision.reason,
                    "gate_status": decision.gate_status,
                }
            )
            return RollbackResult(applied=False, mode="legacy", reason="noop", cooldown_until=None)

        cooldown_until = int(active.get("cooldown_until") or 0)
        if now < cooldown_until:
            _append_audit(
                {
                    "ts": now,
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "source": source,
                    "action": "hold",
                    "reason": "cooldown_active",
                    "gate_status": decision.gate_status,
                    "cooldown_until": cooldown_until,
                }
            )
            return RollbackResult(applied=False, mode="legacy", reason="cooldown_active", cooldown_until=cooldown_until)

        _CACHE.set_json(_override_key(), {"cleared": True}, ttl=1)
        _append_audit(
            {
                "ts": now,
                "trace_id": trace_id,
                "request_id": request_id,
                "source": source,
                "action": "release",
                "reason": "gate_recovered",
                "gate_status": decision.gate_status,
            }
        )
        return RollbackResult(applied=False, mode="legacy", reason="released", cooldown_until=None)

    cooldown_until = now + _cooldown_sec()
    payload = {
        "enabled": True,
        "set_at": now,
        "cooldown_until": cooldown_until,
        "reason": decision.reason,
        "gate_status": decision.gate_status,
        "blocker_ratio": decision.blocker_ratio,
        "mismatch_ratio": decision.mismatch_ratio,
    }
    _CACHE.set_json(_override_key(), payload, ttl=max(60, _cooldown_sec()))
    _append_audit(
        {
            "ts": now,
            "trace_id": trace_id,
            "request_id": request_id,
            "source": source,
            "action": "force_legacy",
            "reason": decision.reason,
            "gate_status": decision.gate_status,
            "cooldown_until": cooldown_until,
            "blocker_ratio": decision.blocker_ratio,
            "mismatch_ratio": decision.mismatch_ratio,
        }
    )
    return RollbackResult(applied=True, mode="legacy", reason=decision.reason, cooldown_until=cooldown_until)
