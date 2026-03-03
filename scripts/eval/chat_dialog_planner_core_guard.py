#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


VALID_TRANSITIONS: dict[str, set[str]] = {
    "INIT": {"ASK", "CONFIRM", "JUDGE", "ESCALATE"},
    "ASK": {"ASK", "CONFIRM", "JUDGE", "ESCALATE"},
    "CONFIRM": {"ASK", "JUDGE", "EXECUTE", "ESCALATE"},
    "JUDGE": {"ASK", "EXECUTE", "ESCALATE"},
    "EXECUTE": {"VERIFY", "ESCALATE"},
    "VERIFY": {"DONE", "ASK", "ESCALATE"},
    "DONE": set(),
    "ESCALATE": set(),
}

QUESTION_STRATEGIES = {
    "ASK_MISSING_SLOT",
    "ASK_CLARIFICATION",
    "ASK_ORDER_ID",
    "ASK_CONFIRMATION",
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


def _state_value(value: Any) -> str:
    return str(value or "").strip().upper()


def _from_state(row: Mapping[str, Any]) -> str:
    return _state_value(row.get("from_state") or row.get("state_from"))


def _to_state(row: Mapping[str, Any]) -> str:
    return _state_value(row.get("to_state") or row.get("state_to"))


def _transition_event(row: Mapping[str, Any]) -> bool:
    if row.get("transition_event") is not None:
        return _safe_bool(row.get("transition_event"))
    return bool(_from_state(row) and _to_state(row))


def _transition_valid(row: Mapping[str, Any]) -> bool:
    if row.get("transition_valid") is not None:
        return _safe_bool(row.get("transition_valid"))
    src = _from_state(row)
    dst = _to_state(row)
    if not src or not dst:
        return False
    allowed = VALID_TRANSITIONS.get(src)
    if allowed is None:
        return False
    return dst in allowed


def _policy_blocked(row: Mapping[str, Any]) -> bool:
    if row.get("policy_blocked") is not None:
        return _safe_bool(row.get("policy_blocked"))
    return not _safe_bool(row.get("policy_guard_passed", True))


def _transition_succeeded(row: Mapping[str, Any]) -> bool:
    status = _state_value(row.get("transition_result") or row.get("result"))
    if status:
        return status in {"SUCCESS", "OK", "APPLIED", "EXECUTED"}
    return _safe_bool(row.get("transition_succeeded"))


def _required_slots(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("required_slots")
    if isinstance(raw, list):
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    text = str(row.get("required_slot_names") or "").strip()
    if not text:
        return set()
    return {item.strip().lower() for item in text.split(",") if item.strip()}


def _provided_slots(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("provided_slots")
    if isinstance(raw, list):
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    slots = row.get("slots")
    if isinstance(slots, Mapping):
        return {str(key).strip().lower() for key in slots.keys() if str(key).strip()}
    text = str(row.get("provided_slot_names") or "").strip()
    if not text:
        return set()
    return {item.strip().lower() for item in text.split(",") if item.strip()}


def _question_strategy_applied(row: Mapping[str, Any]) -> bool:
    if row.get("question_strategy_applied") is not None:
        return _safe_bool(row.get("question_strategy_applied"))
    if _safe_bool(row.get("slot_question_asked")):
        return True
    strategy = _state_value(row.get("question_strategy"))
    return strategy in QUESTION_STRATEGIES


def summarize_dialog_planner_core_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    transition_total = 0
    valid_transition_total = 0
    invalid_transition_total = 0
    policy_blocked_total = 0
    policy_block_violation_total = 0
    missing_required_slots_total = 0
    question_strategy_applied_total = 0
    missing_slot_question_missing_total = 0
    planner_path_deviation_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        if not _transition_event(row):
            continue
        transition_total += 1

        valid_transition = _transition_valid(row)
        if valid_transition:
            valid_transition_total += 1
        else:
            invalid_transition_total += 1
            planner_path_deviation_total += 1

        policy_blocked = _policy_blocked(row)
        if policy_blocked:
            policy_blocked_total += 1
            if _transition_succeeded(row):
                policy_block_violation_total += 1

        required = _required_slots(row)
        provided = _provided_slots(row)
        missing = {slot for slot in required if slot not in provided}
        if missing:
            missing_required_slots_total += 1
            question_applied = _question_strategy_applied(row)
            if question_applied:
                question_strategy_applied_total += 1
            else:
                missing_slot_question_missing_total += 1

        if _safe_bool(row.get("path_deviation")):
            planner_path_deviation_total += 1

    valid_transition_ratio = 1.0 if transition_total == 0 else float(valid_transition_total) / float(transition_total)
    missing_slot_question_coverage_ratio = (
        1.0
        if missing_required_slots_total == 0
        else float(question_strategy_applied_total) / float(missing_required_slots_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "transition_total": transition_total,
        "valid_transition_total": valid_transition_total,
        "valid_transition_ratio": valid_transition_ratio,
        "invalid_transition_total": invalid_transition_total,
        "policy_blocked_total": policy_blocked_total,
        "policy_block_violation_total": policy_block_violation_total,
        "missing_required_slots_total": missing_required_slots_total,
        "question_strategy_applied_total": question_strategy_applied_total,
        "missing_slot_question_missing_total": missing_slot_question_missing_total,
        "missing_slot_question_coverage_ratio": missing_slot_question_coverage_ratio,
        "planner_path_deviation_total": planner_path_deviation_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_valid_transition_ratio: float,
    min_missing_slot_question_coverage_ratio: float,
    max_invalid_transition_total: int,
    max_policy_block_violation_total: int,
    max_missing_slot_question_missing_total: int,
    max_planner_path_deviation_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    valid_transition_ratio = _safe_float(summary.get("valid_transition_ratio"), 0.0)
    missing_slot_question_coverage_ratio = _safe_float(summary.get("missing_slot_question_coverage_ratio"), 0.0)
    invalid_transition_total = _safe_int(summary.get("invalid_transition_total"), 0)
    policy_block_violation_total = _safe_int(summary.get("policy_block_violation_total"), 0)
    missing_slot_question_missing_total = _safe_int(summary.get("missing_slot_question_missing_total"), 0)
    planner_path_deviation_total = _safe_int(summary.get("planner_path_deviation_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"dialog planner window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"dialog planner event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if valid_transition_ratio < max(0.0, float(min_valid_transition_ratio)):
        failures.append(
            f"dialog planner valid transition ratio below minimum: {valid_transition_ratio:.4f} < {float(min_valid_transition_ratio):.4f}"
        )
    if missing_slot_question_coverage_ratio < max(0.0, float(min_missing_slot_question_coverage_ratio)):
        failures.append(
            "dialog planner missing-slot question coverage ratio below minimum: "
            f"{missing_slot_question_coverage_ratio:.4f} < {float(min_missing_slot_question_coverage_ratio):.4f}"
        )
    if invalid_transition_total > max(0, int(max_invalid_transition_total)):
        failures.append(f"dialog planner invalid transition total exceeded: {invalid_transition_total} > {int(max_invalid_transition_total)}")
    if policy_block_violation_total > max(0, int(max_policy_block_violation_total)):
        failures.append(
            f"dialog planner policy block violation total exceeded: {policy_block_violation_total} > {int(max_policy_block_violation_total)}"
        )
    if missing_slot_question_missing_total > max(0, int(max_missing_slot_question_missing_total)):
        failures.append(
            "dialog planner missing-slot question missing total exceeded: "
            f"{missing_slot_question_missing_total} > {int(max_missing_slot_question_missing_total)}"
        )
    if planner_path_deviation_total > max(0, int(max_planner_path_deviation_total)):
        failures.append(
            f"dialog planner path deviation total exceeded: {planner_path_deviation_total} > {int(max_planner_path_deviation_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"dialog planner stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Dialog Planner Core Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- valid_transition_ratio: {_safe_float(summary.get('valid_transition_ratio'), 0.0):.4f}")
    lines.append(
        "- missing_slot_question_coverage_ratio: "
        f"{_safe_float(summary.get('missing_slot_question_coverage_ratio'), 0.0):.4f}"
    )
    lines.append(f"- invalid_transition_total: {_safe_int(summary.get('invalid_transition_total'), 0)}")
    lines.append(f"- policy_block_violation_total: {_safe_int(summary.get('policy_block_violation_total'), 0)}")
    lines.append(
        f"- missing_slot_question_missing_total: {_safe_int(summary.get('missing_slot_question_missing_total'), 0)}"
    )
    lines.append(f"- planner_path_deviation_total: {_safe_int(summary.get('planner_path_deviation_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate dialog planner core transition quality.")
    parser.add_argument("--events-jsonl", default="var/dialog_planner/transition_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_dialog_planner_core_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-valid-transition-ratio", type=float, default=0.0)
    parser.add_argument("--min-missing-slot-question-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-invalid-transition-total", type=int, default=1000000)
    parser.add_argument("--max-policy-block-violation-total", type=int, default=1000000)
    parser.add_argument("--max-missing-slot-question-missing-total", type=int, default=1000000)
    parser.add_argument("--max-planner-path-deviation-total", type=int, default=1000000)
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
    summary = summarize_dialog_planner_core_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_valid_transition_ratio=max(0.0, float(args.min_valid_transition_ratio)),
        min_missing_slot_question_coverage_ratio=max(0.0, float(args.min_missing_slot_question_coverage_ratio)),
        max_invalid_transition_total=max(0, int(args.max_invalid_transition_total)),
        max_policy_block_violation_total=max(0, int(args.max_policy_block_violation_total)),
        max_missing_slot_question_missing_total=max(0, int(args.max_missing_slot_question_missing_total)),
        max_planner_path_deviation_total=max(0, int(args.max_planner_path_deviation_total)),
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
                "min_valid_transition_ratio": float(args.min_valid_transition_ratio),
                "min_missing_slot_question_coverage_ratio": float(args.min_missing_slot_question_coverage_ratio),
                "max_invalid_transition_total": int(args.max_invalid_transition_total),
                "max_policy_block_violation_total": int(args.max_policy_block_violation_total),
                "max_missing_slot_question_missing_total": int(args.max_missing_slot_question_missing_total),
                "max_planner_path_deviation_total": int(args.max_planner_path_deviation_total),
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
    print(f"valid_transition_ratio={_safe_float(summary.get('valid_transition_ratio'), 0.0):.4f}")
    print(f"missing_slot_question_coverage_ratio={_safe_float(summary.get('missing_slot_question_coverage_ratio'), 0.0):.4f}")
    print(f"invalid_transition_total={_safe_int(summary.get('invalid_transition_total'), 0)}")
    print(f"policy_block_violation_total={_safe_int(summary.get('policy_block_violation_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
