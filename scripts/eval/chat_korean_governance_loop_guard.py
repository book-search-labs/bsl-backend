#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


UPDATE_EVENT_TYPES = {
    "dictionary_update_proposed",
    "dictionary_update_approved",
    "dictionary_update_deployed",
    "style_policy_update_proposed",
    "style_policy_update_approved",
    "style_policy_update_deployed",
}
FEEDBACK_EVENT_TYPES = {
    "style_violation_reported",
    "style_feedback_submitted",
    "style_feedback_triaged",
    "style_feedback_resolved",
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


def _event_type(row: Mapping[str, Any]) -> str:
    return str(row.get("event_type") or row.get("type") or "").strip().lower()


def _is_update_event(row: Mapping[str, Any]) -> bool:
    event_type = _event_type(row)
    if event_type in UPDATE_EVENT_TYPES:
        return True
    return bool(str(row.get("proposal_id") or row.get("change_request_id") or row.get("dictionary_version_to") or "").strip())


def _is_update_deployed(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("update_deployed"), False):
        return True
    event_type = _event_type(row)
    if event_type.endswith("_deployed"):
        return True
    status = str(row.get("status") or row.get("approval_status") or "").strip().lower()
    return status in {"deployed", "released", "applied"}


def _is_update_approved(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("approved"), False):
        return True
    event_type = _event_type(row)
    if event_type.endswith("_approved"):
        return True
    status = str(row.get("approval_status") or row.get("status") or "").strip().lower()
    return status == "approved"


def _has_approval_evidence(row: Mapping[str, Any]) -> bool:
    approver = str(row.get("approved_by") or row.get("approver_id") or "").strip()
    approved_at = _parse_ts(row.get("approved_at"))
    approval_ref = str(row.get("approval_ticket_id") or row.get("approval_request_id") or "").strip()
    return bool((approver and approved_at is not None) or approval_ref)


def _is_pending_update(row: Mapping[str, Any]) -> bool:
    event_type = _event_type(row)
    if event_type.endswith("_proposed") and not _is_update_approved(row) and not _is_update_deployed(row):
        return True
    status = str(row.get("status") or row.get("approval_status") or "").strip().lower()
    return status == "pending"


def _is_feedback_event(row: Mapping[str, Any]) -> bool:
    event_type = _event_type(row)
    if event_type in FEEDBACK_EVENT_TYPES:
        return True
    return bool(str(row.get("feedback_id") or row.get("violation_case_id") or "").strip())


def _is_feedback_triaged(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("triaged"), False):
        return True
    event_type = _event_type(row)
    if event_type in {"style_feedback_triaged", "style_feedback_resolved"}:
        return True
    status = str(row.get("triage_status") or row.get("status") or "").strip().lower()
    if status in {"triaged", "resolved", "closed"}:
        return True
    return bool(str(row.get("triage_id") or "").strip())


def _is_feedback_closed(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("resolved"), False):
        return True
    event_type = _event_type(row)
    if event_type == "style_feedback_resolved":
        return True
    status = str(row.get("triage_status") or row.get("status") or "").strip().lower()
    return status in {"resolved", "closed"}


def _reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("reason_code") or row.get("policy_rule") or "").strip())


def _pending_age_hours(row: Mapping[str, Any], *, now: datetime) -> float:
    created_at = _parse_ts(row.get("proposed_at") or row.get("created_at")) or _event_ts(row)
    if created_at is None:
        return 0.0
    return max(0.0, (now - created_at).total_seconds() / 3600.0)


