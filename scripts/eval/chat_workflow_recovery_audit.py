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


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
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
    for key in ("timestamp", "event_time", "ts", "created_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_event(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "interrupted": "INTERRUPTED",
        "disconnect": "INTERRUPTED",
        "session_lost": "INTERRUPTED",
        "recovered": "RECOVERED",
        "resume": "RECOVERED",
        "resumed": "RECOVERED",
        "step": "STEP",
        "step_executed": "STEP",
        "execute": "EXECUTE",
        "executed": "EXECUTE",
        "audit": "AUDIT",
    }
    if text.upper() in {"INTERRUPTED", "RECOVERED", "STEP", "EXECUTE", "AUDIT"}:
        return text.upper()
    return aliases.get(text, text.upper() or "UNKNOWN")


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * min(1.0, max(0.0, ratio))))
    index = max(0, min(len(ordered) - 1, index))
    return float(ordered[index])


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


def summarize_recovery_audit(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    interrupted_workflow_total = 0
    recovered_workflow_total = 0
    audit_step_total = 0
    audit_missing_fields_total = 0
    audit_write_without_idempotency_total = 0
    recovery_latency_samples: list[float] = []
    latest_ts: datetime | None = None

    by_workflow: dict[str, dict[str, Any]] = {}

    for row in events:
        workflow_id = str(row.get("workflow_id") or row.get("id") or "").strip()
        if not workflow_id:
            continue
        event = _normalize_event(row.get("event_type") or row.get("status") or row.get("phase"))
        step_name = str(row.get("step") or row.get("current_step") or "").strip()
        reason_code = str(row.get("reason_code") or "").strip()
        tool_name = str(row.get("tool_name") or row.get("tool") or "").strip()
        action_type = str(row.get("action_type") or "").strip().upper()
        idempotency_key = str(row.get("idempotency_key") or "").strip()
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        flow = by_workflow.setdefault(
            workflow_id,
            {
                "interrupted_at": None,
                "recovered_at": None,
                "interrupted": False,
                "recovered": False,
            },
        )

        if event == "INTERRUPTED":
            flow["interrupted"] = True
            if isinstance(ts, datetime) and flow["interrupted_at"] is None:
                flow["interrupted_at"] = ts
        elif event == "RECOVERED":
            flow["recovered"] = True
            if isinstance(ts, datetime) and flow["recovered_at"] is None:
                flow["recovered_at"] = ts

        if event in {"STEP", "EXECUTE", "AUDIT"}:
            audit_step_total += 1
            if not step_name or not reason_code or not tool_name:
                audit_missing_fields_total += 1
            if action_type in {"WRITE", "WRITE_SENSITIVE"} and not idempotency_key:
                audit_write_without_idempotency_total += 1

    for flow in by_workflow.values():
        if flow.get("interrupted"):
            interrupted_workflow_total += 1
            if flow.get("recovered"):
                recovered_workflow_total += 1
                interrupted_at = flow.get("interrupted_at")
                recovered_at = flow.get("recovered_at")
                if isinstance(interrupted_at, datetime) and isinstance(recovered_at, datetime):
                    recovery_latency_samples.append(max(0.0, (recovered_at - interrupted_at).total_seconds()))

    recovery_success_ratio = (
        1.0 if interrupted_workflow_total == 0 else float(recovered_workflow_total) / float(interrupted_workflow_total)
    )
    audit_completeness_ratio = (
        1.0 if audit_step_total == 0 else float(audit_step_total - audit_missing_fields_total) / float(audit_step_total)
    )
    recovery_latency_p95_sec = _percentile(recovery_latency_samples, 0.95)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "workflow_total": len(by_workflow),
        "interrupted_workflow_total": interrupted_workflow_total,
        "recovered_workflow_total": recovered_workflow_total,
        "recovery_success_ratio": recovery_success_ratio,
        "recovery_latency_p95_sec": recovery_latency_p95_sec,
        "audit_step_total": audit_step_total,
        "audit_missing_fields_total": audit_missing_fields_total,
        "audit_completeness_ratio": audit_completeness_ratio,
        "audit_write_without_idempotency_total": audit_write_without_idempotency_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_recovery_success_ratio: float,
    max_recovery_latency_p95_sec: float,
    max_audit_missing_fields_total: int,
    max_write_without_idempotency_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    recovery_success_ratio = _safe_float(summary.get("recovery_success_ratio"), 0.0)
    recovery_latency_p95_sec = _safe_float(summary.get("recovery_latency_p95_sec"), 0.0)
    audit_missing_fields_total = _safe_int(summary.get("audit_missing_fields_total"), 0)
    audit_write_without_idempotency_total = _safe_int(summary.get("audit_write_without_idempotency_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"workflow recovery-audit window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if recovery_success_ratio < max(0.0, float(min_recovery_success_ratio)):
        failures.append(
            f"workflow recovery success ratio below threshold: {recovery_success_ratio:.4f} < {float(min_recovery_success_ratio):.4f}"
        )
    if recovery_latency_p95_sec > max(0.0, float(max_recovery_latency_p95_sec)):
        failures.append(
            f"workflow recovery latency p95 exceeded: {recovery_latency_p95_sec:.1f}s > {float(max_recovery_latency_p95_sec):.1f}s"
        )
    if audit_missing_fields_total > max(0, int(max_audit_missing_fields_total)):
        failures.append(
            f"workflow audit missing fields total exceeded: {audit_missing_fields_total} > {int(max_audit_missing_fields_total)}"
        )
    if audit_write_without_idempotency_total > max(0, int(max_write_without_idempotency_total)):
        failures.append(
            "workflow audit write-without-idempotency total exceeded: "
            f"{audit_write_without_idempotency_total} > {int(max_write_without_idempotency_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"workflow recovery-audit events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Workflow Recovery Audit")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- interrupted_workflow_total: {_safe_int(summary.get('interrupted_workflow_total'), 0)}")
    lines.append(f"- recovered_workflow_total: {_safe_int(summary.get('recovered_workflow_total'), 0)}")
    lines.append(f"- recovery_success_ratio: {_safe_float(summary.get('recovery_success_ratio'), 0.0):.4f}")
    lines.append(f"- recovery_latency_p95_sec: {_safe_float(summary.get('recovery_latency_p95_sec'), 0.0):.1f}")
    lines.append(f"- audit_missing_fields_total: {_safe_int(summary.get('audit_missing_fields_total'), 0)}")
    lines.append(
        f"- audit_write_without_idempotency_total: {_safe_int(summary.get('audit_write_without_idempotency_total'), 0)}"
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
    parser = argparse.ArgumentParser(description="Evaluate workflow recovery and per-step audit completeness.")
    parser.add_argument("--events-jsonl", default="var/chat_workflow/workflow_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_workflow_recovery_audit")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--min-recovery-success-ratio", type=float, default=0.95)
    parser.add_argument("--max-recovery-latency-p95-sec", type=float, default=600.0)
    parser.add_argument("--max-audit-missing-fields-total", type=int, default=0)
    parser.add_argument("--max-write-without-idempotency-total", type=int, default=0)
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
    summary = summarize_recovery_audit(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_recovery_success_ratio=max(0.0, float(args.min_recovery_success_ratio)),
        max_recovery_latency_p95_sec=max(0.0, float(args.max_recovery_latency_p95_sec)),
        max_audit_missing_fields_total=max(0, int(args.max_audit_missing_fields_total)),
        max_write_without_idempotency_total=max(0, int(args.max_write_without_idempotency_total)),
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
                "min_recovery_success_ratio": float(args.min_recovery_success_ratio),
                "max_recovery_latency_p95_sec": float(args.max_recovery_latency_p95_sec),
                "max_audit_missing_fields_total": int(args.max_audit_missing_fields_total),
                "max_write_without_idempotency_total": int(args.max_write_without_idempotency_total),
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
    print(f"interrupted_workflow_total={_safe_int(summary.get('interrupted_workflow_total'), 0)}")
    print(f"recovery_success_ratio={_safe_float(summary.get('recovery_success_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
