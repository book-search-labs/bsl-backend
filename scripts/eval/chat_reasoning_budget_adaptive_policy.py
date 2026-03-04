#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

HIGH_COST_INTENTS_DEFAULT = {"REFUND_REQUEST", "CANCEL_ORDER", "PAYMENT_CHANGE"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _event_ts(row: Mapping[str, Any]) -> datetime | None:
    for key in ("timestamp", "event_time", "created_at", "updated_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _read_rows(path: Path, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except Exception:
            continue
        if isinstance(item, Mapping):
            rows.append({str(k): v for k, v in item.items()})
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]

    threshold = datetime.now(timezone.utc) - timedelta(hours=max(1, int(window_hours)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def _event_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "ADJUST": "ADAPTIVE_ADJUST",
        "PROFILE_APPLIED": "ADAPTIVE_ADJUST",
        "PRECONFIRM": "PRECONFIRM_REQUIRED",
        "PRE_CONFIRM_REQUIRED": "PRECONFIRM_REQUIRED",
        "PRECONFIRM_SKIPPED": "PRECONFIRM_MISSING",
        "PRE_CONFIRM_SKIPPED": "PRECONFIRM_MISSING",
        "ROLLBACK": "ROLLBACK",
    }
    return aliases.get(text, text or "UNKNOWN")


def _request_key(row: Mapping[str, Any]) -> str:
    for key in ("request_id", "trace_id", "session_id", "turn_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def summarize_adaptive_policy(
    events: list[Mapping[str, Any]],
    *,
    high_cost_intents: set[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None
    states: dict[str, dict[str, Any]] = {}

    for row in events:
        key = _request_key(row)
        if not key:
            continue
        state = states.setdefault(
            key,
            {
                "high_cost": False,
                "preconfirm": False,
                "preconfirm_missing": False,
                "adjusted": False,
                "direction": "",
                "before_success": None,
                "after_success": None,
                "before_cost": None,
                "after_cost": None,
                "rollback": False,
            },
        )
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        intent = str(row.get("intent") or row.get("intent_type") or "").strip().upper()
        if intent in high_cost_intents or _safe_bool(row.get("high_cost_intent"), False):
            state["high_cost"] = True

        event = _event_type(row.get("event_type") or row.get("event") or row.get("status"))
        if event == "PRECONFIRM_REQUIRED" or _safe_bool(row.get("preconfirm_required"), False):
            state["preconfirm"] = True
        if event == "PRECONFIRM_MISSING" or _safe_bool(row.get("preconfirm_missing"), False):
            state["preconfirm_missing"] = True

        if event == "ADAPTIVE_ADJUST":
            state["adjusted"] = True
            direction = str(row.get("adjustment_direction") or row.get("direction") or "").strip().upper()
            if direction:
                state["direction"] = direction
            if row.get("before_success_rate") is not None:
                state["before_success"] = _safe_float(row.get("before_success_rate"), 0.0)
            if row.get("after_success_rate") is not None:
                state["after_success"] = _safe_float(row.get("after_success_rate"), 0.0)
            if row.get("before_cost_per_session") is not None:
                state["before_cost"] = _safe_float(row.get("before_cost_per_session"), 0.0)
            if row.get("after_cost_per_session") is not None:
                state["after_cost"] = _safe_float(row.get("after_cost_per_session"), 0.0)

        if event == "ROLLBACK":
            state["rollback"] = True

    request_total = len(states)
    adjustment_total = 0
    expansion_total = 0
    unsafe_expansion_total = 0
    success_regression_total = 0
    cost_regression_total = 0
    success_improved_total = 0
    cost_reduced_total = 0
    rollback_total = 0
    high_cost_request_total = 0
    preconfirm_missing_total = 0
    preconfirm_covered_total = 0

    for state in states.values():
        if state["high_cost"]:
            high_cost_request_total += 1
            if state["preconfirm"]:
                preconfirm_covered_total += 1
            else:
                preconfirm_missing_total += 1
            if state["preconfirm_missing"]:
                preconfirm_missing_total += 1

        if state["adjusted"]:
            adjustment_total += 1
            before_success = state["before_success"]
            after_success = state["after_success"]
            before_cost = state["before_cost"]
            after_cost = state["after_cost"]
            direction = str(state["direction"] or "").upper()
            if direction == "INCREASE":
                expansion_total += 1
                if (
                    before_success is not None
                    and after_success is not None
                    and before_cost is not None
                    and after_cost is not None
                    and after_cost > before_cost
                    and after_success <= before_success
                ):
                    unsafe_expansion_total += 1
            if before_success is not None and after_success is not None:
                if after_success < before_success:
                    success_regression_total += 1
                elif after_success > before_success:
                    success_improved_total += 1
            if before_cost is not None and after_cost is not None:
                if after_cost > before_cost:
                    cost_regression_total += 1
                elif after_cost < before_cost:
                    cost_reduced_total += 1

        if state["rollback"]:
            rollback_total += 1

    preconfirm_coverage_ratio = (
        1.0 if high_cost_request_total == 0 else float(preconfirm_covered_total) / float(high_cost_request_total)
    )
    success_regression_ratio = 0.0 if adjustment_total == 0 else float(success_regression_total) / float(adjustment_total)
    cost_regression_ratio = 0.0 if adjustment_total == 0 else float(cost_regression_total) / float(adjustment_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "request_total": request_total,
        "adjustment_total": adjustment_total,
        "expansion_total": expansion_total,
        "unsafe_expansion_total": unsafe_expansion_total,
        "success_regression_total": success_regression_total,
        "cost_regression_total": cost_regression_total,
        "success_improved_total": success_improved_total,
        "cost_reduced_total": cost_reduced_total,
        "rollback_total": rollback_total,
        "high_cost_request_total": high_cost_request_total,
        "preconfirm_missing_total": preconfirm_missing_total,
        "preconfirm_coverage_ratio": preconfirm_coverage_ratio,
        "success_regression_ratio": success_regression_ratio,
        "cost_regression_ratio": cost_regression_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_unsafe_expansion_total: int,
    max_preconfirm_missing_total: int,
    min_preconfirm_coverage_ratio: float,
    max_success_regression_ratio: float,
    max_cost_regression_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    unsafe_expansion_total = _safe_int(summary.get("unsafe_expansion_total"), 0)
    preconfirm_missing_total = _safe_int(summary.get("preconfirm_missing_total"), 0)
    preconfirm_coverage_ratio = _safe_float(summary.get("preconfirm_coverage_ratio"), 1.0)
    success_regression_ratio = _safe_float(summary.get("success_regression_ratio"), 0.0)
    cost_regression_ratio = _safe_float(summary.get("cost_regression_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"reasoning adaptive window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if unsafe_expansion_total > max(0, int(max_unsafe_expansion_total)):
        failures.append(
            f"reasoning adaptive unsafe expansion total exceeded: {unsafe_expansion_total} > {int(max_unsafe_expansion_total)}"
        )
    if preconfirm_missing_total > max(0, int(max_preconfirm_missing_total)):
        failures.append(
            f"reasoning adaptive preconfirm missing total exceeded: {preconfirm_missing_total} > {int(max_preconfirm_missing_total)}"
        )
    if preconfirm_coverage_ratio < max(0.0, float(min_preconfirm_coverage_ratio)):
        failures.append(
            "reasoning adaptive preconfirm coverage ratio below threshold: "
            f"{preconfirm_coverage_ratio:.4f} < {float(min_preconfirm_coverage_ratio):.4f}"
        )
    if success_regression_ratio > max(0.0, float(max_success_regression_ratio)):
        failures.append(
            "reasoning adaptive success regression ratio exceeded: "
            f"{success_regression_ratio:.4f} > {float(max_success_regression_ratio):.4f}"
        )
    if cost_regression_ratio > max(0.0, float(max_cost_regression_ratio)):
        failures.append(
            f"reasoning adaptive cost regression ratio exceeded: {cost_regression_ratio:.4f} > {float(max_cost_regression_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"reasoning adaptive evidence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_unsafe_expansion_total_increase: int,
    max_preconfirm_missing_total_increase: int,
    max_preconfirm_coverage_ratio_drop: float,
    max_success_regression_ratio_increase: float,
    max_cost_regression_ratio_increase: float,
    max_rollback_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_pairs = [
        ("unsafe_expansion_total", max_unsafe_expansion_total_increase),
        ("preconfirm_missing_total", max_preconfirm_missing_total_increase),
        ("rollback_total", max_rollback_total_increase),
    ]
    for key, allowed_increase in baseline_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        increase = max(0, cur_value - base_value)
        if increase > max(0, int(allowed_increase)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_increase={max(0, int(allowed_increase))}"
            )

    base_preconfirm_coverage_ratio = _safe_float(base_summary.get("preconfirm_coverage_ratio"), 0.0)
    cur_preconfirm_coverage_ratio = _safe_float(current_summary.get("preconfirm_coverage_ratio"), 0.0)
    preconfirm_coverage_ratio_drop = max(0.0, base_preconfirm_coverage_ratio - cur_preconfirm_coverage_ratio)
    if preconfirm_coverage_ratio_drop > max(0.0, float(max_preconfirm_coverage_ratio_drop)):
        failures.append(
            "preconfirm_coverage_ratio regression: "
            f"baseline={base_preconfirm_coverage_ratio:.6f}, current={cur_preconfirm_coverage_ratio:.6f}, "
            f"allowed_drop={float(max_preconfirm_coverage_ratio_drop):.6f}"
        )

    base_success_regression_ratio = _safe_float(base_summary.get("success_regression_ratio"), 0.0)
    cur_success_regression_ratio = _safe_float(current_summary.get("success_regression_ratio"), 0.0)
    success_regression_ratio_increase = max(0.0, cur_success_regression_ratio - base_success_regression_ratio)
    if success_regression_ratio_increase > max(0.0, float(max_success_regression_ratio_increase)):
        failures.append(
            "success_regression_ratio regression: "
            f"baseline={base_success_regression_ratio:.6f}, current={cur_success_regression_ratio:.6f}, "
            f"allowed_increase={float(max_success_regression_ratio_increase):.6f}"
        )

    base_cost_regression_ratio = _safe_float(base_summary.get("cost_regression_ratio"), 0.0)
    cur_cost_regression_ratio = _safe_float(current_summary.get("cost_regression_ratio"), 0.0)
    cost_regression_ratio_increase = max(0.0, cur_cost_regression_ratio - base_cost_regression_ratio)
    if cost_regression_ratio_increase > max(0.0, float(max_cost_regression_ratio_increase)):
        failures.append(
            "cost_regression_ratio regression: "
            f"baseline={base_cost_regression_ratio:.6f}, current={cur_cost_regression_ratio:.6f}, "
            f"allowed_increase={float(max_cost_regression_ratio_increase):.6f}"
        )

    base_stale_minutes = _safe_float(base_summary.get("stale_minutes"), 0.0)
    cur_stale_minutes = _safe_float(current_summary.get("stale_minutes"), 0.0)
    stale_minutes_increase = max(0.0, cur_stale_minutes - base_stale_minutes)
    if stale_minutes_increase > max(0.0, float(max_stale_minutes_increase)):
        failures.append(
            "stale minutes regression: "
            f"baseline={base_stale_minutes:.6f}, current={cur_stale_minutes:.6f}, "
            f"allowed_increase={float(max_stale_minutes_increase):.6f}"
        )

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Reasoning Budget Adaptive Policy")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- adjustment_total: {_safe_int(summary.get('adjustment_total'), 0)}")
    lines.append(f"- unsafe_expansion_total: {_safe_int(summary.get('unsafe_expansion_total'), 0)}")
    lines.append(f"- preconfirm_missing_total: {_safe_int(summary.get('preconfirm_missing_total'), 0)}")
    lines.append(f"- preconfirm_coverage_ratio: {_safe_float(summary.get('preconfirm_coverage_ratio'), 1.0):.4f}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate adaptive reasoning budget tuning policy.")
    parser.add_argument("--events-jsonl", default="var/chat_budget/adaptive_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--high-cost-intents", default="REFUND_REQUEST,CANCEL_ORDER,PAYMENT_CHANGE")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_reasoning_budget_adaptive_policy")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-unsafe-expansion-total", type=int, default=0)
    parser.add_argument("--max-preconfirm-missing-total", type=int, default=0)
    parser.add_argument("--min-preconfirm-coverage-ratio", type=float, default=0.9)
    parser.add_argument("--max-success-regression-ratio", type=float, default=0.2)
    parser.add_argument("--max-cost-regression-ratio", type=float, default=0.2)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-unsafe-expansion-total-increase", type=int, default=0)
    parser.add_argument("--max-preconfirm-missing-total-increase", type=int, default=0)
    parser.add_argument("--max-preconfirm-coverage-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-success-regression-ratio-increase", type=float, default=0.05)
    parser.add_argument("--max-cost-regression-ratio-increase", type=float, default=0.05)
    parser.add_argument("--max-rollback-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    high_cost_intents = {
        token.strip().upper() for token in str(args.high_cost_intents).split(",") if token.strip()
    } or set(HIGH_COST_INTENTS_DEFAULT)
    events_path = Path(args.events_jsonl)
    events = _read_rows(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_adaptive_policy(events, high_cost_intents=high_cost_intents)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_unsafe_expansion_total=max(0, int(args.max_unsafe_expansion_total)),
        max_preconfirm_missing_total=max(0, int(args.max_preconfirm_missing_total)),
        min_preconfirm_coverage_ratio=max(0.0, float(args.min_preconfirm_coverage_ratio)),
        max_success_regression_ratio=max(0.0, float(args.max_success_regression_ratio)),
        max_cost_regression_ratio=max(0.0, float(args.max_cost_regression_ratio)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_unsafe_expansion_total_increase=max(0, int(args.max_unsafe_expansion_total_increase)),
            max_preconfirm_missing_total_increase=max(0, int(args.max_preconfirm_missing_total_increase)),
            max_preconfirm_coverage_ratio_drop=max(0.0, float(args.max_preconfirm_coverage_ratio_drop)),
            max_success_regression_ratio_increase=max(0.0, float(args.max_success_regression_ratio_increase)),
            max_cost_regression_ratio_increase=max(0.0, float(args.max_cost_regression_ratio_increase)),
            max_rollback_total_increase=max(0, int(args.max_rollback_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": int(args.window_hours),
            "limit": int(args.limit),
            "high_cost_intents": sorted(high_cost_intents),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": summary,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_unsafe_expansion_total": int(args.max_unsafe_expansion_total),
                "max_preconfirm_missing_total": int(args.max_preconfirm_missing_total),
                "min_preconfirm_coverage_ratio": float(args.min_preconfirm_coverage_ratio),
                "max_success_regression_ratio": float(args.max_success_regression_ratio),
                "max_cost_regression_ratio": float(args.max_cost_regression_ratio),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_unsafe_expansion_total_increase": int(args.max_unsafe_expansion_total_increase),
                "max_preconfirm_missing_total_increase": int(args.max_preconfirm_missing_total_increase),
                "max_preconfirm_coverage_ratio_drop": float(args.max_preconfirm_coverage_ratio_drop),
                "max_success_regression_ratio_increase": float(args.max_success_regression_ratio_increase),
                "max_cost_regression_ratio_increase": float(args.max_cost_regression_ratio_increase),
                "max_rollback_total_increase": int(args.max_rollback_total_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"adjustment_total={_safe_int(summary.get('adjustment_total'), 0)}")
    print(f"unsafe_expansion_total={_safe_int(summary.get('unsafe_expansion_total'), 0)}")
    print(f"preconfirm_coverage_ratio={_safe_float(summary.get('preconfirm_coverage_ratio'), 1.0):.4f}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