def summarize_korean_governance_loop_guard(
    rows: list[Mapping[str, Any]],
    *,
    pending_sla_hours: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    update_event_total = 0
    update_deployed_total = 0
    approved_update_total = 0
    approval_evidence_missing_total = 0
    unaudited_deploy_total = 0
    pending_update_total = 0
    pending_update_sla_breach_total = 0

    feedback_event_total = 0
    feedback_triaged_total = 0
    feedback_closed_total = 0
    reason_code_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if _is_update_event(row):
            update_event_total += 1
            deployed = _is_update_deployed(row)
            approved = _is_update_approved(row)
            if deployed:
                update_deployed_total += 1
            if approved:
                approved_update_total += 1
                if not _has_approval_evidence(row):
                    approval_evidence_missing_total += 1
            if deployed and not approved:
                unaudited_deploy_total += 1
            if _is_pending_update(row):
                pending_update_total += 1
                if _pending_age_hours(row, now=now_dt) > max(0.0, float(pending_sla_hours)):
                    pending_update_sla_breach_total += 1
            if (deployed or approved) and not _reason_present(row):
                reason_code_missing_total += 1

        if _is_feedback_event(row):
            feedback_event_total += 1
            triaged = _is_feedback_triaged(row)
            closed = _is_feedback_closed(row)
            if triaged:
                feedback_triaged_total += 1
            if closed:
                feedback_closed_total += 1
            if triaged and not _reason_present(row):
                reason_code_missing_total += 1

    feedback_triage_ratio = 1.0 if feedback_event_total == 0 else float(feedback_triaged_total) / float(feedback_event_total)
    feedback_closure_ratio = (
        1.0 if feedback_triaged_total == 0 else float(feedback_closed_total) / float(feedback_triaged_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "update_event_total": update_event_total,
        "update_deployed_total": update_deployed_total,
        "approved_update_total": approved_update_total,
        "approval_evidence_missing_total": approval_evidence_missing_total,
        "unaudited_deploy_total": unaudited_deploy_total,
        "pending_update_total": pending_update_total,
        "pending_update_sla_breach_total": pending_update_sla_breach_total,
        "feedback_event_total": feedback_event_total,
        "feedback_triaged_total": feedback_triaged_total,
        "feedback_closed_total": feedback_closed_total,
        "feedback_triage_ratio": feedback_triage_ratio,
        "feedback_closure_ratio": feedback_closure_ratio,
        "reason_code_missing_total": reason_code_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_update_event_total: int,
    min_feedback_event_total: int,
    min_feedback_triage_ratio: float,
    min_feedback_closure_ratio: float,
    max_unaudited_deploy_total: int,
    max_approval_evidence_missing_total: int,
    max_pending_update_sla_breach_total: int,
    max_reason_code_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    update_event_total = _safe_int(summary.get("update_event_total"), 0)
    feedback_event_total = _safe_int(summary.get("feedback_event_total"), 0)
    feedback_triage_ratio = _safe_float(summary.get("feedback_triage_ratio"), 0.0)
    feedback_closure_ratio = _safe_float(summary.get("feedback_closure_ratio"), 0.0)
    unaudited_deploy_total = _safe_int(summary.get("unaudited_deploy_total"), 0)
    approval_evidence_missing_total = _safe_int(summary.get("approval_evidence_missing_total"), 0)
    pending_update_sla_breach_total = _safe_int(summary.get("pending_update_sla_breach_total"), 0)
    reason_code_missing_total = _safe_int(summary.get("reason_code_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat korean governance window too small: {window_size} < {int(min_window)}")
    if update_event_total < max(0, int(min_update_event_total)):
        failures.append(
            f"chat korean governance update event total too small: {update_event_total} < {int(min_update_event_total)}"
        )
    if feedback_event_total < max(0, int(min_feedback_event_total)):
        failures.append(
            f"chat korean governance feedback event total too small: {feedback_event_total} < {int(min_feedback_event_total)}"
        )
    if window_size == 0:
        return failures

    if feedback_triage_ratio < max(0.0, float(min_feedback_triage_ratio)):
        failures.append(
            f"chat korean governance feedback triage ratio below minimum: {feedback_triage_ratio:.4f} < {float(min_feedback_triage_ratio):.4f}"
        )
    if feedback_closure_ratio < max(0.0, float(min_feedback_closure_ratio)):
        failures.append(
            f"chat korean governance feedback closure ratio below minimum: {feedback_closure_ratio:.4f} < {float(min_feedback_closure_ratio):.4f}"
        )
    if unaudited_deploy_total > max(0, int(max_unaudited_deploy_total)):
        failures.append(
            f"chat korean governance unaudited deploy total exceeded: {unaudited_deploy_total} > {int(max_unaudited_deploy_total)}"
        )
    if approval_evidence_missing_total > max(0, int(max_approval_evidence_missing_total)):
        failures.append(
            "chat korean governance approval evidence missing total exceeded: "
            f"{approval_evidence_missing_total} > {int(max_approval_evidence_missing_total)}"
        )
    if pending_update_sla_breach_total > max(0, int(max_pending_update_sla_breach_total)):
        failures.append(
            "chat korean governance pending update SLA breach total exceeded: "
            f"{pending_update_sla_breach_total} > {int(max_pending_update_sla_breach_total)}"
        )
    if reason_code_missing_total > max(0, int(max_reason_code_missing_total)):
        failures.append(
            f"chat korean governance reason code missing total exceeded: {reason_code_missing_total} > {int(max_reason_code_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat korean governance stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Korean Governance Loop Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- update_event_total: {_safe_int(summary.get('update_event_total'), 0)}")
    lines.append(f"- feedback_event_total: {_safe_int(summary.get('feedback_event_total'), 0)}")
    lines.append(f"- feedback_triage_ratio: {_safe_float(summary.get('feedback_triage_ratio'), 0.0):.4f}")
    lines.append(f"- unaudited_deploy_total: {_safe_int(summary.get('unaudited_deploy_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat korean terminology/style governance loop.")
    parser.add_argument("--events-jsonl", default="var/chat_style/governance_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_korean_governance_loop_guard")
    parser.add_argument("--pending-sla-hours", type=float, default=24.0)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-update-event-total", type=int, default=0)
    parser.add_argument("--min-feedback-event-total", type=int, default=0)
    parser.add_argument("--min-feedback-triage-ratio", type=float, default=0.0)
    parser.add_argument("--min-feedback-closure-ratio", type=float, default=0.0)
    parser.add_argument("--max-unaudited-deploy-total", type=int, default=1000000)
    parser.add_argument("--max-approval-evidence-missing-total", type=int, default=1000000)
    parser.add_argument("--max-pending-update-sla-breach-total", type=int, default=1000000)
    parser.add_argument("--max-reason-code-missing-total", type=int, default=1000000)
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
    summary = summarize_korean_governance_loop_guard(
        rows,
        pending_sla_hours=max(0.0, float(args.pending_sla_hours)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_update_event_total=max(0, int(args.min_update_event_total)),
        min_feedback_event_total=max(0, int(args.min_feedback_event_total)),
        min_feedback_triage_ratio=max(0.0, float(args.min_feedback_triage_ratio)),
        min_feedback_closure_ratio=max(0.0, float(args.min_feedback_closure_ratio)),
        max_unaudited_deploy_total=max(0, int(args.max_unaudited_deploy_total)),
        max_approval_evidence_missing_total=max(0, int(args.max_approval_evidence_missing_total)),
        max_pending_update_sla_breach_total=max(0, int(args.max_pending_update_sla_breach_total)),
        max_reason_code_missing_total=max(0, int(args.max_reason_code_missing_total)),
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
                "pending_sla_hours": float(args.pending_sla_hours),
                "min_window": int(args.min_window),
                "min_update_event_total": int(args.min_update_event_total),
                "min_feedback_event_total": int(args.min_feedback_event_total),
                "min_feedback_triage_ratio": float(args.min_feedback_triage_ratio),
                "min_feedback_closure_ratio": float(args.min_feedback_closure_ratio),
                "max_unaudited_deploy_total": int(args.max_unaudited_deploy_total),
                "max_approval_evidence_missing_total": int(args.max_approval_evidence_missing_total),
                "max_pending_update_sla_breach_total": int(args.max_pending_update_sla_breach_total),
                "max_reason_code_missing_total": int(args.max_reason_code_missing_total),
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
    print(f"update_event_total={_safe_int(summary.get('update_event_total'), 0)}")
    print(f"feedback_event_total={_safe_int(summary.get('feedback_event_total'), 0)}")
    print(f"feedback_triage_ratio={_safe_float(summary.get('feedback_triage_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
