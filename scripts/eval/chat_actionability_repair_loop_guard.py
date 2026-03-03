#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


INTENT_CUTLINES: dict[str, float] = {
    "ORDER": 0.75,
    "SHIPPING": 0.75,
    "REFUND": 0.85,
    "GENERAL": 0.60,
}

FAIL_CLOSED_ACTIONS = {"OPEN_SUPPORT_TICKET", "ESCALATE_TO_HUMAN"}


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


def _intent_bucket(row: Mapping[str, Any]) -> str:
    raw = str(row.get("intent") or row.get("intent_name") or row.get("intent_bucket") or "").upper()
    if "REFUND" in raw or "RETURN" in raw:
        return "REFUND"
    if "SHIP" in raw or "DELIVERY" in raw or "TRACK" in raw:
        return "SHIPPING"
    if "ORDER" in raw or "CANCEL" in raw or "PAY" in raw:
        return "ORDER"
    return "GENERAL"


def _normalize_score(value: Any) -> float | None:
    if value is None:
        return None
    score = _safe_float(value, -1.0)
    if score < 0.0:
        return None
    if score > 1.0:
        if score <= 100.0:
            score = score / 100.0
        else:
            score = 1.0
    return max(0.0, min(1.0, score))


def _repair_required(row: Mapping[str, Any]) -> bool:
    if row.get("repair_required") is not None:
        return _safe_bool(row.get("repair_required"))
    if row.get("low_actionability") is not None:
        return _safe_bool(row.get("low_actionability"))
    score = _normalize_score(row.get("actionability_score_before"))
    if score is None:
        score = _normalize_score(row.get("actionability_score"))
    if score is None:
        return False
    bucket = _intent_bucket(row)
    cutline = INTENT_CUTLINES.get(bucket, INTENT_CUTLINES["GENERAL"])
    return score < cutline


def _repair_attempts(row: Mapping[str, Any]) -> int:
    raw = row.get("repair_attempts")
    if raw is not None:
        return max(0, _safe_int(raw, 0))
    attempts = row.get("repair_attempt_log")
    if isinstance(attempts, list):
        return len(attempts)
    return 0


def _repair_triggered(row: Mapping[str, Any]) -> bool:
    if row.get("repair_triggered") is not None:
        return _safe_bool(row.get("repair_triggered"))
    return _repair_attempts(row) > 0


def _repair_result(row: Mapping[str, Any]) -> str:
    return str(row.get("repair_result") or row.get("result") or "").strip().upper()


def _repair_success(row: Mapping[str, Any]) -> bool:
    if row.get("repair_success") is not None:
        return _safe_bool(row.get("repair_success"))
    result = _repair_result(row)
    if result in {"SUCCESS", "RECOVERED", "PASS"}:
        return True
    score_after = _normalize_score(row.get("actionability_score_after"))
    if score_after is None:
        return False
    bucket = _intent_bucket(row)
    cutline = INTENT_CUTLINES.get(bucket, INTENT_CUTLINES["GENERAL"])
    return score_after >= cutline


def _repair_failed(row: Mapping[str, Any]) -> bool:
    if row.get("repair_failed") is not None:
        return _safe_bool(row.get("repair_failed"))
    result = _repair_result(row)
    if result in {"FAILED", "FAIL_CLOSED", "EXHAUSTED", "ERROR"}:
        return True
    return _repair_triggered(row) and not _repair_success(row) and _repair_attempts(row) >= 2


def _fail_closed(row: Mapping[str, Any]) -> bool:
    if row.get("fail_closed_enforced") is not None:
        return _safe_bool(row.get("fail_closed_enforced"))
    result = _repair_result(row)
    if result == "FAIL_CLOSED":
        return True
    next_action = str(row.get("next_action") or "").strip().upper()
    return next_action in FAIL_CLOSED_ACTIONS


def _missing_slots_before(row: Mapping[str, Any]) -> int:
    slots = row.get("missing_slots_before")
    if isinstance(slots, list):
        return len(slots)
    return max(0, _safe_int(row.get("missing_slot_count_before"), 0))


def _missing_slots_after(row: Mapping[str, Any]) -> int:
    slots = row.get("missing_slots_after")
    if isinstance(slots, list):
        return len(slots)
    return max(0, _safe_int(row.get("missing_slot_count_after"), 0))


