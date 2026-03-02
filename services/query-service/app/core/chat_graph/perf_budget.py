from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

from app.core.cache import get_cache
from app.core.metrics import metrics

_CACHE = get_cache()


@dataclass(frozen=True)
class BudgetGateDecision:
    passed: bool
    failures: list[str]


@dataclass(frozen=True)
class CutoverDecision:
    action: str
    next_stage: int
    reason: str


def _global_key() -> str:
    return "chat:graph:perf-budget:global"


def _ttl_sec() -> int:
    return 86400


def _max_entries() -> int:
    return 1000


def _append_event(event: dict[str, Any]) -> None:
    cached = _CACHE.get_json(_global_key())
    rows: list[dict[str, Any]] = []
    if isinstance(cached, Mapping) and isinstance(cached.get("events"), list):
        rows = [dict(item) for item in cached.get("events", []) if isinstance(item, Mapping)]
    rows.append(event)
    if len(rows) > _max_entries():
        rows = rows[-_max_entries() :]
    _CACHE.set_json(_global_key(), {"events": rows}, ttl=_ttl_sec())


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * q
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(ordered[lo])
    weight = rank - lo
    return float(ordered[lo]) * (1.0 - weight) + float(ordered[hi]) * weight


def append_perf_sample(
    *,
    trace_id: str,
    request_id: str,
    session_id: str,
    engine_mode: str,
    route: str,
    status: str,
    runtime_ms: int,
    llm_path: bool,
    tool_calls: int,
) -> None:
    event = {
        "ts": int(time.time()),
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "engine_mode": engine_mode,
        "route": route,
        "status": status,
        "runtime_ms": max(0, int(runtime_ms)),
        "llm_path": bool(llm_path),
        "tool_calls": max(0, int(tool_calls)),
    }
    _append_event(event)
    metrics.inc(
        "chat_graph_perf_sample_total",
        {
            "engine_mode": engine_mode,
            "route": route or "NONE",
            "status": status or "unknown",
            "llm_path": "true" if llm_path else "false",
        },
    )
    metrics.inc("chat_graph_runtime_latency_ms", {"engine_mode": engine_mode}, value=max(1, int(runtime_ms)))


def build_perf_summary(*, limit: int = 500) -> dict[str, Any]:
    cached = _CACHE.get_json(_global_key())
    rows: list[dict[str, Any]] = []
    if isinstance(cached, Mapping) and isinstance(cached.get("events"), list):
        rows = [dict(item) for item in cached.get("events", []) if isinstance(item, Mapping)]
    sliced = rows[-max(1, int(limit)) :]
    llm_latencies = [int(item.get("runtime_ms") or 0) for item in sliced if bool(item.get("llm_path"))]
    non_llm_latencies = [int(item.get("runtime_ms") or 0) for item in sliced if not bool(item.get("llm_path"))]
    all_latencies = [int(item.get("runtime_ms") or 0) for item in sliced]
    fallback_count = sum(1 for item in sliced if str(item.get("status") or "") != "ok")
    avg_tool_calls = (
        0.0 if not sliced else float(sum(int(item.get("tool_calls") or 0) for item in sliced)) / float(len(sliced))
    )
    return {
        "window_size": len(sliced),
        "llm_count": len(llm_latencies),
        "non_llm_count": len(non_llm_latencies),
        "all_p95_ms": _percentile(all_latencies, 0.95),
        "all_p99_ms": _percentile(all_latencies, 0.99),
        "llm_p95_ms": _percentile(llm_latencies, 0.95),
        "llm_p99_ms": _percentile(llm_latencies, 0.99),
        "non_llm_p95_ms": _percentile(non_llm_latencies, 0.95),
        "non_llm_p99_ms": _percentile(non_llm_latencies, 0.99),
        "fallback_ratio": 0.0 if not sliced else float(fallback_count) / float(len(sliced)),
        "avg_tool_calls": avg_tool_calls,
        "samples": sliced[-30:],
    }


def evaluate_budget_gate(summary: Mapping[str, Any]) -> BudgetGateDecision:
    failures: list[str] = []
    min_window = max(0, int(os.getenv("QS_CHAT_BUDGET_MIN_WINDOW", "20")))
    non_llm_p95_max = max(1.0, float(os.getenv("QS_CHAT_BUDGET_NON_LLM_P95_MS", "600")))
    llm_p95_max = max(1.0, float(os.getenv("QS_CHAT_BUDGET_LLM_P95_MS", "4000")))
    max_avg_tool_calls = max(0.0, float(os.getenv("QS_CHAT_BUDGET_MAX_AVG_TOOL_CALLS", "1.5")))
    max_fallback_ratio = min(1.0, max(0.0, float(os.getenv("QS_CHAT_BUDGET_MAX_FALLBACK_RATIO", "0.15"))))

    window_size = int(summary.get("window_size") or 0)
    if window_size < min_window:
        failures.append(f"insufficient perf samples: window_size={window_size} < min_window={min_window}")

    non_llm_p95 = float(summary.get("non_llm_p95_ms") or 0.0)
    llm_p95 = float(summary.get("llm_p95_ms") or 0.0)
    avg_tool_calls = float(summary.get("avg_tool_calls") or 0.0)
    fallback_ratio = float(summary.get("fallback_ratio") or 0.0)

    non_llm_count = int(summary.get("non_llm_count") or 0)
    llm_count = int(summary.get("llm_count") or 0)
    if non_llm_count > 0 and non_llm_p95 > non_llm_p95_max:
        failures.append(f"non-llm p95 exceeded: {non_llm_p95:.2f}ms > {non_llm_p95_max:.2f}ms")
    if llm_count > 0 and llm_p95 > llm_p95_max:
        failures.append(f"llm p95 exceeded: {llm_p95:.2f}ms > {llm_p95_max:.2f}ms")
    if avg_tool_calls > max_avg_tool_calls:
        failures.append(f"avg tool calls exceeded: {avg_tool_calls:.4f} > {max_avg_tool_calls:.4f}")
    if fallback_ratio > max_fallback_ratio:
        failures.append(f"fallback ratio exceeded: {fallback_ratio:.4f} > {max_fallback_ratio:.4f}")
    return BudgetGateDecision(passed=len(failures) == 0, failures=failures)


def evaluate_cutover_decision(
    summary: Mapping[str, Any],
    *,
    current_stage: int,
    dwell_minutes: int,
) -> CutoverDecision:
    gate = evaluate_budget_gate(summary)
    min_dwell = max(0, int(os.getenv("QS_CHAT_CUTOVER_MIN_DWELL_MIN", "30")))
    allowed_stages = [10, 25, 50, 100]
    stage = current_stage if current_stage in allowed_stages else 10
    if not gate.passed:
        return CutoverDecision(action="rollback", next_stage=max(10, stage // 2), reason="budget_gate_failed")
    if dwell_minutes < min_dwell:
        return CutoverDecision(action="hold", next_stage=stage, reason="dwell_not_met")
    if stage >= 100:
        return CutoverDecision(action="hold", next_stage=100, reason="already_full")
    next_stage = 100
    for item in allowed_stages:
        if item > stage:
            next_stage = item
            break
    return CutoverDecision(action="promote", next_stage=next_stage, reason="budget_gate_passed")
