#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


STATE_HEALTHY = "HEALTHY"
STATE_AT_RISK = "AT_RISK"
STATE_DEGRADED = "DEGRADED"

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATE_HEALTHY: {STATE_HEALTHY, STATE_AT_RISK},
    STATE_AT_RISK: {STATE_HEALTHY, STATE_AT_RISK, STATE_DEGRADED},
    STATE_DEGRADED: {STATE_DEGRADED, STATE_AT_RISK},
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


def _session_id(row: Mapping[str, Any], fallback_index: int) -> str:
    session_id = str(row.get("session_id") or row.get("conversation_id") or "").strip()
    if session_id:
        return session_id
    return f"_missing_session_{fallback_index}"


def _normalize_state(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {STATE_HEALTHY, STATE_AT_RISK, STATE_DEGRADED}:
        return text
    return ""


def _classify_state(row: Mapping[str, Any]) -> str:
    explicit = _normalize_state(row.get("session_state"))
    if explicit:
        return explicit
    score = _safe_float(row.get("session_quality_score"), _safe_float(row.get("quality_score"), 0.0))
    consecutive_failures = _safe_int(row.get("consecutive_failures"), 0)
    if consecutive_failures >= 3:
        return STATE_DEGRADED
    if score >= 0.75:
        return STATE_HEALTHY
    if score >= 0.45:
        return STATE_AT_RISK
    return STATE_DEGRADED


def _expected_state(row: Mapping[str, Any]) -> str:
    return _normalize_state(row.get("expected_state"))


def summarize_session_state_transition_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    classified_total = 0
    state_healthy_total = 0
    state_at_risk_total = 0
    state_degraded_total = 0
    state_mismatch_total = 0
    invalid_transition_total = 0
    false_alarm_total = 0

    timeline: list[tuple[datetime, str, str, Mapping[str, Any]]] = []
    for idx, row in enumerate(rows):
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        session_id = _session_id(row, idx)
        state = _classify_state(row)
        classified_total += 1
        if state == STATE_HEALTHY:
            state_healthy_total += 1
        elif state == STATE_AT_RISK:
            state_at_risk_total += 1
        elif state == STATE_DEGRADED:
            state_degraded_total += 1

        expected = _expected_state(row)
        if expected and expected != state:
            state_mismatch_total += 1
        if _safe_bool(row.get("false_alarm")):
            false_alarm_total += 1

        timeline.append((ts or datetime.min.replace(tzinfo=timezone.utc), session_id, state, row))

    timeline.sort(key=lambda item: (item[1], item[0]))
    prev_state_by_session: dict[str, str] = {}
    for _, session_id, state, row in timeline:
        prev = prev_state_by_session.get(session_id)
        if prev:
            if prev == STATE_DEGRADED and state == STATE_HEALTHY and not _safe_bool(row.get("recovery_confirmed")):
                invalid_transition_total += 1
            elif state not in ALLOWED_TRANSITIONS.get(prev, {STATE_HEALTHY, STATE_AT_RISK, STATE_DEGRADED}):
                invalid_transition_total += 1
        prev_state_by_session[session_id] = state

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)
    return {
        "window_size": len(rows),
        "event_total": event_total,
        "classified_total": classified_total,
        "state_healthy_total": state_healthy_total,
        "state_at_risk_total": state_at_risk_total,
        "state_degraded_total": state_degraded_total,
        "state_mismatch_total": state_mismatch_total,
        "invalid_transition_total": invalid_transition_total,
        "false_alarm_total": false_alarm_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    max_state_mismatch_total: int,
    max_invalid_transition_total: int,
    max_false_alarm_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    state_mismatch_total = _safe_int(summary.get("state_mismatch_total"), 0)
    invalid_transition_total = _safe_int(summary.get("invalid_transition_total"), 0)
    false_alarm_total = _safe_int(summary.get("false_alarm_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"session state window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"session state event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if state_mismatch_total > max(0, int(max_state_mismatch_total)):
        failures.append(
            f"session state mismatch total exceeded: {state_mismatch_total} > {int(max_state_mismatch_total)}"
        )
    if invalid_transition_total > max(0, int(max_invalid_transition_total)):
        failures.append(
            f"session state invalid transition total exceeded: {invalid_transition_total} > {int(max_invalid_transition_total)}"
        )
    if false_alarm_total > max(0, int(max_false_alarm_total)):
        failures.append(f"session state false alarm total exceeded: {false_alarm_total} > {int(max_false_alarm_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"session state stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Session State Transition Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- state_healthy_total: {_safe_int(summary.get('state_healthy_total'), 0)}")
    lines.append(f"- state_at_risk_total: {_safe_int(summary.get('state_at_risk_total'), 0)}")
    lines.append(f"- state_degraded_total: {_safe_int(summary.get('state_degraded_total'), 0)}")
    lines.append(f"- invalid_transition_total: {_safe_int(summary.get('invalid_transition_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate session state transition quality.")
    parser.add_argument("--events-jsonl", default="var/session_quality/session_state_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_session_state_transition_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--max-state-mismatch-total", type=int, default=1000000)
    parser.add_argument("--max-invalid-transition-total", type=int, default=1000000)
    parser.add_argument("--max-false-alarm-total", type=int, default=1000000)
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
    summary = summarize_session_state_transition_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        max_state_mismatch_total=max(0, int(args.max_state_mismatch_total)),
        max_invalid_transition_total=max(0, int(args.max_invalid_transition_total)),
        max_false_alarm_total=max(0, int(args.max_false_alarm_total)),
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
                "max_state_mismatch_total": int(args.max_state_mismatch_total),
                "max_invalid_transition_total": int(args.max_invalid_transition_total),
                "max_false_alarm_total": int(args.max_false_alarm_total),
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
    print(f"event_total={_safe_int(summary.get('event_total'), 0)}")
    print(f"state_healthy_total={_safe_int(summary.get('state_healthy_total'), 0)}")
    print(f"state_at_risk_total={_safe_int(summary.get('state_at_risk_total'), 0)}")
    print(f"state_degraded_total={_safe_int(summary.get('state_degraded_total'), 0)}")
    print(f"invalid_transition_total={_safe_int(summary.get('invalid_transition_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
