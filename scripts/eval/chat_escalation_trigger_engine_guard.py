#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


HIGH_RISK_REASON_TOKENS = {
    "AUTHZ",
    "PAYMENT",
    "SECURITY",
    "PRIVACY",
    "REFUND_DENY",
    "WRITE_SENSITIVE",
}


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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "y"}


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


def _reason_code(row: Mapping[str, Any]) -> str:
    return str(row.get("reason_code") or row.get("trigger_reason_code") or "").upper()


def _high_risk_reason(row: Mapping[str, Any]) -> bool:
    if row.get("high_risk_reason") is not None:
        return _safe_bool(row.get("high_risk_reason"))
    reason = _reason_code(row)
    return any(token in reason for token in HIGH_RISK_REASON_TOKENS)


def _dissatisfaction_signal(row: Mapping[str, Any]) -> bool:
    if row.get("dissatisfaction_signal") is not None:
        return _safe_bool(row.get("dissatisfaction_signal"))
    if row.get("user_complaint_signal") is not None:
        return _safe_bool(row.get("user_complaint_signal"))
    sentiment = str(row.get("sentiment") or "").strip().lower()
    return sentiment in {"angry", "frustrated", "negative"}


def _failure_count(row: Mapping[str, Any]) -> int:
    return max(0, _safe_int(row.get("failure_count_recent"), _safe_int(row.get("failure_streak"), 0)))


def _candidate(row: Mapping[str, Any], *, failure_threshold: int) -> bool:
    if row.get("escalation_candidate") is not None:
        return _safe_bool(row.get("escalation_candidate"))
    if _failure_count(row) >= max(1, int(failure_threshold)):
        return True
    if _high_risk_reason(row):
        return True
    if _dissatisfaction_signal(row):
        return True
    return False


def _escalated(row: Mapping[str, Any]) -> bool:
    if row.get("escalation_triggered") is not None:
        return _safe_bool(row.get("escalation_triggered"))
    level = str(row.get("escalation_level") or "").strip().upper()
    return level not in {"", "NONE", "NO_ESCALATION"}


def _cooldown_active(row: Mapping[str, Any]) -> bool:
    if row.get("cooldown_active") is not None:
        return _safe_bool(row.get("cooldown_active"))
    return _safe_bool(row.get("trigger_cooldown_applied"))


def _hysteresis_applied(row: Mapping[str, Any]) -> bool:
    if row.get("hysteresis_applied") is not None:
        return _safe_bool(row.get("hysteresis_applied"))
    return _safe_bool(row.get("confidence_hysteresis_applied"))


def _threshold_version_present(row: Mapping[str, Any]) -> bool:
    version = str(row.get("threshold_version") or row.get("escalation_policy_version") or "").strip()
    return bool(version)


