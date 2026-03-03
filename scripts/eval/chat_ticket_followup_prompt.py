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


def _ticket_ref(row: Mapping[str, Any]) -> str:
    for key in ("ticket_no", "ticket_id", "id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def _normalize_event(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "status_transition": "STATUS_TRANSITION",
        "ticket_status_transition": "STATUS_TRANSITION",
        "status_changed": "STATUS_TRANSITION",
        "followup_prompt": "FOLLOWUP_PROMPT",
        "ticket_followup_prompt": "FOLLOWUP_PROMPT",
        "reminder_sent": "REMINDER_SENT",
        "ticket_reminder_sent": "REMINDER_SENT",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().upper()


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


def summarize_followup_prompt(
    events: list[Mapping[str, Any]],
    *,
    reminder_threshold_hours: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    transitions: dict[str, list[dict[str, Any]]] = {}
    prompts: dict[str, list[dict[str, Any]]] = {}
    reminders: dict[str, list[datetime]] = {}

    followup_prompt_total = 0
    prompt_missing_action_total = 0
    waiting_user_transition_total = 0
    reminder_due_total = 0

    for row in events:
        ticket = _ticket_ref(row)
        if not ticket:
            continue
        event = _normalize_event(row.get("event_type") or row.get("event") or row.get("status_event"))
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if event == "STATUS_TRANSITION":
            to_status = _normalize_status(row.get("to_status") or row.get("status"))
            waiting_hours = _safe_float(row.get("waiting_hours"), -1.0)
            transition = {"to_status": to_status, "ts": ts, "waiting_hours": waiting_hours}
            transitions.setdefault(ticket, []).append(transition)
            if to_status == "WAITING_USER":
                waiting_user_transition_total += 1
                if waiting_hours >= float(reminder_threshold_hours):
                    reminder_due_total += 1
        elif event == "FOLLOWUP_PROMPT":
            followup_prompt_total += 1
            status = _normalize_status(row.get("status") or row.get("ticket_status") or row.get("for_status"))
            guidance = str(row.get("guidance_text") or row.get("message") or "").strip()
            action = str(row.get("recommended_action") or row.get("next_action") or "").strip()
            prompts.setdefault(ticket, []).append({"status": status, "ts": ts})
            if not guidance and not action:
                prompt_missing_action_total += 1
        elif event == "REMINDER_SENT":
            reminders.setdefault(ticket, []).append(ts if ts is not None else datetime.min.replace(tzinfo=timezone.utc))

    waiting_user_prompt_covered_total = 0
    reminder_sent_on_due_total = 0

    for ticket, rows in transitions.items():
        prompt_rows = prompts.get(ticket, [])
        reminder_rows = reminders.get(ticket, [])
        for row in rows:
            to_status = str(row.get("to_status") or "")
            ts = row.get("ts")
            if to_status == "WAITING_USER":
                has_prompt = False
                for prompt in prompt_rows:
                    prompt_ts = prompt.get("ts")
                    prompt_status = str(prompt.get("status") or "")
                    if prompt_status == "WAITING_USER":
                        if isinstance(ts, datetime) and isinstance(prompt_ts, datetime):
                            if prompt_ts >= ts:
                                has_prompt = True
                                break
                        else:
                            has_prompt = True
                            break
                if has_prompt:
                    waiting_user_prompt_covered_total += 1

                waiting_hours = _safe_float(row.get("waiting_hours"), -1.0)
                if waiting_hours >= float(reminder_threshold_hours):
                    has_reminder = False
                    for reminder_ts in reminder_rows:
                        if isinstance(ts, datetime) and isinstance(reminder_ts, datetime):
                            if reminder_ts >= ts:
                                has_reminder = True
                                break
                        else:
                            has_reminder = True
                            break
                    if has_reminder:
                        reminder_sent_on_due_total += 1

    waiting_user_prompt_coverage_ratio = (
        1.0
        if waiting_user_transition_total == 0
        else float(waiting_user_prompt_covered_total) / float(waiting_user_transition_total)
    )
    reminder_due_coverage_ratio = 1.0 if reminder_due_total == 0 else float(reminder_sent_on_due_total) / float(reminder_due_total)

    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "ticket_total": len(transitions),
        "followup_prompt_total": followup_prompt_total,
        "prompt_missing_action_total": prompt_missing_action_total,
        "waiting_user_transition_total": waiting_user_transition_total,
        "waiting_user_prompt_covered_total": waiting_user_prompt_covered_total,
        "waiting_user_prompt_coverage_ratio": waiting_user_prompt_coverage_ratio,
        "reminder_due_total": reminder_due_total,
        "reminder_sent_on_due_total": reminder_sent_on_due_total,
        "reminder_due_coverage_ratio": reminder_due_coverage_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_prompt_missing_action_total: int,
    min_waiting_user_prompt_coverage_ratio: float,
    min_reminder_due_coverage_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    prompt_missing_action_total = _safe_int(summary.get("prompt_missing_action_total"), 0)
    waiting_user_prompt_coverage_ratio = _safe_float(summary.get("waiting_user_prompt_coverage_ratio"), 1.0)
    reminder_due_coverage_ratio = _safe_float(summary.get("reminder_due_coverage_ratio"), 1.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket follow-up window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if prompt_missing_action_total > max(0, int(max_prompt_missing_action_total)):
        failures.append(
            f"follow-up prompt missing action total exceeded: {prompt_missing_action_total} > {int(max_prompt_missing_action_total)}"
        )
    if waiting_user_prompt_coverage_ratio < max(0.0, float(min_waiting_user_prompt_coverage_ratio)):
        failures.append(
            "waiting_user prompt coverage ratio below threshold: "
            f"{waiting_user_prompt_coverage_ratio:.4f} < {float(min_waiting_user_prompt_coverage_ratio):.4f}"
        )
    if reminder_due_coverage_ratio < max(0.0, float(min_reminder_due_coverage_ratio)):
        failures.append(
            f"reminder due coverage ratio below threshold: {reminder_due_coverage_ratio:.4f} < {float(min_reminder_due_coverage_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket follow-up events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Ticket Follow-up Prompt")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- followup_prompt_total: {_safe_int(summary.get('followup_prompt_total'), 0)}")
    lines.append(f"- waiting_user_transition_total: {_safe_int(summary.get('waiting_user_transition_total'), 0)}")
    lines.append(
        f"- waiting_user_prompt_coverage_ratio: {_safe_float(summary.get('waiting_user_prompt_coverage_ratio'), 1.0):.4f}"
    )
    lines.append(f"- reminder_due_coverage_ratio: {_safe_float(summary.get('reminder_due_coverage_ratio'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate ticket follow-up prompt and reminder policy.")
    parser.add_argument("--events-jsonl", default="var/chat_ticket/ticket_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--reminder-threshold-hours", type=float, default=24.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_followup_prompt")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-prompt-missing-action-total", type=int, default=0)
    parser.add_argument("--min-waiting-user-prompt-coverage-ratio", type=float, default=0.95)
    parser.add_argument("--min-reminder-due-coverage-ratio", type=float, default=0.90)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    events_path = Path(args.events_jsonl)
    events = read_events(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_followup_prompt(
        events,
        reminder_threshold_hours=max(0.0, float(args.reminder_threshold_hours)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_prompt_missing_action_total=max(0, int(args.max_prompt_missing_action_total)),
        min_waiting_user_prompt_coverage_ratio=max(0.0, float(args.min_waiting_user_prompt_coverage_ratio)),
        min_reminder_due_coverage_ratio=max(0.0, float(args.min_reminder_due_coverage_ratio)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_prompt_missing_action_total": int(args.max_prompt_missing_action_total),
                "min_waiting_user_prompt_coverage_ratio": float(args.min_waiting_user_prompt_coverage_ratio),
                "min_reminder_due_coverage_ratio": float(args.min_reminder_due_coverage_ratio),
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
    print(f"waiting_user_transition_total={_safe_int(summary.get('waiting_user_transition_total'), 0)}")
    print(f"followup_prompt_total={_safe_int(summary.get('followup_prompt_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
