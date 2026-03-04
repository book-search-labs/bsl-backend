#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

CRITICAL_EVENTS = {"BUDGET_EXCEEDED", "BUDGET_ABORT", "HARD_BREACH"}


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
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, Mapping):
            rows.append({str(k): v for k, v in payload.items()})
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
        "EXCEEDED": "BUDGET_EXCEEDED",
        "ABORT": "BUDGET_ABORT",
        "EARLY_STOP": "BUDGET_ABORT",
        "HARD_LIMIT_BREACH": "HARD_BREACH",
    }
    return aliases.get(text, text or "UNKNOWN")


def summarize_audit_explainability(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    missing_reason_code_total = 0
    unknown_reason_code_total = 0
    missing_trace_id_total = 0
    missing_request_id_total = 0
    missing_budget_type_total = 0
    explainability_missing_total = 0
    dashboard_tag_missing_total = 0
    critical_event_total = 0

    for row in events:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        reason_code = str(row.get("reason_code") or "").strip().upper()
        if not reason_code:
            missing_reason_code_total += 1
        elif "BUDGET" not in reason_code:
            unknown_reason_code_total += 1

        trace_id = str(row.get("trace_id") or "").strip()
        request_id = str(row.get("request_id") or "").strip()
        if not trace_id:
            missing_trace_id_total += 1
        if not request_id:
            missing_request_id_total += 1

        intent = str(row.get("intent") or row.get("intent_type") or "").strip()
        tenant_id = str(row.get("tenant_id") or row.get("tenant") or "").strip()
        if not intent or not tenant_id:
            dashboard_tag_missing_total += 1

        event = _event_type(row.get("event_type") or row.get("event") or row.get("status"))
        if event in CRITICAL_EVENTS:
            critical_event_total += 1
            budget_type = str(row.get("budget_type") or row.get("limit_type") or "").strip()
            if not budget_type:
                missing_budget_type_total += 1
            explain_text = str(
                row.get("user_message")
                or row.get("retry_hint")
                or row.get("next_action")
                or row.get("operator_note")
                or ""
            ).strip()
            if not explain_text:
                explainability_missing_total += 1

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)
    return {
        "window_size": len(events),
        "critical_event_total": critical_event_total,
        "missing_reason_code_total": missing_reason_code_total,
        "unknown_reason_code_total": unknown_reason_code_total,
        "missing_trace_id_total": missing_trace_id_total,
        "missing_request_id_total": missing_request_id_total,
        "missing_budget_type_total": missing_budget_type_total,
        "explainability_missing_total": explainability_missing_total,
        "dashboard_tag_missing_total": dashboard_tag_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_missing_reason_code_total: int,
    max_unknown_reason_code_total: int,
    max_missing_trace_id_total: int,
    max_missing_request_id_total: int,
    max_missing_budget_type_total: int,
    max_explainability_missing_total: int,
    max_dashboard_tag_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    unknown_reason_code_total = _safe_int(summary.get("unknown_reason_code_total"), 0)
    missing_trace_id_total = _safe_int(summary.get("missing_trace_id_total"), 0)
    missing_request_id_total = _safe_int(summary.get("missing_request_id_total"), 0)
    missing_budget_type_total = _safe_int(summary.get("missing_budget_type_total"), 0)
    explainability_missing_total = _safe_int(summary.get("explainability_missing_total"), 0)
    dashboard_tag_missing_total = _safe_int(summary.get("dashboard_tag_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"reasoning audit window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(
            f"reasoning audit missing reason code total exceeded: {missing_reason_code_total} > {int(max_missing_reason_code_total)}"
        )
    if unknown_reason_code_total > max(0, int(max_unknown_reason_code_total)):
        failures.append(
            f"reasoning audit unknown reason code total exceeded: {unknown_reason_code_total} > {int(max_unknown_reason_code_total)}"
        )
    if missing_trace_id_total > max(0, int(max_missing_trace_id_total)):
        failures.append(
            f"reasoning audit missing trace id total exceeded: {missing_trace_id_total} > {int(max_missing_trace_id_total)}"
        )
    if missing_request_id_total > max(0, int(max_missing_request_id_total)):
        failures.append(
            f"reasoning audit missing request id total exceeded: {missing_request_id_total} > {int(max_missing_request_id_total)}"
        )
    if missing_budget_type_total > max(0, int(max_missing_budget_type_total)):
        failures.append(
            f"reasoning audit missing budget type total exceeded: {missing_budget_type_total} > {int(max_missing_budget_type_total)}"
        )
    if explainability_missing_total > max(0, int(max_explainability_missing_total)):
        failures.append(
            "reasoning audit explainability missing total exceeded: "
            f"{explainability_missing_total} > {int(max_explainability_missing_total)}"
        )
    if dashboard_tag_missing_total > max(0, int(max_dashboard_tag_missing_total)):
        failures.append(
            f"reasoning audit dashboard tag missing total exceeded: {dashboard_tag_missing_total} > {int(max_dashboard_tag_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"reasoning audit evidence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_critical_event_total_drop: int,
    max_missing_reason_code_total_increase: int,
    max_unknown_reason_code_total_increase: int,
    max_missing_trace_id_total_increase: int,
    max_missing_request_id_total_increase: int,
    max_missing_budget_type_total_increase: int,
    max_explainability_missing_total_increase: int,
    max_dashboard_tag_missing_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_critical_event_total = _safe_int(base_summary.get("critical_event_total"), 0)
    cur_critical_event_total = _safe_int(current_summary.get("critical_event_total"), 0)
    critical_event_total_drop = max(0, base_critical_event_total - cur_critical_event_total)
    if critical_event_total_drop > max(0, int(max_critical_event_total_drop)):
        failures.append(
            "critical_event_total regression: "
            f"baseline={base_critical_event_total}, current={cur_critical_event_total}, "
            f"allowed_drop={max(0, int(max_critical_event_total_drop))}"
        )

    baseline_pairs = [
        ("missing_reason_code_total", max_missing_reason_code_total_increase),
        ("unknown_reason_code_total", max_unknown_reason_code_total_increase),
        ("missing_trace_id_total", max_missing_trace_id_total_increase),
        ("missing_request_id_total", max_missing_request_id_total_increase),
        ("missing_budget_type_total", max_missing_budget_type_total_increase),
        ("explainability_missing_total", max_explainability_missing_total_increase),
        ("dashboard_tag_missing_total", max_dashboard_tag_missing_total_increase),
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
    lines.append("# Chat Reasoning Budget Audit Explainability")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- missing_reason_code_total: {_safe_int(summary.get('missing_reason_code_total'), 0)}")
    lines.append(f"- missing_trace_id_total: {_safe_int(summary.get('missing_trace_id_total'), 0)}")
    lines.append(f"- explainability_missing_total: {_safe_int(summary.get('explainability_missing_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate audit/explainability quality for reasoning budget events.")
    parser.add_argument("--events-jsonl", default="var/chat_budget/audit_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_reasoning_budget_audit_explainability")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--max-unknown-reason-code-total", type=int, default=0)
    parser.add_argument("--max-missing-trace-id-total", type=int, default=0)
    parser.add_argument("--max-missing-request-id-total", type=int, default=0)
    parser.add_argument("--max-missing-budget-type-total", type=int, default=0)
    parser.add_argument("--max-explainability-missing-total", type=int, default=0)
    parser.add_argument("--max-dashboard-tag-missing-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-critical-event-total-drop", type=int, default=5)
    parser.add_argument("--max-missing-reason-code-total-increase", type=int, default=0)
    parser.add_argument("--max-unknown-reason-code-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-trace-id-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-request-id-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-budget-type-total-increase", type=int, default=0)
    parser.add_argument("--max-explainability-missing-total-increase", type=int, default=0)
    parser.add_argument("--max-dashboard-tag-missing-total-increase", type=int, default=0)
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
    summary = summarize_audit_explainability(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        max_unknown_reason_code_total=max(0, int(args.max_unknown_reason_code_total)),
        max_missing_trace_id_total=max(0, int(args.max_missing_trace_id_total)),
        max_missing_request_id_total=max(0, int(args.max_missing_request_id_total)),
        max_missing_budget_type_total=max(0, int(args.max_missing_budget_type_total)),
        max_explainability_missing_total=max(0, int(args.max_explainability_missing_total)),
        max_dashboard_tag_missing_total=max(0, int(args.max_dashboard_tag_missing_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_critical_event_total_drop=max(0, int(args.max_critical_event_total_drop)),
            max_missing_reason_code_total_increase=max(0, int(args.max_missing_reason_code_total_increase)),
            max_unknown_reason_code_total_increase=max(0, int(args.max_unknown_reason_code_total_increase)),
            max_missing_trace_id_total_increase=max(0, int(args.max_missing_trace_id_total_increase)),
            max_missing_request_id_total_increase=max(0, int(args.max_missing_request_id_total_increase)),
            max_missing_budget_type_total_increase=max(0, int(args.max_missing_budget_type_total_increase)),
            max_explainability_missing_total_increase=max(0, int(args.max_explainability_missing_total_increase)),
            max_dashboard_tag_missing_total_increase=max(0, int(args.max_dashboard_tag_missing_total_increase)),
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
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "max_unknown_reason_code_total": int(args.max_unknown_reason_code_total),
                "max_missing_trace_id_total": int(args.max_missing_trace_id_total),
                "max_missing_request_id_total": int(args.max_missing_request_id_total),
                "max_missing_budget_type_total": int(args.max_missing_budget_type_total),
                "max_explainability_missing_total": int(args.max_explainability_missing_total),
                "max_dashboard_tag_missing_total": int(args.max_dashboard_tag_missing_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_critical_event_total_drop": int(args.max_critical_event_total_drop),
                "max_missing_reason_code_total_increase": int(args.max_missing_reason_code_total_increase),
                "max_unknown_reason_code_total_increase": int(args.max_unknown_reason_code_total_increase),
                "max_missing_trace_id_total_increase": int(args.max_missing_trace_id_total_increase),
                "max_missing_request_id_total_increase": int(args.max_missing_request_id_total_increase),
                "max_missing_budget_type_total_increase": int(args.max_missing_budget_type_total_increase),
                "max_explainability_missing_total_increase": int(args.max_explainability_missing_total_increase),
                "max_dashboard_tag_missing_total_increase": int(args.max_dashboard_tag_missing_total_increase),
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
    print(f"missing_reason_code_total={_safe_int(summary.get('missing_reason_code_total'), 0)}")
    print(f"explainability_missing_total={_safe_int(summary.get('explainability_missing_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
