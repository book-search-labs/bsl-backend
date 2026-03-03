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


def _candidate_event(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("proposal_id") or row.get("candidate_id") or row.get("knowledge_candidate_id") or "").strip())


def _approved(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("approved"), False):
        return True
    status = str(row.get("approval_status") or row.get("status") or "").strip().lower()
    event_type = str(row.get("event_type") or "").strip().lower()
    return status == "approved" or event_type in {"knowledge_approved", "candidate_approved"}


def _indexed(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("indexed"), False):
        return True
    status = str(row.get("index_status") or row.get("status") or "").strip().lower()
    event_type = str(row.get("event_type") or "").strip().lower()
    return status in {"indexed", "deployed"} or event_type in {"knowledge_indexed", "knowledge_deployed"}


def _pending(row: Mapping[str, Any]) -> bool:
    status = str(row.get("approval_status") or row.get("status") or "").strip().lower()
    return status == "pending"


def _rollback(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("rollback_applied"), False):
        return True
    event_type = str(row.get("event_type") or "").strip().lower()
    return event_type in {"knowledge_rollback", "rollback_applied"}


def _approval_evidence_present(row: Mapping[str, Any]) -> bool:
    approver = str(row.get("approved_by") or row.get("approver_id") or "").strip()
    approved_at = _parse_ts(row.get("approved_at"))
    approval_ref = str(row.get("approval_ticket_id") or row.get("approval_request_id") or "").strip()
    return bool((approver and approved_at is not None) or approval_ref)


def _rollback_reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("rollback_reason") or row.get("reason_code") or "").strip())


def _candidate_created_at(row: Mapping[str, Any]) -> datetime | None:
    return _parse_ts(row.get("candidate_created_at") or row.get("created_at")) or _event_ts(row)


def _approval_latency_minutes(row: Mapping[str, Any]) -> float:
    created = _candidate_created_at(row)
    approved_at = _parse_ts(row.get("approved_at"))
    if created is None or approved_at is None:
        return 0.0
    return max(0.0, (approved_at - created).total_seconds() / 60.0)


def _index_latency_minutes(row: Mapping[str, Any]) -> float:
    approved_at = _parse_ts(row.get("approved_at"))
    indexed_at = _parse_ts(row.get("indexed_at") or row.get("deployed_at"))
    if approved_at is None or indexed_at is None:
        return 0.0
    return max(0.0, (indexed_at - approved_at).total_seconds() / 60.0)


