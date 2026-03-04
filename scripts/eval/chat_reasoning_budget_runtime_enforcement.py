#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


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
        "WARNING": "BUDGET_WARNING",
        "BUDGET_WARN": "BUDGET_WARNING",
        "EXCEEDED": "BUDGET_EXCEEDED",
        "BUDGET_LIMIT_EXCEEDED": "BUDGET_EXCEEDED",
        "EARLY_STOP": "BUDGET_ABORT",
        "ABORT": "BUDGET_ABORT",
        "BUDGET_ABORTED": "BUDGET_ABORT",
        "HARD_LIMIT_BREACH": "HARD_BREACH",
        "RETRY": "RETRY_PROMPT",
    }
    return aliases.get(text, text or "UNKNOWN")


def _request_key(row: Mapping[str, Any]) -> str:
    for key in ("request_id", "trace_id", "session_id", "turn_id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def summarize_runtime_enforcement(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None
    states: dict[str, dict[str, bool]] = {}
    exceed_by_type: dict[str, int] = {}
    hard_breach_total = 0

    for row in events:
        event = _event_type(row.get("event_type") or row.get("event") or row.get("status"))
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        key = _request_key(row)
        if not key:
            continue
        state = states.setdefault(
            key,
            {
                "warned": False,
                "exceeded": False,
                "aborted": False,
                "graceful": False,
                "retry_prompt": False,
                "enforced": False,
                "hard_breach": False,
            },
        )

        enforcement_action = str(row.get("enforcement_action") or row.get("action") or "").strip().upper()
        if enforcement_action:
            state["enforced"] = True

        if event == "BUDGET_WARNING":
            state["warned"] = True
        elif event == "BUDGET_EXCEEDED":
            state["exceeded"] = True
            budget_type = str(row.get("budget_type") or row.get("limit_type") or "UNKNOWN").strip().upper() or "UNKNOWN"
            exceed_by_type[budget_type] = exceed_by_type.get(budget_type, 0) + 1
        elif event == "BUDGET_ABORT":
            state["aborted"] = True
            state["graceful"] = _safe_bool(row.get("graceful"), True)
        elif event == "RETRY_PROMPT":
            state["retry_prompt"] = True
        elif event == "HARD_BREACH":
            state["hard_breach"] = True
            hard_breach_total += 1

    request_total = len(states)
    exceeded_request_total = 0
    abort_request_total = 0
    graceful_abort_request_total = 0
    warning_before_abort_total = 0
    retry_prompt_request_total = 0
    enforced_exceed_request_total = 0
    unhandled_exceed_request_total = 0

    for state in states.values():
        if state["exceeded"]:
            exceeded_request_total += 1
            if state["aborted"] or state["enforced"]:
                enforced_exceed_request_total += 1
            else:
                unhandled_exceed_request_total += 1
        if state["aborted"]:
            abort_request_total += 1
            if state["graceful"]:
                graceful_abort_request_total += 1
            if state["warned"]:
                warning_before_abort_total += 1
            if state["retry_prompt"]:
                retry_prompt_request_total += 1
        if state["hard_breach"]:
            hard_breach_total += 0

    enforcement_coverage_ratio = (
        1.0 if exceeded_request_total == 0 else float(enforced_exceed_request_total) / float(exceeded_request_total)
    )
    warning_before_abort_ratio = (
        1.0 if abort_request_total == 0 else float(warning_before_abort_total) / float(abort_request_total)
    )
    graceful_abort_ratio = (
        1.0 if abort_request_total == 0 else float(graceful_abort_request_total) / float(abort_request_total)
    )
    retry_prompt_ratio = 1.0 if abort_request_total == 0 else float(retry_prompt_request_total) / float(abort_request_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "request_total": request_total,
        "exceeded_request_total": exceeded_request_total,
        "abort_request_total": abort_request_total,
        "graceful_abort_request_total": graceful_abort_request_total,
        "warning_before_abort_total": warning_before_abort_total,
        "retry_prompt_request_total": retry_prompt_request_total,
        "enforced_exceed_request_total": enforced_exceed_request_total,
        "unhandled_exceed_request_total": unhandled_exceed_request_total,
        "hard_breach_total": hard_breach_total,
        "enforcement_coverage_ratio": enforcement_coverage_ratio,
        "warning_before_abort_ratio": warning_before_abort_ratio,
        "graceful_abort_ratio": graceful_abort_ratio,
        "retry_prompt_ratio": retry_prompt_ratio,
        "exceed_by_type": [
            {"budget_type": key, "count": value}
            for key, value in sorted(exceed_by_type.items(), key=lambda item: item[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_hard_breach_total: int,
    max_unhandled_exceed_request_total: int,
    min_enforcement_coverage_ratio: float,
    min_warning_before_abort_ratio: float,
    min_graceful_abort_ratio: float,
    min_retry_prompt_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    hard_breach_total = _safe_int(summary.get("hard_breach_total"), 0)
    unhandled_exceed_request_total = _safe_int(summary.get("unhandled_exceed_request_total"), 0)
    enforcement_coverage_ratio = _safe_float(summary.get("enforcement_coverage_ratio"), 1.0)
    warning_before_abort_ratio = _safe_float(summary.get("warning_before_abort_ratio"), 1.0)
    graceful_abort_ratio = _safe_float(summary.get("graceful_abort_ratio"), 1.0)
    retry_prompt_ratio = _safe_float(summary.get("retry_prompt_ratio"), 1.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"reasoning runtime window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if hard_breach_total > max(0, int(max_hard_breach_total)):
        failures.append(f"reasoning runtime hard breach total exceeded: {hard_breach_total} > {int(max_hard_breach_total)}")
    if unhandled_exceed_request_total > max(0, int(max_unhandled_exceed_request_total)):
        failures.append(
            "reasoning runtime unhandled exceed request total exceeded: "
            f"{unhandled_exceed_request_total} > {int(max_unhandled_exceed_request_total)}"
        )
    if enforcement_coverage_ratio < max(0.0, float(min_enforcement_coverage_ratio)):
        failures.append(
            "reasoning runtime enforcement coverage ratio below threshold: "
            f"{enforcement_coverage_ratio:.4f} < {float(min_enforcement_coverage_ratio):.4f}"
        )
    if warning_before_abort_ratio < max(0.0, float(min_warning_before_abort_ratio)):
        failures.append(
            "reasoning runtime warning-before-abort ratio below threshold: "
            f"{warning_before_abort_ratio:.4f} < {float(min_warning_before_abort_ratio):.4f}"
        )
    if graceful_abort_ratio < max(0.0, float(min_graceful_abort_ratio)):
        failures.append(
            f"reasoning runtime graceful abort ratio below threshold: {graceful_abort_ratio:.4f} < {float(min_graceful_abort_ratio):.4f}"
        )
    if retry_prompt_ratio < max(0.0, float(min_retry_prompt_ratio)):
        failures.append(
            f"reasoning runtime retry prompt ratio below threshold: {retry_prompt_ratio:.4f} < {float(min_retry_prompt_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"reasoning runtime evidence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_hard_breach_total_increase: int,
    max_unhandled_exceed_request_total_increase: int,
    max_enforcement_coverage_ratio_drop: float,
    max_warning_before_abort_ratio_drop: float,
    max_graceful_abort_ratio_drop: float,
    max_retry_prompt_ratio_drop: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_pairs = [
        ("hard_breach_total", max_hard_breach_total_increase),
        ("unhandled_exceed_request_total", max_unhandled_exceed_request_total_increase),
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

    baseline_ratio_pairs = [
        ("enforcement_coverage_ratio", max_enforcement_coverage_ratio_drop),
        ("warning_before_abort_ratio", max_warning_before_abort_ratio_drop),
        ("graceful_abort_ratio", max_graceful_abort_ratio_drop),
        ("retry_prompt_ratio", max_retry_prompt_ratio_drop),
    ]
    for key, allowed_drop in baseline_ratio_pairs:
        base_value = _safe_float(base_summary.get(key), 0.0)
        cur_value = _safe_float(current_summary.get(key), 0.0)
        drop = max(0.0, base_value - cur_value)
        if drop > max(0.0, float(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value:.6f}, current={cur_value:.6f}, "
                f"allowed_drop={max(0.0, float(allowed_drop)):.6f}"
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
    lines.append("# Chat Reasoning Budget Runtime Enforcement")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- hard_breach_total: {_safe_int(summary.get('hard_breach_total'), 0)}")
    lines.append(f"- unhandled_exceed_request_total: {_safe_int(summary.get('unhandled_exceed_request_total'), 0)}")
    lines.append(f"- enforcement_coverage_ratio: {_safe_float(summary.get('enforcement_coverage_ratio'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate runtime enforcement for reasoning budget overflow.")
    parser.add_argument("--events-jsonl", default="var/chat_budget/runtime_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_reasoning_budget_runtime_enforcement")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-hard-breach-total", type=int, default=0)
    parser.add_argument("--max-unhandled-exceed-request-total", type=int, default=0)
    parser.add_argument("--min-enforcement-coverage-ratio", type=float, default=0.95)
    parser.add_argument("--min-warning-before-abort-ratio", type=float, default=0.7)
    parser.add_argument("--min-graceful-abort-ratio", type=float, default=0.9)
    parser.add_argument("--min-retry-prompt-ratio", type=float, default=0.8)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-hard-breach-total-increase", type=int, default=0)
    parser.add_argument("--max-unhandled-exceed-request-total-increase", type=int, default=0)
    parser.add_argument("--max-enforcement-coverage-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-warning-before-abort-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-graceful-abort-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-retry-prompt-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    events_path = Path(args.events_jsonl)
    events = _read_rows(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_runtime_enforcement(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_hard_breach_total=max(0, int(args.max_hard_breach_total)),
        max_unhandled_exceed_request_total=max(0, int(args.max_unhandled_exceed_request_total)),
        min_enforcement_coverage_ratio=max(0.0, float(args.min_enforcement_coverage_ratio)),
        min_warning_before_abort_ratio=max(0.0, float(args.min_warning_before_abort_ratio)),
        min_graceful_abort_ratio=max(0.0, float(args.min_graceful_abort_ratio)),
        min_retry_prompt_ratio=max(0.0, float(args.min_retry_prompt_ratio)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_hard_breach_total_increase=max(0, int(args.max_hard_breach_total_increase)),
            max_unhandled_exceed_request_total_increase=max(0, int(args.max_unhandled_exceed_request_total_increase)),
            max_enforcement_coverage_ratio_drop=max(0.0, float(args.max_enforcement_coverage_ratio_drop)),
            max_warning_before_abort_ratio_drop=max(0.0, float(args.max_warning_before_abort_ratio_drop)),
            max_graceful_abort_ratio_drop=max(0.0, float(args.max_graceful_abort_ratio_drop)),
            max_retry_prompt_ratio_drop=max(0.0, float(args.max_retry_prompt_ratio_drop)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": int(args.window_hours),
            "limit": int(args.limit),
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
                "max_hard_breach_total": int(args.max_hard_breach_total),
                "max_unhandled_exceed_request_total": int(args.max_unhandled_exceed_request_total),
                "min_enforcement_coverage_ratio": float(args.min_enforcement_coverage_ratio),
                "min_warning_before_abort_ratio": float(args.min_warning_before_abort_ratio),
                "min_graceful_abort_ratio": float(args.min_graceful_abort_ratio),
                "min_retry_prompt_ratio": float(args.min_retry_prompt_ratio),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_hard_breach_total_increase": int(args.max_hard_breach_total_increase),
                "max_unhandled_exceed_request_total_increase": int(args.max_unhandled_exceed_request_total_increase),
                "max_enforcement_coverage_ratio_drop": float(args.max_enforcement_coverage_ratio_drop),
                "max_warning_before_abort_ratio_drop": float(args.max_warning_before_abort_ratio_drop),
                "max_graceful_abort_ratio_drop": float(args.max_graceful_abort_ratio_drop),
                "max_retry_prompt_ratio_drop": float(args.max_retry_prompt_ratio_drop),
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
    print(f"window_size={_safe_int(summary.get('window_size'), 0)}")
    print(f"hard_breach_total={_safe_int(summary.get('hard_breach_total'), 0)}")
    print(f"enforcement_coverage_ratio={_safe_float(summary.get('enforcement_coverage_ratio'), 1.0):.4f}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
