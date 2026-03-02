#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


RESOLVED_ACTIONS = {"PURGED", "ANONYMIZED", "EXEMPT_APPROVED"}
DELETION_ACTIONS = {"PURGED", "ANONYMIZED"}
EXCEPTION_ACTIONS = {"EXEMPT_APPROVED", "EXEMPT_PENDING", "EXEMPT_DENIED"}


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
    for key in ("timestamp", "event_time", "generated_at", "created_at", "ts"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _expires_ts(row: Mapping[str, Any]) -> datetime | None:
    for key in ("expires_at", "expire_at", "ttl_expires_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _approval_id(row: Mapping[str, Any]) -> str:
    for key in ("approval_id", "exception_approval_id", "retention_approval_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalize_action(value: Any) -> str:
    return str(value or "UNKNOWN").strip().upper()


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


def summarize_retention(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    expired_total = 0
    resolved_total = 0
    overdue_total = 0
    deletion_action_total = 0
    approved_exception_total = 0
    unapproved_exception_total = 0
    missing_trace_total = 0
    traced_total = 0

    latest_ts: datetime | None = None
    data_class_rows: dict[str, dict[str, int]] = {}
    reasons: dict[str, int] = {}

    for row in events:
        data_class = str(row.get("data_class") or "unknown")
        action = _normalize_action(row.get("action"))
        reason_code = str(row.get("reason_code") or "NONE")
        expires_at = _expires_ts(row)
        ts = _event_ts(row)
        approval_id = _approval_id(row)
        trace_id = str(row.get("trace_id") or "").strip()
        request_id = str(row.get("request_id") or "").strip()

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        class_row = data_class_rows.setdefault(
            data_class,
            {
                "total": 0,
                "expired": 0,
                "resolved": 0,
                "overdue": 0,
                "deletions": 0,
            },
        )
        class_row["total"] += 1
        reasons[reason_code] = reasons.get(reason_code, 0) + 1

        if trace_id and request_id:
            traced_total += 1
        else:
            missing_trace_total += 1

        if action in RESOLVED_ACTIONS:
            resolved_total += 1
            class_row["resolved"] += 1
        if action in DELETION_ACTIONS:
            deletion_action_total += 1
            class_row["deletions"] += 1

        if action in EXCEPTION_ACTIONS:
            if action == "EXEMPT_APPROVED" and approval_id:
                approved_exception_total += 1
            elif not approval_id:
                unapproved_exception_total += 1

        if expires_at is not None and expires_at <= now_dt:
            expired_total += 1
            class_row["expired"] += 1
            if action not in RESOLVED_ACTIONS:
                overdue_total += 1
                class_row["overdue"] += 1

    window_size = len(events)
    overdue_ratio = 0.0 if expired_total == 0 else float(overdue_total) / float(expired_total)
    purge_coverage_ratio = 1.0 if expired_total == 0 else float(expired_total - overdue_total) / float(expired_total)
    trace_coverage_ratio = 1.0 if window_size == 0 else float(traced_total) / float(window_size)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    classes = [
        {
            "data_class": key,
            "total": value["total"],
            "expired": value["expired"],
            "resolved": value["resolved"],
            "overdue": value["overdue"],
            "deletions": value["deletions"],
        }
        for key, value in sorted(data_class_rows.items(), key=lambda item: (-item[1]["overdue"], -item[1]["total"], item[0]))
    ]

    top_reasons = [
        {"reason_code": code, "count": count}
        for code, count in sorted(reasons.items(), key=lambda item: item[1], reverse=True)[:10]
    ]

    return {
        "window_size": window_size,
        "expired_total": expired_total,
        "resolved_total": resolved_total,
        "overdue_total": overdue_total,
        "overdue_ratio": overdue_ratio,
        "purge_coverage_ratio": purge_coverage_ratio,
        "deletion_action_total": deletion_action_total,
        "approved_exception_total": approved_exception_total,
        "unapproved_exception_total": unapproved_exception_total,
        "missing_trace_total": missing_trace_total,
        "trace_coverage_ratio": trace_coverage_ratio,
        "stale_minutes": stale_minutes,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "data_classes": classes,
        "top_reasons": top_reasons,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_overdue_total: int,
    max_overdue_ratio: float,
    min_purge_coverage_ratio: float,
    max_unapproved_exception_total: int,
    max_stale_minutes: float,
    min_trace_coverage_ratio: float,
    max_missing_trace_total: int,
) -> list[str]:
    failures: list[str] = []
    window_size = int(summary.get("window_size") or 0)
    overdue_total = int(summary.get("overdue_total") or 0)
    overdue_ratio = _safe_float(summary.get("overdue_ratio"), 0.0)
    purge_coverage_ratio = _safe_float(summary.get("purge_coverage_ratio"), 1.0)
    unapproved_exception_total = int(summary.get("unapproved_exception_total") or 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)
    trace_coverage_ratio = _safe_float(summary.get("trace_coverage_ratio"), 1.0)
    missing_trace_total = int(summary.get("missing_trace_total") or 0)

    if window_size < max(0, int(min_window)):
        failures.append(f"retention window too small: {window_size} < {int(min_window)}")
    if overdue_total > max(0, int(max_overdue_total)):
        failures.append(f"overdue records exceeded: {overdue_total} > {int(max_overdue_total)}")
    if overdue_ratio > max(0.0, float(max_overdue_ratio)):
        failures.append(f"overdue ratio exceeded: {overdue_ratio:.4f} > {float(max_overdue_ratio):.4f}")
    if purge_coverage_ratio < max(0.0, float(min_purge_coverage_ratio)):
        failures.append(
            f"purge coverage below threshold: {purge_coverage_ratio:.4f} < {float(min_purge_coverage_ratio):.4f}"
        )
    if unapproved_exception_total > max(0, int(max_unapproved_exception_total)):
        failures.append(
            "unapproved retention exceptions exceeded: "
            f"{unapproved_exception_total} > {int(max_unapproved_exception_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"retention events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    if trace_coverage_ratio < max(0.0, float(min_trace_coverage_ratio)):
        failures.append(
            f"trace coverage below threshold: {trace_coverage_ratio:.4f} < {float(min_trace_coverage_ratio):.4f}"
        )
    if missing_trace_total > max(0, int(max_missing_trace_total)):
        failures.append(f"missing trace context exceeded: {missing_trace_total} > {int(max_missing_trace_total)}")

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Data Retention Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {int(summary.get('window_size') or 0)}")
    lines.append(f"- expired_total: {int(summary.get('expired_total') or 0)}")
    lines.append(f"- overdue_total: {int(summary.get('overdue_total') or 0)}")
    lines.append(f"- overdue_ratio: {_safe_float(summary.get('overdue_ratio'), 0.0):.4f}")
    lines.append(f"- purge_coverage_ratio: {_safe_float(summary.get('purge_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- unapproved_exception_total: {int(summary.get('unapproved_exception_total') or 0)}")
    lines.append(f"- trace_coverage_ratio: {_safe_float(summary.get('trace_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- stale_minutes: {_safe_float(summary.get('stale_minutes'), 0.0):.1f}")
    lines.append("")
    lines.append("## Data Classes")
    lines.append("")
    class_rows = summary.get("data_classes") if isinstance(summary.get("data_classes"), list) else []
    if class_rows:
        for row in class_rows:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                "- "
                f"{row.get('data_class')}: total={int(row.get('total') or 0)} "
                f"expired={int(row.get('expired') or 0)} resolved={int(row.get('resolved') or 0)} "
                f"overdue={int(row.get('overdue') or 0)} deletions={int(row.get('deletions') or 0)}"
            )
    else:
        lines.append("- (none)")
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
    parser = argparse.ArgumentParser(description="Evaluate chat retention enforcement from lifecycle events.")
    parser.add_argument("--events-jsonl", default="var/chat_governance/retention_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=72)
    parser.add_argument("--limit", type=int, default=20000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_data_retention_guard")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-overdue-total", type=int, default=0)
    parser.add_argument("--max-overdue-ratio", type=float, default=0.0)
    parser.add_argument("--min-purge-coverage-ratio", type=float, default=1.0)
    parser.add_argument("--max-unapproved-exception-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=180.0)
    parser.add_argument("--min-trace-coverage-ratio", type=float, default=1.0)
    parser.add_argument("--max-missing-trace-total", type=int, default=0)
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
    summary = summarize_retention(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_overdue_total=max(0, int(args.max_overdue_total)),
        max_overdue_ratio=max(0.0, float(args.max_overdue_ratio)),
        min_purge_coverage_ratio=max(0.0, float(args.min_purge_coverage_ratio)),
        max_unapproved_exception_total=max(0, int(args.max_unapproved_exception_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
        min_trace_coverage_ratio=max(0.0, float(args.min_trace_coverage_ratio)),
        max_missing_trace_total=max(0, int(args.max_missing_trace_total)),
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
                "max_overdue_total": int(args.max_overdue_total),
                "max_overdue_ratio": float(args.max_overdue_ratio),
                "min_purge_coverage_ratio": float(args.min_purge_coverage_ratio),
                "max_unapproved_exception_total": int(args.max_unapproved_exception_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "min_trace_coverage_ratio": float(args.min_trace_coverage_ratio),
                "max_missing_trace_total": int(args.max_missing_trace_total),
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
    print(f"window_size={int(summary.get('window_size') or 0)}")
    print(f"overdue_total={int(summary.get('overdue_total') or 0)}")
    print(f"trace_coverage_ratio={_safe_float(summary.get('trace_coverage_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
