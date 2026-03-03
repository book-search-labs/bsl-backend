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


def _resume_attempt(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("resume_attempt")):
        return True
    if _safe_bool(row.get("session_reentered")):
        return True
    event_type = str(row.get("event_type") or "").strip().upper()
    return event_type in {"SESSION_REENTRY", "PLAN_RESUME"}


def _plan_id_present(row: Mapping[str, Any]) -> bool:
    plan_id = str(row.get("plan_id") or row.get("resolution_plan_id") or "").strip()
    return bool(plan_id)


def _plan_state_restored(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("plan_state_restored")):
        return True
    if _safe_bool(row.get("plan_state_loaded")):
        return True
    status = str(row.get("resume_status") or "").strip().upper()
    return status == "RESTORED"


def _checkpoint_present(row: Mapping[str, Any]) -> bool:
    if row.get("checkpoint_index") is not None:
        return True
    if row.get("checkpoint_id") is not None:
        return True
    if row.get("resume_checkpoint") is not None:
        return True
    return False


def _failed_step_index(row: Mapping[str, Any]) -> int | None:
    if row.get("failed_step_index") is None:
        return None
    return _safe_int(row.get("failed_step_index"), -1)


def _resumed_from_step_index(row: Mapping[str, Any]) -> int | None:
    if row.get("resumed_from_step_index") is not None:
        return _safe_int(row.get("resumed_from_step_index"), -1)
    if row.get("resume_step_index") is not None:
        return _safe_int(row.get("resume_step_index"), -1)
    return None


def _resume_from_failed_step_success(row: Mapping[str, Any], *, failed_index: int) -> bool:
    explicit = row.get("resume_from_failed_step_success")
    if explicit is not None:
        return _safe_bool(explicit)
    resumed_index = _resumed_from_step_index(row)
    if resumed_index is not None:
        return resumed_index == failed_index
    return _safe_bool(row.get("resume_success"))


def _ticket_handoff(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("ticket_handoff")):
        return True
    next_action = str(row.get("next_action") or "").strip().upper()
    return next_action in {"OPEN_SUPPORT_TICKET", "ESCALATE_TO_HUMAN"}


def _handoff_summary_present(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("handoff_summary_present")):
        return True
    summary = str(row.get("handoff_summary") or row.get("operator_summary") or "").strip()
    return bool(summary)


