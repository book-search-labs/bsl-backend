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


def _normalize_event(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "ticket_create_requested": "TICKET_CREATE_REQUESTED",
        "create_requested": "TICKET_CREATE_REQUESTED",
        "ticket_created": "TICKET_CREATED",
        "create_success": "TICKET_CREATED",
        "ticket_create_failed": "TICKET_CREATE_FAILED",
        "create_failed": "TICKET_CREATE_FAILED",
        "ticket_reused": "TICKET_REUSED",
        "dedup_reused": "TICKET_REUSED",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


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


def _payload_missing_fields(row: Mapping[str, Any]) -> int:
    required = [
        str(row.get("summary") or row.get("issue_summary") or "").strip(),
        str(row.get("order_id") or row.get("order_no") or row.get("order_ref") or "").strip(),
        str(row.get("error_code") or row.get("issue_code") or "").strip(),
    ]
    return sum(1 for value in required if not value)


def summarize_ticket_creation(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    create_requested_total = 0
    create_success_total = 0
    create_failed_total = 0
    dedup_reused_total = 0
    payload_missing_fields_total = 0
    missing_ticket_no_total = 0
    missing_eta_total = 0

    for row in events:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event = _normalize_event(row.get("event_type") or row.get("event") or row.get("status"))
        if event == "TICKET_CREATE_REQUESTED":
            create_requested_total += 1
            payload_missing_fields_total += _payload_missing_fields(row)
        elif event == "TICKET_CREATED":
            create_success_total += 1
            ticket_no = str(row.get("ticket_no") or row.get("ticket_id") or "").strip()
            eta = str(row.get("eta_minutes") or row.get("expected_resolution_minutes") or row.get("eta") or "").strip()
            if not ticket_no:
                missing_ticket_no_total += 1
            if not eta:
                missing_eta_total += 1
        elif event == "TICKET_CREATE_FAILED":
            create_failed_total += 1
        elif event == "TICKET_REUSED":
            dedup_reused_total += 1

    create_success_ratio = 1.0 if create_requested_total == 0 else float(create_success_total) / float(create_requested_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "create_requested_total": create_requested_total,
        "create_success_total": create_success_total,
        "create_failed_total": create_failed_total,
        "dedup_reused_total": dedup_reused_total,
        "create_success_ratio": create_success_ratio,
        "payload_missing_fields_total": payload_missing_fields_total,
        "missing_ticket_no_total": missing_ticket_no_total,
        "missing_eta_total": missing_eta_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_create_success_ratio: float,
    max_payload_missing_fields_total: int,
    max_missing_ticket_no_total: int,
    max_missing_eta_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    create_success_ratio = _safe_float(summary.get("create_success_ratio"), 1.0)
    payload_missing_fields_total = _safe_int(summary.get("payload_missing_fields_total"), 0)
    missing_ticket_no_total = _safe_int(summary.get("missing_ticket_no_total"), 0)
    missing_eta_total = _safe_int(summary.get("missing_eta_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket creation window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if create_success_ratio < max(0.0, float(min_create_success_ratio)):
        failures.append(
            f"ticket creation success ratio below threshold: {create_success_ratio:.4f} < {float(min_create_success_ratio):.4f}"
        )
    if payload_missing_fields_total > max(0, int(max_payload_missing_fields_total)):
        failures.append(
            "ticket creation payload missing fields total exceeded: "
            f"{payload_missing_fields_total} > {int(max_payload_missing_fields_total)}"
        )
    if missing_ticket_no_total > max(0, int(max_missing_ticket_no_total)):
        failures.append(f"ticket_no missing total exceeded: {missing_ticket_no_total} > {int(max_missing_ticket_no_total)}")
    if missing_eta_total > max(0, int(max_missing_eta_total)):
        failures.append(f"eta missing total exceeded: {missing_eta_total} > {int(max_missing_eta_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket creation events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Ticket Creation Integration")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- create_requested_total: {_safe_int(summary.get('create_requested_total'), 0)}")
    lines.append(f"- create_success_total: {_safe_int(summary.get('create_success_total'), 0)}")
    lines.append(f"- create_success_ratio: {_safe_float(summary.get('create_success_ratio'), 1.0):.4f}")
    lines.append(f"- payload_missing_fields_total: {_safe_int(summary.get('payload_missing_fields_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate support ticket creation integration quality.")
    parser.add_argument("--events-jsonl", default="var/chat_ticket/ticket_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_creation_integration")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-create-success-ratio", type=float, default=0.95)
    parser.add_argument("--max-payload-missing-fields-total", type=int, default=0)
    parser.add_argument("--max-missing-ticket-no-total", type=int, default=0)
    parser.add_argument("--max-missing-eta-total", type=int, default=0)
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
    summary = summarize_ticket_creation(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_create_success_ratio=max(0.0, float(args.min_create_success_ratio)),
        max_payload_missing_fields_total=max(0, int(args.max_payload_missing_fields_total)),
        max_missing_ticket_no_total=max(0, int(args.max_missing_ticket_no_total)),
        max_missing_eta_total=max(0, int(args.max_missing_eta_total)),
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
                "min_create_success_ratio": float(args.min_create_success_ratio),
                "max_payload_missing_fields_total": int(args.max_payload_missing_fields_total),
                "max_missing_ticket_no_total": int(args.max_missing_ticket_no_total),
                "max_missing_eta_total": int(args.max_missing_eta_total),
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
    print(f"create_requested_total={_safe_int(summary.get('create_requested_total'), 0)}")
    print(f"create_success_total={_safe_int(summary.get('create_success_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