def _pending_age_hours(row: Mapping[str, Any], *, now: datetime) -> float:
    created = _candidate_created_at(row)
    if created is None:
        return 0.0
    return max(0.0, (now - created).total_seconds() / 3600.0)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_ticket_knowledge_approval_rollback_guard(
    rows: list[Mapping[str, Any]],
    *,
    pending_sla_hours: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    candidate_total = 0
    approved_total = 0
    indexed_total = 0
    unapproved_index_total = 0
    approval_evidence_missing_total = 0
    pending_total = 0
    pending_sla_breach_total = 0
    rollback_total = 0
    rollback_without_reason_total = 0
    approval_latencies: list[float] = []
    index_latencies: list[float] = []

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _candidate_event(row):
            continue
        candidate_total += 1

        approved = _approved(row)
        indexed = _indexed(row)
        pending = _pending(row)
        rollback = _rollback(row)

        if approved:
            approved_total += 1
            approval_latencies.append(_approval_latency_minutes(row))
            if not _approval_evidence_present(row):
                approval_evidence_missing_total += 1
        if indexed:
            indexed_total += 1
            index_latencies.append(_index_latency_minutes(row))
            if not approved:
                unapproved_index_total += 1
        if pending:
            pending_total += 1
            if _pending_age_hours(row, now=now_dt) > max(0.0, float(pending_sla_hours)):
                pending_sla_breach_total += 1
        if rollback:
            rollback_total += 1
            if not _rollback_reason_present(row):
                rollback_without_reason_total += 1

    p95_candidate_to_approval_minutes = _p95(approval_latencies)
    p95_approval_to_index_minutes = _p95(index_latencies)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "candidate_total": candidate_total,
        "approved_total": approved_total,
        "indexed_total": indexed_total,
        "unapproved_index_total": unapproved_index_total,
        "approval_evidence_missing_total": approval_evidence_missing_total,
        "pending_total": pending_total,
        "pending_sla_breach_total": pending_sla_breach_total,
        "rollback_total": rollback_total,
        "rollback_without_reason_total": rollback_without_reason_total,
        "p95_candidate_to_approval_minutes": p95_candidate_to_approval_minutes,
        "p95_approval_to_index_minutes": p95_approval_to_index_minutes,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_candidate_total: int,
    min_approved_total: int,
    min_indexed_total: int,
    max_unapproved_index_total: int,
    max_approval_evidence_missing_total: int,
    max_pending_sla_breach_total: int,
    max_rollback_without_reason_total: int,
    max_p95_candidate_to_approval_minutes: float,
    max_p95_approval_to_index_minutes: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    candidate_total = _safe_int(summary.get("candidate_total"), 0)
    approved_total = _safe_int(summary.get("approved_total"), 0)
    indexed_total = _safe_int(summary.get("indexed_total"), 0)
    unapproved_index_total = _safe_int(summary.get("unapproved_index_total"), 0)
    approval_evidence_missing_total = _safe_int(summary.get("approval_evidence_missing_total"), 0)
    pending_sla_breach_total = _safe_int(summary.get("pending_sla_breach_total"), 0)
    rollback_without_reason_total = _safe_int(summary.get("rollback_without_reason_total"), 0)
    p95_candidate_to_approval_minutes = _safe_float(summary.get("p95_candidate_to_approval_minutes"), 0.0)
    p95_approval_to_index_minutes = _safe_float(summary.get("p95_approval_to_index_minutes"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat ticket knowledge approval window too small: {window_size} < {int(min_window)}")
    if candidate_total < max(0, int(min_candidate_total)):
        failures.append(f"chat ticket knowledge candidate total too small: {candidate_total} < {int(min_candidate_total)}")
    if approved_total < max(0, int(min_approved_total)):
        failures.append(f"chat ticket knowledge approved total too small: {approved_total} < {int(min_approved_total)}")
    if indexed_total < max(0, int(min_indexed_total)):
        failures.append(f"chat ticket knowledge indexed total too small: {indexed_total} < {int(min_indexed_total)}")
    if window_size == 0:
        return failures

    if unapproved_index_total > max(0, int(max_unapproved_index_total)):
        failures.append(
            f"chat ticket knowledge unapproved index total exceeded: {unapproved_index_total} > {int(max_unapproved_index_total)}"
        )
    if approval_evidence_missing_total > max(0, int(max_approval_evidence_missing_total)):
        failures.append(
            "chat ticket knowledge approval evidence missing total exceeded: "
            f"{approval_evidence_missing_total} > {int(max_approval_evidence_missing_total)}"
        )
    if pending_sla_breach_total > max(0, int(max_pending_sla_breach_total)):
        failures.append(
            f"chat ticket knowledge pending SLA breach total exceeded: {pending_sla_breach_total} > {int(max_pending_sla_breach_total)}"
        )
    if rollback_without_reason_total > max(0, int(max_rollback_without_reason_total)):
        failures.append(
            "chat ticket knowledge rollback-without-reason total exceeded: "
            f"{rollback_without_reason_total} > {int(max_rollback_without_reason_total)}"
        )
    if p95_candidate_to_approval_minutes > max(0.0, float(max_p95_candidate_to_approval_minutes)):
        failures.append(
            "chat ticket knowledge p95 candidate->approval minutes exceeded: "
            f"{p95_candidate_to_approval_minutes:.2f} > {float(max_p95_candidate_to_approval_minutes):.2f}"
        )
    if p95_approval_to_index_minutes > max(0.0, float(max_p95_approval_to_index_minutes)):
        failures.append(
            "chat ticket knowledge p95 approval->index minutes exceeded: "
            f"{p95_approval_to_index_minutes:.2f} > {float(max_p95_approval_to_index_minutes):.2f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat ticket knowledge approval stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Ticket Knowledge Approval/Rollback Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- candidate_total: {_safe_int(summary.get('candidate_total'), 0)}")
    lines.append(f"- approved_total: {_safe_int(summary.get('approved_total'), 0)}")
    lines.append(f"- indexed_total: {_safe_int(summary.get('indexed_total'), 0)}")
    lines.append(f"- unapproved_index_total: {_safe_int(summary.get('unapproved_index_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate ticket knowledge approval/rollback pipeline quality.")
    parser.add_argument("--events-jsonl", default="var/chat_ticket_knowledge/approval_pipeline_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_knowledge_approval_rollback_guard")
    parser.add_argument("--pending-sla-hours", type=float, default=24.0)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-candidate-total", type=int, default=0)
    parser.add_argument("--min-approved-total", type=int, default=0)
    parser.add_argument("--min-indexed-total", type=int, default=0)
    parser.add_argument("--max-unapproved-index-total", type=int, default=1000000)
    parser.add_argument("--max-approval-evidence-missing-total", type=int, default=1000000)
    parser.add_argument("--max-pending-sla-breach-total", type=int, default=1000000)
    parser.add_argument("--max-rollback-without-reason-total", type=int, default=1000000)
    parser.add_argument("--max-p95-candidate-to-approval-minutes", type=float, default=1000000.0)
    parser.add_argument("--max-p95-approval-to-index-minutes", type=float, default=1000000.0)
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
    summary = summarize_ticket_knowledge_approval_rollback_guard(
        rows,
        pending_sla_hours=max(0.0, float(args.pending_sla_hours)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_candidate_total=max(0, int(args.min_candidate_total)),
        min_approved_total=max(0, int(args.min_approved_total)),
        min_indexed_total=max(0, int(args.min_indexed_total)),
        max_unapproved_index_total=max(0, int(args.max_unapproved_index_total)),
        max_approval_evidence_missing_total=max(0, int(args.max_approval_evidence_missing_total)),
        max_pending_sla_breach_total=max(0, int(args.max_pending_sla_breach_total)),
        max_rollback_without_reason_total=max(0, int(args.max_rollback_without_reason_total)),
        max_p95_candidate_to_approval_minutes=max(0.0, float(args.max_p95_candidate_to_approval_minutes)),
        max_p95_approval_to_index_minutes=max(0.0, float(args.max_p95_approval_to_index_minutes)),
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
                "min_candidate_total": int(args.min_candidate_total),
                "min_approved_total": int(args.min_approved_total),
                "min_indexed_total": int(args.min_indexed_total),
                "max_unapproved_index_total": int(args.max_unapproved_index_total),
                "max_approval_evidence_missing_total": int(args.max_approval_evidence_missing_total),
                "max_pending_sla_breach_total": int(args.max_pending_sla_breach_total),
                "max_rollback_without_reason_total": int(args.max_rollback_without_reason_total),
                "max_p95_candidate_to_approval_minutes": float(args.max_p95_candidate_to_approval_minutes),
                "max_p95_approval_to_index_minutes": float(args.max_p95_approval_to_index_minutes),
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
    print(f"candidate_total={_safe_int(summary.get('candidate_total'), 0)}")
    print(f"approved_total={_safe_int(summary.get('approved_total'), 0)}")
    print(f"indexed_total={_safe_int(summary.get('indexed_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
