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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "detected_at", "resolved_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _read_jsonl(path: Path, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
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


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def _report_to_rollback_minutes(row: Mapping[str, Any]) -> float | None:
    explicit = row.get("report_to_rollback_minutes")
    if explicit is not None:
        return max(0.0, _safe_float(explicit, 0.0))

    reported_at = _parse_ts(row.get("reported_at") or row.get("false_positive_reported_at"))
    rollback_at = _parse_ts(row.get("rollback_at") or row.get("blocked_at") or row.get("disabled_at"))
    if reported_at is None or rollback_at is None:
        return None
    return max(0.0, (rollback_at - reported_at).total_seconds() / 60.0)


def summarize_correction_quality_safeguards(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    correction_applied_total = 0
    overapply_total = 0
    precision_gate_fail_total = 0
    false_positive_report_total = 0
    false_positive_open_total = 0
    emergency_block_total = 0
    rollback_total = 0
    rollback_sla_breach_total = 0
    missing_audit_total = 0
    detection_latencies: list[float] = []

    for row in rows:
        event_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        applied = _safe_bool(row.get("correction_applied"), False)
        if applied:
            correction_applied_total += 1
        if _safe_bool(row.get("overapply_detected"), False):
            overapply_total += 1
        if _safe_bool(row.get("precision_gate_fail"), False) or _safe_bool(row.get("precision_below_threshold"), False):
            precision_gate_fail_total += 1

        false_positive = _safe_bool(row.get("false_positive_reported"), False)
        if false_positive:
            false_positive_report_total += 1
            status = str(row.get("false_positive_status") or row.get("status") or "").strip().upper()
            if status in {"OPEN", "PENDING", "UNRESOLVED"}:
                false_positive_open_total += 1

        if _safe_bool(row.get("emergency_blocked"), False) or _safe_bool(row.get("immediate_disable"), False):
            emergency_block_total += 1
        if _safe_bool(row.get("rolled_back"), False) or _safe_bool(row.get("disabled"), False):
            rollback_total += 1

        minutes = _report_to_rollback_minutes(row)
        if minutes is not None:
            detection_latencies.append(minutes)
            if minutes > 30.0:
                rollback_sla_breach_total += 1

        actor = str(row.get("actor_id") or row.get("actor") or "").strip()
        reason = str(row.get("reason_code") or row.get("quality_reason_code") or "").strip()
        if (false_positive or applied) and (not actor or not reason):
            missing_audit_total += 1

    p95_report_to_rollback_minutes = _p95(detection_latencies)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "correction_applied_total": correction_applied_total,
        "overapply_total": overapply_total,
        "precision_gate_fail_total": precision_gate_fail_total,
        "false_positive_report_total": false_positive_report_total,
        "false_positive_open_total": false_positive_open_total,
        "emergency_block_total": emergency_block_total,
        "rollback_total": rollback_total,
        "rollback_sla_breach_total": rollback_sla_breach_total,
        "missing_audit_total": missing_audit_total,
        "p95_report_to_rollback_minutes": p95_report_to_rollback_minutes,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    max_overapply_total: int,
    max_precision_gate_fail_total: int,
    max_false_positive_open_total: int,
    max_rollback_sla_breach_total: int,
    max_missing_audit_total: int,
    max_p95_report_to_rollback_minutes: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    overapply_total = _safe_int(summary.get("overapply_total"), 0)
    precision_gate_fail_total = _safe_int(summary.get("precision_gate_fail_total"), 0)
    false_positive_open_total = _safe_int(summary.get("false_positive_open_total"), 0)
    rollback_sla_breach_total = _safe_int(summary.get("rollback_sla_breach_total"), 0)
    missing_audit_total = _safe_int(summary.get("missing_audit_total"), 0)
    p95_report_to_rollback_minutes = _safe_float(summary.get("p95_report_to_rollback_minutes"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat correction safeguards window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"chat correction safeguards event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if overapply_total > max(0, int(max_overapply_total)):
        failures.append(f"chat correction safeguards overapply total exceeded: {overapply_total} > {int(max_overapply_total)}")
    if precision_gate_fail_total > max(0, int(max_precision_gate_fail_total)):
        failures.append(
            f"chat correction safeguards precision gate fail total exceeded: {precision_gate_fail_total} > {int(max_precision_gate_fail_total)}"
        )
    if false_positive_open_total > max(0, int(max_false_positive_open_total)):
        failures.append(
            "chat correction safeguards false-positive open total exceeded: "
            f"{false_positive_open_total} > {int(max_false_positive_open_total)}"
        )
    if rollback_sla_breach_total > max(0, int(max_rollback_sla_breach_total)):
        failures.append(
            f"chat correction safeguards rollback SLA breach total exceeded: {rollback_sla_breach_total} > {int(max_rollback_sla_breach_total)}"
        )
    if missing_audit_total > max(0, int(max_missing_audit_total)):
        failures.append(
            f"chat correction safeguards missing audit total exceeded: {missing_audit_total} > {int(max_missing_audit_total)}"
        )
    if p95_report_to_rollback_minutes > max(0.0, float(max_p95_report_to_rollback_minutes)):
        failures.append(
            "chat correction safeguards p95 report->rollback exceeded: "
            f"{p95_report_to_rollback_minutes:.2f}m > {float(max_p95_report_to_rollback_minutes):.2f}m"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat correction safeguards stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Correction Quality Safeguards")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- correction_applied_total: {_safe_int(summary.get('correction_applied_total'), 0)}")
    lines.append(f"- overapply_total: {_safe_int(summary.get('overapply_total'), 0)}")
    lines.append(f"- false_positive_open_total: {_safe_int(summary.get('false_positive_open_total'), 0)}")
    lines.append(f"- rollback_sla_breach_total: {_safe_int(summary.get('rollback_sla_breach_total'), 0)}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    else:
        lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate correction memory quality safeguards.")
    parser.add_argument("--events-jsonl", default="var/chat_correction/correction_quality_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_correction_quality_safeguards")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--max-overapply-total", type=int, default=0)
    parser.add_argument("--max-precision-gate-fail-total", type=int, default=0)
    parser.add_argument("--max-false-positive-open-total", type=int, default=0)
    parser.add_argument("--max-rollback-sla-breach-total", type=int, default=0)
    parser.add_argument("--max-missing-audit-total", type=int, default=0)
    parser.add_argument("--max-p95-report-to-rollback-minutes", type=float, default=1000000.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_correction_quality_safeguards(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        max_overapply_total=max(0, int(args.max_overapply_total)),
        max_precision_gate_fail_total=max(0, int(args.max_precision_gate_fail_total)),
        max_false_positive_open_total=max(0, int(args.max_false_positive_open_total)),
        max_rollback_sla_breach_total=max(0, int(args.max_rollback_sla_breach_total)),
        max_missing_audit_total=max(0, int(args.max_missing_audit_total)),
        max_p95_report_to_rollback_minutes=max(0.0, float(args.max_p95_report_to_rollback_minutes)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(args.events_jsonl),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "max_overapply_total": int(args.max_overapply_total),
                "max_precision_gate_fail_total": int(args.max_precision_gate_fail_total),
                "max_false_positive_open_total": int(args.max_false_positive_open_total),
                "max_rollback_sla_breach_total": int(args.max_rollback_sla_breach_total),
                "max_missing_audit_total": int(args.max_missing_audit_total),
                "max_p95_report_to_rollback_minutes": float(args.max_p95_report_to_rollback_minutes),
                "max_stale_minutes": float(args.max_stale_minutes),
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
    print(f"overapply_total={_safe_int(summary.get('overapply_total'), 0)}")
    print(f"false_positive_open_total={_safe_int(summary.get('false_positive_open_total'), 0)}")
    print(f"rollback_sla_breach_total={_safe_int(summary.get('rollback_sla_breach_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
