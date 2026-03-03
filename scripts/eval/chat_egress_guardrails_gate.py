#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
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
    for key in ("timestamp", "event_time", "ts", "generated_at", "created_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_status(value: Any) -> str:
    text = str(value or "UNKNOWN").strip().upper()
    if not text:
        return "UNKNOWN"
    return text


def _destination(row: Mapping[str, Any]) -> str:
    for key in ("destination", "target", "provider", "egress_target"):
        text = str(row.get(key) or "").strip().lower()
        if text:
            return text
    return "unknown"


def _sensitive_hit_total(row: Mapping[str, Any]) -> int:
    value = row.get("sensitive_field_total")
    total = _safe_int(value, 0)
    if total > 0:
        return total
    hits = row.get("sensitive_hits")
    if isinstance(hits, list):
        return len(hits)
    if _safe_bool(row.get("sensitive_detected"), False):
        return 1
    return 0


def _is_masked(row: Mapping[str, Any], *, status: str) -> bool:
    if _safe_bool(row.get("masked"), False):
        return True
    action = str(row.get("policy_action") or "").strip().upper()
    if action in {"MASK", "BLOCK"}:
        return True
    return status in {"MASKED", "BLOCKED"}


def _is_blocked(row: Mapping[str, Any], *, status: str) -> bool:
    if status == "BLOCKED":
        return True
    action = str(row.get("policy_action") or "").strip().upper()
    return action == "BLOCK"


def read_events(path: Path, *, window_hours: int, limit: int, now: datetime | None = None) -> list[dict[str, Any]]:
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
        if isinstance(payload, dict):
            rows.append(payload)

    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]

    threshold = (now or datetime.now(timezone.utc)) - timedelta(hours=max(1, int(window_hours)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def _parse_allowlist(raw: str) -> set[str]:
    items = [item.strip().lower() for item in str(raw or "").split(",") if item.strip()]
    return set(items)


def summarize_egress(events: list[Mapping[str, Any]], *, allow_destinations: set[str], now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    blocked_total = 0
    masked_total = 0
    violation_total = 0
    unknown_destination_total = 0
    unmasked_sensitive_total = 0
    error_total = 0
    missing_trace_total = 0
    traced_total = 0
    alert_sent_total = 0
    alerts_for_violation_total = 0

    latest_ts: datetime | None = None
    destinations: dict[str, dict[str, int]] = {}
    statuses: dict[str, int] = {}
    unique_requests: set[str] = set()

    for row in events:
        status = _normalize_status(row.get("status"))
        destination = _destination(row)
        sensitive_total = _sensitive_hit_total(row)
        masked = _is_masked(row, status=status)
        blocked = _is_blocked(row, status=status)
        allowlist_violation = _safe_bool(row.get("allowlist_violation"), False)
        trace_id = str(row.get("trace_id") or "").strip()
        request_id = str(row.get("request_id") or "").strip()
        ts = _event_ts(row)
        alert_sent = _safe_bool(row.get("alert_sent"), False)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        statuses[status] = statuses.get(status, 0) + 1

        if trace_id and request_id:
            traced_total += 1
            unique_requests.add(f"{trace_id}:{request_id}")
        else:
            missing_trace_total += 1

        if alert_sent:
            alert_sent_total += 1

        row_destination = destinations.setdefault(destination, {"total": 0, "violations": 0, "blocked": 0})
        row_destination["total"] += 1

        if blocked:
            blocked_total += 1
            row_destination["blocked"] += 1
        if masked:
            masked_total += 1

        is_unknown_destination = bool(allow_destinations) and destination not in allow_destinations
        if is_unknown_destination and not blocked:
            unknown_destination_total += 1

        unmasked_sensitive = sensitive_total > 0 and not masked and not blocked
        if unmasked_sensitive:
            unmasked_sensitive_total += 1

        is_violation = allowlist_violation or status == "VIOLATION" or unmasked_sensitive or (is_unknown_destination and not blocked)
        if is_violation:
            violation_total += 1
            row_destination["violations"] += 1
            if alert_sent:
                alerts_for_violation_total += 1

        if status in {"ERROR", "FAILED"}:
            error_total += 1

    window_size = len(events)
    error_ratio = 0.0 if window_size == 0 else float(error_total) / float(window_size)
    trace_coverage_ratio = 1.0 if window_size == 0 else float(traced_total) / float(window_size)
    alert_coverage_ratio = 1.0 if violation_total == 0 else float(alerts_for_violation_total) / float(violation_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    destination_rows = [
        {
            "destination": name,
            "total": values["total"],
            "violations": values["violations"],
            "blocked": values["blocked"],
        }
        for name, values in sorted(destinations.items(), key=lambda item: (-item[1]["violations"], -item[1]["total"], item[0]))
    ]

    status_rows = [
        {"status": status, "count": count}
        for status, count in sorted(statuses.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "window_size": window_size,
        "unique_request_total": len(unique_requests),
        "blocked_total": blocked_total,
        "masked_total": masked_total,
        "violation_total": violation_total,
        "unknown_destination_total": unknown_destination_total,
        "unmasked_sensitive_total": unmasked_sensitive_total,
        "error_total": error_total,
        "error_ratio": error_ratio,
        "missing_trace_total": missing_trace_total,
        "trace_coverage_ratio": trace_coverage_ratio,
        "alert_sent_total": alert_sent_total,
        "alerts_for_violation_total": alerts_for_violation_total,
        "alert_coverage_ratio": alert_coverage_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
        "allow_destinations": sorted(allow_destinations),
        "destinations": destination_rows,
        "statuses": status_rows,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_violation_total: int,
    max_unmasked_sensitive_total: int,
    max_unknown_destination_total: int,
    max_error_ratio: float,
    max_missing_trace_total: int,
    min_alert_coverage_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = int(summary.get("window_size") or 0)
    violation_total = int(summary.get("violation_total") or 0)
    unmasked_sensitive_total = int(summary.get("unmasked_sensitive_total") or 0)
    unknown_destination_total = int(summary.get("unknown_destination_total") or 0)
    error_ratio = _safe_float(summary.get("error_ratio"), 0.0)
    missing_trace_total = int(summary.get("missing_trace_total") or 0)
    alert_coverage_ratio = _safe_float(summary.get("alert_coverage_ratio"), 1.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"egress window too small: {window_size} < {int(min_window)}")
    if violation_total > max(0, int(max_violation_total)):
        failures.append(f"egress violations exceeded: {violation_total} > {int(max_violation_total)}")
    if unmasked_sensitive_total > max(0, int(max_unmasked_sensitive_total)):
        failures.append(
            "unmasked sensitive egress exceeded: "
            f"{unmasked_sensitive_total} > {int(max_unmasked_sensitive_total)}"
        )
    if unknown_destination_total > max(0, int(max_unknown_destination_total)):
        failures.append(
            "unknown destination egress exceeded: "
            f"{unknown_destination_total} > {int(max_unknown_destination_total)}"
        )
    if error_ratio > max(0.0, float(max_error_ratio)):
        failures.append(f"egress error ratio exceeded: {error_ratio:.4f} > {float(max_error_ratio):.4f}")
    if missing_trace_total > max(0, int(max_missing_trace_total)):
        failures.append(f"missing trace context exceeded: {missing_trace_total} > {int(max_missing_trace_total)}")
    if alert_coverage_ratio < max(0.0, float(min_alert_coverage_ratio)):
        failures.append(
            f"alert coverage below threshold: {alert_coverage_ratio:.4f} < {float(min_alert_coverage_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"egress events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_violation_total_increase: int,
    max_unmasked_sensitive_increase: int,
    max_unknown_destination_increase: int,
    max_error_ratio_increase: float,
    max_alert_coverage_ratio_drop: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_violation_total = int(base_summary.get("violation_total") or 0)
    cur_violation_total = int(current_summary.get("violation_total") or 0)
    violation_increase = max(0, cur_violation_total - base_violation_total)
    if violation_increase > max(0, int(max_violation_total_increase)):
        failures.append(
            "violation regression: "
            f"baseline={base_violation_total}, current={cur_violation_total}, "
            f"allowed_increase={max(0, int(max_violation_total_increase))}"
        )

    base_unmasked_total = int(base_summary.get("unmasked_sensitive_total") or 0)
    cur_unmasked_total = int(current_summary.get("unmasked_sensitive_total") or 0)
    unmasked_increase = max(0, cur_unmasked_total - base_unmasked_total)
    if unmasked_increase > max(0, int(max_unmasked_sensitive_increase)):
        failures.append(
            "unmasked sensitive regression: "
            f"baseline={base_unmasked_total}, current={cur_unmasked_total}, "
            f"allowed_increase={max(0, int(max_unmasked_sensitive_increase))}"
        )

    base_unknown_total = int(base_summary.get("unknown_destination_total") or 0)
    cur_unknown_total = int(current_summary.get("unknown_destination_total") or 0)
    unknown_increase = max(0, cur_unknown_total - base_unknown_total)
    if unknown_increase > max(0, int(max_unknown_destination_increase)):
        failures.append(
            "unknown destination regression: "
            f"baseline={base_unknown_total}, current={cur_unknown_total}, "
            f"allowed_increase={max(0, int(max_unknown_destination_increase))}"
        )

    base_error_ratio = _safe_float(base_summary.get("error_ratio"), 0.0)
    cur_error_ratio = _safe_float(current_summary.get("error_ratio"), 0.0)
    error_ratio_increase = max(0.0, cur_error_ratio - base_error_ratio)
    if error_ratio_increase > max(0.0, float(max_error_ratio_increase)):
        failures.append(
            "error ratio regression: "
            f"baseline={base_error_ratio:.6f}, current={cur_error_ratio:.6f}, "
            f"allowed_increase={float(max_error_ratio_increase):.6f}"
        )

    base_alert_coverage_ratio = _safe_float(base_summary.get("alert_coverage_ratio"), 1.0)
    cur_alert_coverage_ratio = _safe_float(current_summary.get("alert_coverage_ratio"), 1.0)
    alert_coverage_drop = max(0.0, base_alert_coverage_ratio - cur_alert_coverage_ratio)
    if alert_coverage_drop > max(0.0, float(max_alert_coverage_ratio_drop)):
        failures.append(
            "alert coverage regression: "
            f"baseline={base_alert_coverage_ratio:.6f}, current={cur_alert_coverage_ratio:.6f}, "
            f"allowed_drop={float(max_alert_coverage_ratio_drop):.6f}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Egress Guardrails Gate")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {int(summary.get('window_size') or 0)}")
    lines.append(f"- violation_total: {int(summary.get('violation_total') or 0)}")
    lines.append(f"- unmasked_sensitive_total: {int(summary.get('unmasked_sensitive_total') or 0)}")
    lines.append(f"- unknown_destination_total: {int(summary.get('unknown_destination_total') or 0)}")
    lines.append(f"- error_ratio: {_safe_float(summary.get('error_ratio'), 0.0):.4f}")
    lines.append(f"- trace_coverage_ratio: {_safe_float(summary.get('trace_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- alert_coverage_ratio: {_safe_float(summary.get('alert_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- stale_minutes: {_safe_float(summary.get('stale_minutes'), 0.0):.1f}")
    lines.append("")
    lines.append("## Destinations")
    lines.append("")
    destination_rows = summary.get("destinations") if isinstance(summary.get("destinations"), list) else []
    if destination_rows:
        for row in destination_rows:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                f"- {row.get('destination')}: total={int(row.get('total') or 0)} "
                f"violations={int(row.get('violations') or 0)} blocked={int(row.get('blocked') or 0)}"
            )
    else:
        lines.append("- (none)")

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
    parser = argparse.ArgumentParser(description="Evaluate outbound egress guardrails from chat egress events.")
    parser.add_argument("--events-jsonl", default="var/chat_governance/egress_events.jsonl")
    parser.add_argument("--allow-destinations", default="llm_provider,langsmith,support_api")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=20000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_egress_guardrails_gate")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-violation-total", type=int, default=0)
    parser.add_argument("--max-unmasked-sensitive-total", type=int, default=0)
    parser.add_argument("--max-unknown-destination-total", type=int, default=0)
    parser.add_argument("--max-error-ratio", type=float, default=0.05)
    parser.add_argument("--max-missing-trace-total", type=int, default=0)
    parser.add_argument("--min-alert-coverage-ratio", type=float, default=1.0)
    parser.add_argument("--max-stale-minutes", type=float, default=180.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-violation-total-increase", type=int, default=0)
    parser.add_argument("--max-unmasked-sensitive-increase", type=int, default=0)
    parser.add_argument("--max-unknown-destination-increase", type=int, default=0)
    parser.add_argument("--max-error-ratio-increase", type=float, default=0.02)
    parser.add_argument("--max-alert-coverage-ratio-drop", type=float, default=0.05)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    allow_destinations = _parse_allowlist(args.allow_destinations)
    events_path = Path(args.events_jsonl)
    events = read_events(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )

    summary = summarize_egress(events, allow_destinations=allow_destinations)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_violation_total=max(0, int(args.max_violation_total)),
        max_unmasked_sensitive_total=max(0, int(args.max_unmasked_sensitive_total)),
        max_unknown_destination_total=max(0, int(args.max_unknown_destination_total)),
        max_error_ratio=max(0.0, float(args.max_error_ratio)),
        max_missing_trace_total=max(0, int(args.max_missing_trace_total)),
        min_alert_coverage_ratio=max(0.0, float(args.min_alert_coverage_ratio)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = json.loads(Path(args.baseline_report).read_text(encoding="utf-8"))
        if not isinstance(baseline_report, dict):
            raise RuntimeError(f"expected JSON object from {args.baseline_report}")
        baseline_failures = compare_with_baseline(
            baseline_report,
            summary,
            max_violation_total_increase=max(0, int(args.max_violation_total_increase)),
            max_unmasked_sensitive_increase=max(0, int(args.max_unmasked_sensitive_increase)),
            max_unknown_destination_increase=max(0, int(args.max_unknown_destination_increase)),
            max_error_ratio_increase=max(0.0, float(args.max_error_ratio_increase)),
            max_alert_coverage_ratio_drop=max(0.0, float(args.max_alert_coverage_ratio_drop)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "allow_destinations": sorted(allow_destinations),
            "window_hours": max(1, int(args.window_hours)),
            "limit": max(1, int(args.limit)),
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
                "max_violation_total": int(args.max_violation_total),
                "max_unmasked_sensitive_total": int(args.max_unmasked_sensitive_total),
                "max_unknown_destination_total": int(args.max_unknown_destination_total),
                "max_error_ratio": float(args.max_error_ratio),
                "max_missing_trace_total": int(args.max_missing_trace_total),
                "min_alert_coverage_ratio": float(args.min_alert_coverage_ratio),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_violation_total_increase": int(args.max_violation_total_increase),
                "max_unmasked_sensitive_increase": int(args.max_unmasked_sensitive_increase),
                "max_unknown_destination_increase": int(args.max_unknown_destination_increase),
                "max_error_ratio_increase": float(args.max_error_ratio_increase),
                "max_alert_coverage_ratio_drop": float(args.max_alert_coverage_ratio_drop),
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
    print(f"window_size={int(summary.get('window_size') or 0)}")
    print(f"violation_total={int(summary.get('violation_total') or 0)}")
    print(f"alert_coverage_ratio={_safe_float(summary.get('alert_coverage_ratio'), 0.0):.4f}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and not payload["gate"]["pass"]:
        for failure in failures:
            print(f"[gate-failure] {failure}")
        for failure in baseline_failures:
            print(f"[baseline-failure] {failure}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