def summarize_escalation_trigger_engine_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    failure_threshold: int = 3,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    candidate_total = 0
    escalation_triggered_total = 0
    trigger_missed_total = 0
    cooldown_suppressed_total = 0
    hysteresis_suppressed_total = 0
    false_positive_total = 0
    threshold_version_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        candidate = _candidate(row, failure_threshold=failure_threshold)
        escalated = _escalated(row)
        cooldown = _cooldown_active(row)
        hysteresis = _hysteresis_applied(row)

        if not _threshold_version_present(row):
            threshold_version_missing_total += 1

        if candidate:
            candidate_total += 1
            if escalated:
                escalation_triggered_total += 1
            elif cooldown:
                cooldown_suppressed_total += 1
            elif hysteresis:
                hysteresis_suppressed_total += 1
            else:
                trigger_missed_total += 1
        elif escalated:
            escalation_triggered_total += 1
            false_positive_total += 1

    trigger_recall = 1.0 if candidate_total == 0 else float(escalation_triggered_total - false_positive_total) / float(candidate_total)
    false_positive_rate = 0.0 if escalation_triggered_total == 0 else float(false_positive_total) / float(escalation_triggered_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "candidate_total": candidate_total,
        "escalation_triggered_total": escalation_triggered_total,
        "trigger_missed_total": trigger_missed_total,
        "cooldown_suppressed_total": cooldown_suppressed_total,
        "hysteresis_suppressed_total": hysteresis_suppressed_total,
        "false_positive_total": false_positive_total,
        "false_positive_rate": false_positive_rate,
        "trigger_recall": trigger_recall,
        "threshold_version_missing_total": threshold_version_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_trigger_recall: float,
    max_trigger_missed_total: int,
    max_false_positive_rate: float,
    max_threshold_version_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    trigger_recall = _safe_float(summary.get("trigger_recall"), 0.0)
    trigger_missed_total = _safe_int(summary.get("trigger_missed_total"), 0)
    false_positive_rate = _safe_float(summary.get("false_positive_rate"), 0.0)
    threshold_version_missing_total = _safe_int(summary.get("threshold_version_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"escalation trigger window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"escalation trigger event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if trigger_recall < max(0.0, float(min_trigger_recall)):
        failures.append(f"escalation trigger recall below minimum: {trigger_recall:.4f} < {float(min_trigger_recall):.4f}")
    if trigger_missed_total > max(0, int(max_trigger_missed_total)):
        failures.append(f"escalation trigger missed total exceeded: {trigger_missed_total} > {int(max_trigger_missed_total)}")
    if false_positive_rate > max(0.0, float(max_false_positive_rate)):
        failures.append(
            f"escalation trigger false-positive rate exceeded: {false_positive_rate:.4f} > {float(max_false_positive_rate):.4f}"
        )
    if threshold_version_missing_total > max(0, int(max_threshold_version_missing_total)):
        failures.append(
            "escalation trigger threshold-version-missing total exceeded: "
            f"{threshold_version_missing_total} > {int(max_threshold_version_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"escalation trigger stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Escalation Trigger Engine Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- trigger_recall: {_safe_float(summary.get('trigger_recall'), 0.0):.4f}")
    lines.append(f"- false_positive_rate: {_safe_float(summary.get('false_positive_rate'), 0.0):.4f}")
    lines.append(f"- trigger_missed_total: {_safe_int(summary.get('trigger_missed_total'), 0)}")
    lines.append(f"- cooldown_suppressed_total: {_safe_int(summary.get('cooldown_suppressed_total'), 0)}")
    lines.append(f"- hysteresis_suppressed_total: {_safe_int(summary.get('hysteresis_suppressed_total'), 0)}")
    lines.append(f"- threshold_version_missing_total: {_safe_int(summary.get('threshold_version_missing_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate escalation trigger engine quality.")
    parser.add_argument("--events-jsonl", default="var/dialog_planner/escalation_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_escalation_trigger_engine_guard")
    parser.add_argument("--failure-threshold", type=int, default=3)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-trigger-recall", type=float, default=0.0)
    parser.add_argument("--max-trigger-missed-total", type=int, default=1000000)
    parser.add_argument("--max-false-positive-rate", type=float, default=1.0)
    parser.add_argument("--max-threshold-version-missing-total", type=int, default=1000000)
    parser.add_argument("--max-stale-minutes", type=float, default=1000000.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_escalation_trigger_engine_guard(
        rows,
        failure_threshold=max(1, int(args.failure_threshold)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_trigger_recall=max(0.0, float(args.min_trigger_recall)),
        max_trigger_missed_total=max(0, int(args.max_trigger_missed_total)),
        max_false_positive_rate=max(0.0, float(args.max_false_positive_rate)),
        max_threshold_version_missing_total=max(0, int(args.max_threshold_version_missing_total)),
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
                "failure_threshold": int(args.failure_threshold),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_trigger_recall": float(args.min_trigger_recall),
                "max_trigger_missed_total": int(args.max_trigger_missed_total),
                "max_false_positive_rate": float(args.max_false_positive_rate),
                "max_threshold_version_missing_total": int(args.max_threshold_version_missing_total),
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
    print(f"trigger_recall={_safe_float(summary.get('trigger_recall'), 0.0):.4f}")
    print(f"false_positive_rate={_safe_float(summary.get('false_positive_rate'), 0.0):.4f}")
    print(f"trigger_missed_total={_safe_int(summary.get('trigger_missed_total'), 0)}")
    print(f"threshold_version_missing_total={_safe_int(summary.get('threshold_version_missing_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
