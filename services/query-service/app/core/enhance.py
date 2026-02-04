from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from app.core.cache import CacheClient


@dataclass
class EnhanceConfig:
    score_gap_threshold: float
    min_latency_budget_ms: int
    window_sec: int
    max_per_window: int
    cooldown_sec: int
    max_per_query_per_hour: int


def load_config() -> EnhanceConfig:
    return EnhanceConfig(
        score_gap_threshold=float(os.getenv("QS_ENHANCE_SCORE_GAP_THRESHOLD", "0.05")),
        min_latency_budget_ms=int(os.getenv("QS_ENHANCE_MIN_LATENCY_BUDGET_MS", "200")),
        window_sec=int(os.getenv("QS_ENHANCE_WINDOW_SEC", "60")),
        max_per_window=int(os.getenv("QS_ENHANCE_MAX_PER_WINDOW", "60")),
        cooldown_sec=int(os.getenv("QS_ENHANCE_COOLDOWN_SEC", "300")),
        max_per_query_per_hour=int(os.getenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "10")),
    )


def evaluate_gate(
    reason: str | None,
    signals: dict[str, Any],
    detected: dict[str, Any],
    canonical_key: str,
    cache: CacheClient,
    config: EnhanceConfig,
) -> dict[str, Any]:
    reason_codes: list[str] = []
    if reason:
        reason_codes.append(reason)
    decision = "RUN"
    strategy = "REWRITE_ONLY"

    if not reason:
        return _skip("NO_REASON", reason_codes)

    mode = str(detected.get("mode") or "normal")
    is_isbn = bool(detected.get("is_isbn") or detected.get("isIsbn"))

    if is_isbn:
        return _skip("ISBN_QUERY", reason_codes)

    if reason not in {"ZERO_RESULTS", "LOW_RESULTS", "LOW_CONFIDENCE", "HIGH_OOV", "USER_EXPLICIT"}:
        return _skip("UNSUPPORTED_REASON", reason_codes)

    if reason == "LOW_CONFIDENCE":
        score_gap = signals.get("score_gap")
        if score_gap is None or score_gap >= config.score_gap_threshold:
            return _skip("SCORE_GAP_HIGH", reason_codes)

    latency_budget_ms = signals.get("latency_budget_ms")
    if latency_budget_ms is not None and latency_budget_ms < config.min_latency_budget_ms:
        return _skip("LOW_BUDGET", reason_codes)

    now = int(time.time())
    window_bucket = now // max(config.window_sec, 1)
    global_key = f"qs:enh:budget:{window_bucket}"
    count = cache.incr(global_key, ttl=config.window_sec + 1)
    if count > config.max_per_window:
        return _skip("BUDGET_EXCEEDED", reason_codes)

    cooldown_key = f"qs:enh:cooldown:{canonical_key}"
    if not cache.setnx(cooldown_key, "1", ttl=config.cooldown_sec):
        return _skip("COOLDOWN_HIT", reason_codes)

    hour_bucket = now // 3600
    per_query_key = f"qs:enh:qcount:{canonical_key}:{hour_bucket}"
    per_query_count = cache.incr(per_query_key, ttl=3600 + 10)
    if per_query_count > config.max_per_query_per_hour:
        return _skip("PER_QUERY_CAP", reason_codes)

    if reason == "ZERO_RESULTS":
        strategy = "SPELL_THEN_REWRITE"
    elif reason == "LOW_RESULTS":
        strategy = "REWRITE_ONLY"
    elif reason == "HIGH_OOV":
        strategy = "SPELL_ONLY"
    elif reason == "LOW_CONFIDENCE":
        strategy = "REWRITE_ONLY"
    elif reason == "USER_EXPLICIT":
        strategy = "RAG_REWRITE"

    if mode == "chosung":
        strategy = "REWRITE_ONLY"

    return {
        "decision": decision,
        "strategy": strategy,
        "reason_codes": reason_codes,
    }


def _skip(code: str, reason_codes: list[str]) -> dict[str, Any]:
    if code not in reason_codes:
        reason_codes.append(code)
    return {"decision": "SKIP", "strategy": "NONE", "reason_codes": reason_codes}