def summarize_plan_persistence_resume_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    resume_attempt_total = 0
    resume_state_restored_total = 0
    checkpoint_missing_total = 0
    plan_persistence_missing_total = 0
    resume_from_failed_step_required_total = 0
    resume_from_failed_step_missing_total = 0
    ticket_handoff_total = 0
    ticket_handoff_summary_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        if _resume_attempt(row):
            resume_attempt_total += 1
            if _plan_state_restored(row):
                resume_state_restored_total += 1
            if not _checkpoint_present(row):
                checkpoint_missing_total += 1
            if not _plan_id_present(row):
                plan_persistence_missing_total += 1

            failed_index = _failed_step_index(row)
            if failed_index is not None and failed_index >= 0:
                resume_from_failed_step_required_total += 1
                if not _resume_from_failed_step_success(row, failed_index=failed_index):
                    resume_from_failed_step_missing_total += 1

        if _ticket_handoff(row):
            ticket_handoff_total += 1
            if not _handoff_summary_present(row):
                ticket_handoff_summary_missing_total += 1

    resume_success_rate = (
        1.0 if resume_attempt_total == 0 else float(resume_state_restored_total) / float(resume_attempt_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "resume_attempt_total": resume_attempt_total,
        "resume_state_restored_total": resume_state_restored_total,
        "resume_success_rate": resume_success_rate,
        "checkpoint_missing_total": checkpoint_missing_total,
        "plan_persistence_missing_total": plan_persistence_missing_total,
        "resume_from_failed_step_required_total": resume_from_failed_step_required_total,
        "resume_from_failed_step_missing_total": resume_from_failed_step_missing_total,
        "ticket_handoff_total": ticket_handoff_total,
        "ticket_handoff_summary_missing_total": ticket_handoff_summary_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_resume_success_rate: float,
    max_checkpoint_missing_total: int,
    max_plan_persistence_missing_total: int,
    max_resume_from_failed_step_missing_total: int,
    max_ticket_handoff_summary_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    resume_success_rate = _safe_float(summary.get("resume_success_rate"), 0.0)
    checkpoint_missing_total = _safe_int(summary.get("checkpoint_missing_total"), 0)
    plan_persistence_missing_total = _safe_int(summary.get("plan_persistence_missing_total"), 0)
    resume_from_failed_step_missing_total = _safe_int(summary.get("resume_from_failed_step_missing_total"), 0)
    ticket_handoff_summary_missing_total = _safe_int(summary.get("ticket_handoff_summary_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"plan persistence window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"plan persistence event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if resume_success_rate < max(0.0, float(min_resume_success_rate)):
        failures.append(
            f"plan persistence resume success rate below minimum: {resume_success_rate:.4f} < {float(min_resume_success_rate):.4f}"
        )
    if checkpoint_missing_total > max(0, int(max_checkpoint_missing_total)):
        failures.append(
            f"plan persistence checkpoint missing exceeded: {checkpoint_missing_total} > {int(max_checkpoint_missing_total)}"
        )
    if plan_persistence_missing_total > max(0, int(max_plan_persistence_missing_total)):
        failures.append(
            "plan persistence missing-plan-state exceeded: "
            f"{plan_persistence_missing_total} > {int(max_plan_persistence_missing_total)}"
        )
    if resume_from_failed_step_missing_total > max(0, int(max_resume_from_failed_step_missing_total)):
        failures.append(
            "plan persistence failed-step-resume missing exceeded: "
            f"{resume_from_failed_step_missing_total} > {int(max_resume_from_failed_step_missing_total)}"
        )
    if ticket_handoff_summary_missing_total > max(0, int(max_ticket_handoff_summary_missing_total)):
        failures.append(
            "plan persistence handoff-summary missing exceeded: "
            f"{ticket_handoff_summary_missing_total} > {int(max_ticket_handoff_summary_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"plan persistence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Plan Persistence Resume Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- resume_success_rate: {_safe_float(summary.get('resume_success_rate'), 0.0):.4f}")
    lines.append(f"- checkpoint_missing_total: {_safe_int(summary.get('checkpoint_missing_total'), 0)}")
    lines.append(f"- plan_persistence_missing_total: {_safe_int(summary.get('plan_persistence_missing_total'), 0)}")
    lines.append(
        f"- resume_from_failed_step_missing_total: {_safe_int(summary.get('resume_from_failed_step_missing_total'), 0)}"
    )
    lines.append(
        f"- ticket_handoff_summary_missing_total: {_safe_int(summary.get('ticket_handoff_summary_missing_total'), 0)}"
    )
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
    parser = argparse.ArgumentParser(description="Evaluate plan persistence/resume quality.")
    parser.add_argument("--events-jsonl", default="var/resolution_plan/plan_persistence_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_plan_persistence_resume_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-resume-success-rate", type=float, default=0.0)
    parser.add_argument("--max-checkpoint-missing-total", type=int, default=1000000)
    parser.add_argument("--max-plan-persistence-missing-total", type=int, default=1000000)
    parser.add_argument("--max-resume-from-failed-step-missing-total", type=int, default=1000000)
    parser.add_argument("--max-ticket-handoff-summary-missing-total", type=int, default=1000000)
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
    summary = summarize_plan_persistence_resume_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_resume_success_rate=max(0.0, float(args.min_resume_success_rate)),
        max_checkpoint_missing_total=max(0, int(args.max_checkpoint_missing_total)),
        max_plan_persistence_missing_total=max(0, int(args.max_plan_persistence_missing_total)),
        max_resume_from_failed_step_missing_total=max(0, int(args.max_resume_from_failed_step_missing_total)),
        max_ticket_handoff_summary_missing_total=max(0, int(args.max_ticket_handoff_summary_missing_total)),
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
                "min_resume_success_rate": float(args.min_resume_success_rate),
                "max_checkpoint_missing_total": int(args.max_checkpoint_missing_total),
                "max_plan_persistence_missing_total": int(args.max_plan_persistence_missing_total),
                "max_resume_from_failed_step_missing_total": int(args.max_resume_from_failed_step_missing_total),
                "max_ticket_handoff_summary_missing_total": int(args.max_ticket_handoff_summary_missing_total),
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
    print(f"resume_success_rate={_safe_float(summary.get('resume_success_rate'), 0.0):.4f}")
    print(f"checkpoint_missing_total={_safe_int(summary.get('checkpoint_missing_total'), 0)}")
    print(f"plan_persistence_missing_total={_safe_int(summary.get('plan_persistence_missing_total'), 0)}")
    print(
        "resume_from_failed_step_missing_total="
        f"{_safe_int(summary.get('resume_from_failed_step_missing_total'), 0)}"
    )
    print(
        "ticket_handoff_summary_missing_total="
        f"{_safe_int(summary.get('ticket_handoff_summary_missing_total'), 0)}"
    )

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
