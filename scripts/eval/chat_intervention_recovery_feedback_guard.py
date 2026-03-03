#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


STATE_ORDER = {
    "DEGRADED": 0,
    "AT_RISK": 1,
    "HEALTHY": 2,
}

INEFFECTIVE_RESULTS = {
    "NO_EFFECT",
    "NEGATIVE",
    "FAILED",
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


def _normalize_state(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in STATE_ORDER:
        return text
    return ""


def _intervention_type(row: Mapping[str, Any]) -> str:
    return str(row.get("intervention_type") or "").strip().upper()


def _is_intervention_event(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("intervention_triggered")):
        return True
    return bool(_intervention_type(row))


def _completion_before_after(row: Mapping[str, Any]) -> tuple[float, float]:
    before = row.get("completion_before")
    if before is None:
        before = row.get("completion_rate_before")
    after = row.get("completion_after")
    if after is None:
        after = row.get("completion_rate_after")
    return max(0.0, min(1.0, _safe_float(before, 0.0))), max(0.0, min(1.0, _safe_float(after, 0.0)))


def _recovered(row: Mapping[str, Any]) -> bool:
    explicit = row.get("recovered")
    if explicit is not None:
        return _safe_bool(explicit)
    pre_state = _normalize_state(row.get("pre_state"))
    post_state = _normalize_state(row.get("post_state"))
    if pre_state and post_state:
        return STATE_ORDER.get(post_state, 0) > STATE_ORDER.get(pre_state, 0)
    result = str(row.get("intervention_result") or "").strip().upper()
    if result in {"RECOVERED", "SUCCESS", "IMPROVED"}:
        return True
    return False


def _ineffective(row: Mapping[str, Any], *, recovered: bool) -> bool:
    result = str(row.get("intervention_result") or "").strip().upper()
    if result in INEFFECTIVE_RESULTS:
        return True
    return not recovered


def summarize_intervention_recovery_feedback_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    decay_ineffective_streak_threshold: int = 3,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    intervention_total = 0
    recovered_total = 0
    completion_before_sum = 0.0
    completion_after_sum = 0.0
    feedback_missing_total = 0
    ineffective_total = 0
    auto_decay_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        if not _is_intervention_event(row):
            continue

        intervention_total += 1
        recovered = _recovered(row)
        if recovered:
            recovered_total += 1

        completion_before, completion_after = _completion_before_after(row)
        completion_before_sum += completion_before
        completion_after_sum += completion_after

        if not _safe_bool(row.get("feedback_logged")):
            feedback_missing_total += 1

        ineffective = _ineffective(row, recovered=recovered)
        if ineffective:
            ineffective_total += 1
            streak = _safe_int(row.get("ineffective_streak"), 0)
            decay_applied = _safe_bool(row.get("decay_applied")) or _safe_bool(row.get("weight_dampened"))
            if streak >= max(1, int(decay_ineffective_streak_threshold)) and not decay_applied:
                auto_decay_missing_total += 1

    recovery_rate = 1.0 if intervention_total == 0 else float(recovered_total) / float(intervention_total)
    mean_completion_before = 0.0 if intervention_total == 0 else completion_before_sum / float(intervention_total)
    mean_completion_after = 0.0 if intervention_total == 0 else completion_after_sum / float(intervention_total)
    completion_uplift = mean_completion_after - mean_completion_before
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "intervention_total": intervention_total,
        "recovered_total": recovered_total,
        "recovery_rate": recovery_rate,
        "mean_completion_before": mean_completion_before,
        "mean_completion_after": mean_completion_after,
        "completion_uplift": completion_uplift,
        "feedback_missing_total": feedback_missing_total,
        "ineffective_total": ineffective_total,
        "auto_decay_missing_total": auto_decay_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_recovery_rate: float,
    min_completion_uplift: float,
    max_feedback_missing_total: int,
    max_auto_decay_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    recovery_rate = _safe_float(summary.get("recovery_rate"), 0.0)
    completion_uplift = _safe_float(summary.get("completion_uplift"), 0.0)
    feedback_missing_total = _safe_int(summary.get("feedback_missing_total"), 0)
    auto_decay_missing_total = _safe_int(summary.get("auto_decay_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"intervention feedback window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"intervention feedback event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if recovery_rate < max(0.0, float(min_recovery_rate)):
        failures.append(f"intervention recovery rate below minimum: {recovery_rate:.4f} < {float(min_recovery_rate):.4f}")
    if completion_uplift < float(min_completion_uplift):
        failures.append(f"intervention completion uplift below minimum: {completion_uplift:.4f} < {float(min_completion_uplift):.4f}")
    if feedback_missing_total > max(0, int(max_feedback_missing_total)):
        failures.append(
            f"intervention feedback-missing total exceeded: {feedback_missing_total} > {int(max_feedback_missing_total)}"
        )
    if auto_decay_missing_total > max(0, int(max_auto_decay_missing_total)):
        failures.append(
            f"intervention auto-decay-missing total exceeded: {auto_decay_missing_total} > {int(max_auto_decay_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"intervention feedback stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Intervention Recovery Feedback Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- intervention_total: {_safe_int(summary.get('intervention_total'), 0)}")
    lines.append(f"- recovery_rate: {_safe_float(summary.get('recovery_rate'), 0.0):.4f}")
    lines.append(f"- completion_uplift: {_safe_float(summary.get('completion_uplift'), 0.0):.4f}")
    lines.append(f"- feedback_missing_total: {_safe_int(summary.get('feedback_missing_total'), 0)}")
    lines.append(f"- auto_decay_missing_total: {_safe_int(summary.get('auto_decay_missing_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate intervention recovery feedback loop.")
    parser.add_argument("--events-jsonl", default="var/session_quality/intervention_feedback_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_intervention_recovery_feedback_guard")
    parser.add_argument("--decay-ineffective-streak-threshold", type=int, default=3)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-recovery-rate", type=float, default=0.0)
    parser.add_argument("--min-completion-uplift", type=float, default=-1.0)
    parser.add_argument("--max-feedback-missing-total", type=int, default=1000000)
    parser.add_argument("--max-auto-decay-missing-total", type=int, default=1000000)
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
    summary = summarize_intervention_recovery_feedback_guard(
        rows,
        decay_ineffective_streak_threshold=max(1, int(args.decay_ineffective_streak_threshold)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_recovery_rate=max(0.0, float(args.min_recovery_rate)),
        min_completion_uplift=float(args.min_completion_uplift),
        max_feedback_missing_total=max(0, int(args.max_feedback_missing_total)),
        max_auto_decay_missing_total=max(0, int(args.max_auto_decay_missing_total)),
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
                "decay_ineffective_streak_threshold": int(args.decay_ineffective_streak_threshold),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_recovery_rate": float(args.min_recovery_rate),
                "min_completion_uplift": float(args.min_completion_uplift),
                "max_feedback_missing_total": int(args.max_feedback_missing_total),
                "max_auto_decay_missing_total": int(args.max_auto_decay_missing_total),
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
    print(f"intervention_total={_safe_int(summary.get('intervention_total'), 0)}")
    print(f"recovery_rate={_safe_float(summary.get('recovery_rate'), 0.0):.4f}")
    print(f"completion_uplift={_safe_float(summary.get('completion_uplift'), 0.0):.4f}")
    print(f"feedback_missing_total={_safe_int(summary.get('feedback_missing_total'), 0)}")
    print(f"auto_decay_missing_total={_safe_int(summary.get('auto_decay_missing_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
