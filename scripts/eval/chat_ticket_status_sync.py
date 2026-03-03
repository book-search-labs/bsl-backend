#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_STATUSES = {"RECEIVED", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED"}


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
        "ticket_status_lookup": "TICKET_STATUS_LOOKUP",
        "status_lookup": "TICKET_STATUS_LOOKUP",
        "lookup": "TICKET_STATUS_LOOKUP",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _normalize_result(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "ok": "OK",
        "success": "OK",
        "found": "OK",
        "not_found": "NOT_FOUND",
        "empty": "NOT_FOUND",
        "forbidden": "FORBIDDEN",
        "denied": "FORBIDDEN",
        "error": "ERROR",
        "fail": "ERROR",
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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def summarize_ticket_status_sync(
    events: list[Mapping[str, Any]],
    *,
    max_status_age_hours: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    lookup_total = 0
    lookup_ok_total = 0
    lookup_not_found_total = 0
    lookup_forbidden_total = 0
    lookup_error_total = 0
    invalid_status_total = 0
    missing_ticket_ref_total = 0
    stale_status_total = 0
    source_distribution: dict[str, int] = {}

    for row in events:
        event = _normalize_event(row.get("event_type") or row.get("event") or row.get("status_event"))
        if event != "TICKET_STATUS_LOOKUP":
            continue
        lookup_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        result = _normalize_result(row.get("result") or row.get("lookup_result"))
        source = str(row.get("source") or row.get("ticket_source") or "").strip().lower() or "unknown"
        source_distribution[source] = source_distribution.get(source, 0) + 1
        ticket_ref = str(row.get("ticket_no") or row.get("ticket_id") or "").strip()
        status = str(row.get("ticket_status") or row.get("status") or "").strip().upper()
        status_ts = _parse_ts(row.get("status_updated_at") or row.get("ticket_updated_at"))

        if result == "OK":
            lookup_ok_total += 1
            if status and status not in VALID_STATUSES:
                invalid_status_total += 1
            if not ticket_ref:
                missing_ticket_ref_total += 1
            if status_ts is not None:
                age_hours = max(0.0, (now_dt - status_ts).total_seconds() / 3600.0)
                if age_hours > max(0.0, float(max_status_age_hours)):
                    stale_status_total += 1
        elif result == "NOT_FOUND":
            lookup_not_found_total += 1
        elif result == "FORBIDDEN":
            lookup_forbidden_total += 1
        else:
            lookup_error_total += 1

    lookup_ok_ratio = 1.0 if lookup_total == 0 else float(lookup_ok_total) / float(lookup_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "lookup_total": lookup_total,
        "lookup_ok_total": lookup_ok_total,
        "lookup_not_found_total": lookup_not_found_total,
        "lookup_forbidden_total": lookup_forbidden_total,
        "lookup_error_total": lookup_error_total,
        "lookup_ok_ratio": lookup_ok_ratio,
        "invalid_status_total": invalid_status_total,
        "missing_ticket_ref_total": missing_ticket_ref_total,
        "stale_status_total": stale_status_total,
        "source_distribution": [{"source": key, "count": value} for key, value in sorted(source_distribution.items())],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_lookup_ok_ratio: float,
    max_invalid_status_total: int,
    max_missing_ticket_ref_total: int,
    max_stale_status_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    lookup_ok_ratio = _safe_float(summary.get("lookup_ok_ratio"), 1.0)
    invalid_status_total = _safe_int(summary.get("invalid_status_total"), 0)
    missing_ticket_ref_total = _safe_int(summary.get("missing_ticket_ref_total"), 0)
    stale_status_total = _safe_int(summary.get("stale_status_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket status sync window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if lookup_ok_ratio < max(0.0, float(min_lookup_ok_ratio)):
        failures.append(f"ticket status lookup ok ratio below threshold: {lookup_ok_ratio:.4f} < {float(min_lookup_ok_ratio):.4f}")
    if invalid_status_total > max(0, int(max_invalid_status_total)):
        failures.append(f"invalid ticket status total exceeded: {invalid_status_total} > {int(max_invalid_status_total)}")
    if missing_ticket_ref_total > max(0, int(max_missing_ticket_ref_total)):
        failures.append(
            f"missing ticket reference total exceeded: {missing_ticket_ref_total} > {int(max_missing_ticket_ref_total)}"
        )
    if stale_status_total > max(0, int(max_stale_status_total)):
        failures.append(f"stale ticket status total exceeded: {stale_status_total} > {int(max_stale_status_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket status sync events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_lookup_ok_ratio_drop: float,
    max_invalid_status_total_increase: int,
    max_missing_ticket_ref_total_increase: int,
    max_stale_status_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_lookup_ok_ratio = _safe_float(base_summary.get("lookup_ok_ratio"), 1.0)
    cur_lookup_ok_ratio = _safe_float(current_summary.get("lookup_ok_ratio"), 1.0)
    lookup_ok_ratio_drop = max(0.0, base_lookup_ok_ratio - cur_lookup_ok_ratio)
    if lookup_ok_ratio_drop > max(0.0, float(max_lookup_ok_ratio_drop)):
        failures.append(
            "lookup ok ratio regression: "
            f"baseline={base_lookup_ok_ratio:.6f}, current={cur_lookup_ok_ratio:.6f}, "
            f"allowed_drop={float(max_lookup_ok_ratio_drop):.6f}"
        )

    base_invalid_status_total = _safe_int(base_summary.get("invalid_status_total"), 0)
    cur_invalid_status_total = _safe_int(current_summary.get("invalid_status_total"), 0)
    invalid_status_total_increase = max(0, cur_invalid_status_total - base_invalid_status_total)
    if invalid_status_total_increase > max(0, int(max_invalid_status_total_increase)):
        failures.append(
            "invalid status total regression: "
            f"baseline={base_invalid_status_total}, current={cur_invalid_status_total}, "
            f"allowed_increase={max(0, int(max_invalid_status_total_increase))}"
        )

    base_missing_ticket_ref_total = _safe_int(base_summary.get("missing_ticket_ref_total"), 0)
    cur_missing_ticket_ref_total = _safe_int(current_summary.get("missing_ticket_ref_total"), 0)
    missing_ticket_ref_total_increase = max(0, cur_missing_ticket_ref_total - base_missing_ticket_ref_total)
    if missing_ticket_ref_total_increase > max(0, int(max_missing_ticket_ref_total_increase)):
        failures.append(
            "missing ticket reference total regression: "
            f"baseline={base_missing_ticket_ref_total}, current={cur_missing_ticket_ref_total}, "
            f"allowed_increase={max(0, int(max_missing_ticket_ref_total_increase))}"
        )

    base_stale_status_total = _safe_int(base_summary.get("stale_status_total"), 0)
    cur_stale_status_total = _safe_int(current_summary.get("stale_status_total"), 0)
    stale_status_total_increase = max(0, cur_stale_status_total - base_stale_status_total)
    if stale_status_total_increase > max(0, int(max_stale_status_total_increase)):
        failures.append(
            "stale status total regression: "
            f"baseline={base_stale_status_total}, current={cur_stale_status_total}, "
            f"allowed_increase={max(0, int(max_stale_status_total_increase))}"
        )

    base_stale_minutes = _safe_float(base_summary.get("stale_minutes"), 0.0)
    cur_stale_minutes = _safe_float(current_summary.get("stale_minutes"), 0.0)
    stale_minutes_increase = max(0.0, cur_stale_minutes - base_stale_minutes)
    if stale_minutes_increase > max(0.0, float(max_stale_minutes_increase)):
        failures.append(
            "stale minutes regression: "
            f"baseline={base_stale_minutes:.6f}, current={cur_stale_minutes:.6f}, "
            f"allowed_increase={float(max_stale_minutes_increase):.6f}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Ticket Status Sync")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- lookup_total: {_safe_int(summary.get('lookup_total'), 0)}")
    lines.append(f"- lookup_ok_total: {_safe_int(summary.get('lookup_ok_total'), 0)}")
    lines.append(f"- lookup_ok_ratio: {_safe_float(summary.get('lookup_ok_ratio'), 1.0):.4f}")
    lines.append(f"- invalid_status_total: {_safe_int(summary.get('invalid_status_total'), 0)}")
    lines.append(f"- stale_status_total: {_safe_int(summary.get('stale_status_total'), 0)}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate ticket status synchronization quality.")
    parser.add_argument("--events-jsonl", default="var/chat_ticket/ticket_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--max-status-age-hours", type=float, default=24.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_status_sync")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-lookup-ok-ratio", type=float, default=0.90)
    parser.add_argument("--max-invalid-status-total", type=int, default=0)
    parser.add_argument("--max-missing-ticket-ref-total", type=int, default=0)
    parser.add_argument("--max-stale-status-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-lookup-ok-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-invalid-status-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-ticket-ref-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-status-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
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
    summary = summarize_ticket_status_sync(
        events,
        max_status_age_hours=max(0.0, float(args.max_status_age_hours)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_lookup_ok_ratio=max(0.0, float(args.min_lookup_ok_ratio)),
        max_invalid_status_total=max(0, int(args.max_invalid_status_total)),
        max_missing_ticket_ref_total=max(0, int(args.max_missing_ticket_ref_total)),
        max_stale_status_total=max(0, int(args.max_stale_status_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_lookup_ok_ratio_drop=max(0.0, float(args.max_lookup_ok_ratio_drop)),
            max_invalid_status_total_increase=max(0, int(args.max_invalid_status_total_increase)),
            max_missing_ticket_ref_total_increase=max(0, int(args.max_missing_ticket_ref_total_increase)),
            max_stale_status_total_increase=max(0, int(args.max_stale_status_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": max(1, int(args.window_hours)),
            "limit": max(1, int(args.limit)),
            "max_status_age_hours": max(0.0, float(args.max_status_age_hours)),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": summary,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_lookup_ok_ratio": float(args.min_lookup_ok_ratio),
                "max_invalid_status_total": int(args.max_invalid_status_total),
                "max_missing_ticket_ref_total": int(args.max_missing_ticket_ref_total),
                "max_stale_status_total": int(args.max_stale_status_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_lookup_ok_ratio_drop": float(args.max_lookup_ok_ratio_drop),
                "max_invalid_status_total_increase": int(args.max_invalid_status_total_increase),
                "max_missing_ticket_ref_total_increase": int(args.max_missing_ticket_ref_total_increase),
                "max_stale_status_total_increase": int(args.max_stale_status_total_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
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
    print(f"lookup_total={_safe_int(summary.get('lookup_total'), 0)}")
    print(f"lookup_ok_total={_safe_int(summary.get('lookup_ok_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