def summarize_actionability_repair_loop_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    max_repair_attempts: int = 2,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    repair_required_total = 0
    repair_triggered_total = 0
    repair_success_total = 0
    repair_failed_total = 0
    repair_fail_closed_total = 0
    repair_trigger_missing_total = 0
    fail_closed_missing_total = 0
    attempt_limit_violation_total = 0
    slot_gap_before_total = 0
    slot_gap_after_total = 0
    slot_gap_reduced_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        required = _repair_required(row)
        triggered = _repair_triggered(row)
        attempts = _repair_attempts(row)
        success = _repair_success(row)
        failed = _repair_failed(row)
        fail_closed = _fail_closed(row)

        if required:
            repair_required_total += 1
            if not triggered:
                repair_trigger_missing_total += 1

        if triggered:
            repair_triggered_total += 1
            before = _missing_slots_before(row)
            after = _missing_slots_after(row)
            slot_gap_before_total += before
            slot_gap_after_total += after
            if after < before:
                slot_gap_reduced_total += 1

        if success:
            repair_success_total += 1
        if failed:
            repair_failed_total += 1
            if fail_closed:
                repair_fail_closed_total += 1
            else:
                fail_closed_missing_total += 1

        if attempts > max(0, int(max_repair_attempts)):
            attempt_limit_violation_total += 1

    repair_trigger_coverage_ratio = 1.0 if repair_required_total == 0 else float(repair_triggered_total) / float(repair_required_total)
    repair_success_rate = 1.0 if repair_triggered_total == 0 else float(repair_success_total) / float(repair_triggered_total)
    fail_closed_enforcement_ratio = (
        1.0 if repair_failed_total == 0 else float(repair_fail_closed_total) / float(repair_failed_total)
    )
    slot_gap_reduction_ratio = (
        1.0 if repair_triggered_total == 0 else float(slot_gap_reduced_total) / float(repair_triggered_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "repair_required_total": repair_required_total,
        "repair_triggered_total": repair_triggered_total,
        "repair_trigger_coverage_ratio": repair_trigger_coverage_ratio,
        "repair_success_total": repair_success_total,
        "repair_success_rate": repair_success_rate,
        "repair_failed_total": repair_failed_total,
        "repair_fail_closed_total": repair_fail_closed_total,
        "fail_closed_enforcement_ratio": fail_closed_enforcement_ratio,
        "repair_trigger_missing_total": repair_trigger_missing_total,
        "fail_closed_missing_total": fail_closed_missing_total,
        "attempt_limit_violation_total": attempt_limit_violation_total,
        "slot_gap_before_total": slot_gap_before_total,
        "slot_gap_after_total": slot_gap_after_total,
        "slot_gap_reduced_total": slot_gap_reduced_total,
        "slot_gap_reduction_ratio": slot_gap_reduction_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_repair_trigger_coverage_ratio: float,
    min_repair_success_rate: float,
    min_fail_closed_enforcement_ratio: float,
    min_slot_gap_reduction_ratio: float,
    max_repair_trigger_missing_total: int,
    max_fail_closed_missing_total: int,
    max_attempt_limit_violation_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    repair_trigger_coverage_ratio = _safe_float(summary.get("repair_trigger_coverage_ratio"), 0.0)
    repair_success_rate = _safe_float(summary.get("repair_success_rate"), 0.0)
    fail_closed_enforcement_ratio = _safe_float(summary.get("fail_closed_enforcement_ratio"), 0.0)
    slot_gap_reduction_ratio = _safe_float(summary.get("slot_gap_reduction_ratio"), 0.0)
    repair_trigger_missing_total = _safe_int(summary.get("repair_trigger_missing_total"), 0)
    fail_closed_missing_total = _safe_int(summary.get("fail_closed_missing_total"), 0)
    attempt_limit_violation_total = _safe_int(summary.get("attempt_limit_violation_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"actionability repair window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"actionability repair event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if repair_trigger_coverage_ratio < max(0.0, float(min_repair_trigger_coverage_ratio)):
        failures.append(
            "actionability repair trigger coverage ratio below minimum: "
            f"{repair_trigger_coverage_ratio:.4f} < {float(min_repair_trigger_coverage_ratio):.4f}"
        )
    if repair_success_rate < max(0.0, float(min_repair_success_rate)):
        failures.append(
            f"actionability repair success rate below minimum: {repair_success_rate:.4f} < {float(min_repair_success_rate):.4f}"
        )
    if fail_closed_enforcement_ratio < max(0.0, float(min_fail_closed_enforcement_ratio)):
        failures.append(
            "actionability repair fail-closed enforcement ratio below minimum: "
            f"{fail_closed_enforcement_ratio:.4f} < {float(min_fail_closed_enforcement_ratio):.4f}"
        )
    if slot_gap_reduction_ratio < max(0.0, float(min_slot_gap_reduction_ratio)):
        failures.append(
            "actionability repair slot-gap reduction ratio below minimum: "
            f"{slot_gap_reduction_ratio:.4f} < {float(min_slot_gap_reduction_ratio):.4f}"
        )
    if repair_trigger_missing_total > max(0, int(max_repair_trigger_missing_total)):
        failures.append(
            f"actionability repair trigger-missing total exceeded: {repair_trigger_missing_total} > {int(max_repair_trigger_missing_total)}"
        )
    if fail_closed_missing_total > max(0, int(max_fail_closed_missing_total)):
        failures.append(
            f"actionability repair fail-closed-missing total exceeded: {fail_closed_missing_total} > {int(max_fail_closed_missing_total)}"
        )
    if attempt_limit_violation_total > max(0, int(max_attempt_limit_violation_total)):
        failures.append(
            "actionability repair attempt-limit violation exceeded: "
            f"{attempt_limit_violation_total} > {int(max_attempt_limit_violation_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"actionability repair stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Actionability Repair Loop Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- repair_trigger_coverage_ratio: {_safe_float(summary.get('repair_trigger_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- repair_success_rate: {_safe_float(summary.get('repair_success_rate'), 0.0):.4f}")
    lines.append(f"- fail_closed_enforcement_ratio: {_safe_float(summary.get('fail_closed_enforcement_ratio'), 0.0):.4f}")
    lines.append(f"- slot_gap_reduction_ratio: {_safe_float(summary.get('slot_gap_reduction_ratio'), 0.0):.4f}")
    lines.append(f"- repair_trigger_missing_total: {_safe_int(summary.get('repair_trigger_missing_total'), 0)}")
    lines.append(f"- fail_closed_missing_total: {_safe_int(summary.get('fail_closed_missing_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate actionability repair loop quality.")
    parser.add_argument("--events-jsonl", default="var/actionability/repair_loop_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_actionability_repair_loop_guard")
    parser.add_argument("--max-repair-attempts", type=int, default=2)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-repair-trigger-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-repair-success-rate", type=float, default=0.0)
    parser.add_argument("--min-fail-closed-enforcement-ratio", type=float, default=0.0)
    parser.add_argument("--min-slot-gap-reduction-ratio", type=float, default=0.0)
    parser.add_argument("--max-repair-trigger-missing-total", type=int, default=1000000)
    parser.add_argument("--max-fail-closed-missing-total", type=int, default=1000000)
    parser.add_argument("--max-attempt-limit-violation-total", type=int, default=1000000)
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
    summary = summarize_actionability_repair_loop_guard(
        rows,
        max_repair_attempts=max(0, int(args.max_repair_attempts)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_repair_trigger_coverage_ratio=max(0.0, float(args.min_repair_trigger_coverage_ratio)),
        min_repair_success_rate=max(0.0, float(args.min_repair_success_rate)),
        min_fail_closed_enforcement_ratio=max(0.0, float(args.min_fail_closed_enforcement_ratio)),
        min_slot_gap_reduction_ratio=max(0.0, float(args.min_slot_gap_reduction_ratio)),
        max_repair_trigger_missing_total=max(0, int(args.max_repair_trigger_missing_total)),
        max_fail_closed_missing_total=max(0, int(args.max_fail_closed_missing_total)),
        max_attempt_limit_violation_total=max(0, int(args.max_attempt_limit_violation_total)),
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
                "max_repair_attempts": int(args.max_repair_attempts),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_repair_trigger_coverage_ratio": float(args.min_repair_trigger_coverage_ratio),
                "min_repair_success_rate": float(args.min_repair_success_rate),
                "min_fail_closed_enforcement_ratio": float(args.min_fail_closed_enforcement_ratio),
                "min_slot_gap_reduction_ratio": float(args.min_slot_gap_reduction_ratio),
                "max_repair_trigger_missing_total": int(args.max_repair_trigger_missing_total),
                "max_fail_closed_missing_total": int(args.max_fail_closed_missing_total),
                "max_attempt_limit_violation_total": int(args.max_attempt_limit_violation_total),
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
    print(f"repair_trigger_coverage_ratio={_safe_float(summary.get('repair_trigger_coverage_ratio'), 0.0):.4f}")
    print(f"repair_success_rate={_safe_float(summary.get('repair_success_rate'), 0.0):.4f}")
    print(f"fail_closed_enforcement_ratio={_safe_float(summary.get('fail_closed_enforcement_ratio'), 0.0):.4f}")
    print(f"slot_gap_reduction_ratio={_safe_float(summary.get('slot_gap_reduction_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
