#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

CORE_EVENTS = {"REQUESTED", "CONFIRMED", "EXECUTED", "UNDO_REQUESTED", "UNDO_EXECUTED", "UNDO_EXPIRED"}


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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_event(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "request": "REQUESTED",
        "requested": "REQUESTED",
        "confirm": "CONFIRMED",
        "confirmed": "CONFIRMED",
        "execute": "EXECUTED",
        "executed": "EXECUTED",
        "undo_request": "UNDO_REQUESTED",
        "undo_requested": "UNDO_REQUESTED",
        "undo_execute": "UNDO_EXECUTED",
        "undo_executed": "UNDO_EXECUTED",
        "undo_expired": "UNDO_EXPIRED",
        "undo_window_expired": "UNDO_EXPIRED",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _action_id(row: Mapping[str, Any]) -> str:
    for key in ("action_id", "workflow_id", "request_id", "id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


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


def _missing_audit_fields(row: Mapping[str, Any]) -> int:
    actor = str(row.get("actor_id") or row.get("user_id") or "").strip()
    target = str(row.get("target_id") or row.get("order_id") or row.get("action_target") or "").strip()
    reason_code = str(row.get("reason_code") or "").strip()
    trace_id = str(row.get("trace_id") or "").strip()
    request_id = str(row.get("request_id") or row.get("req_id") or "").strip()
    missing = 0
    if not actor:
        missing += 1
    if not target:
        missing += 1
    if not reason_code:
        missing += 1
    if not trace_id:
        missing += 1
    if not request_id:
        missing += 1
    return missing


def summarize_undo_audit(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None
    grouped: dict[str, list[dict[str, Any]]] = {}

    missing_audit_fields_total = 0
    for row in events:
        action_id = _action_id(row)
        if not action_id:
            continue
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event = _normalize_event(row.get("event_type") or row.get("event") or row.get("status"))
        if event in CORE_EVENTS:
            missing_audit_fields_total += _missing_audit_fields(row)
        grouped.setdefault(action_id, []).append(
            {
                "event": event,
                "undo_supported": _safe_bool(row.get("undo_supported"), False),
                "undo_window_sec": max(0.0, _safe_float(row.get("undo_window_sec"), 0.0)),
                "ts": ts,
            }
        )

    action_total = len(grouped)
    execute_without_request_total = 0
    undo_supported_execute_total = 0
    undo_requested_total = 0
    undo_executed_total = 0
    undo_after_window_total = 0
    audit_trail_incomplete_total = 0

    for rows in grouped.values():
        ordered = sorted(
            rows,
            key=lambda item: item["ts"] if isinstance(item["ts"], datetime) else datetime.min.replace(tzinfo=timezone.utc),
        )
        has_request = False
        has_confirm = False
        has_execute = False
        execute_at: datetime | None = None
        undo_supported = False
        undo_window_sec = 0.0

        for item in ordered:
            event = str(item.get("event") or "UNKNOWN")
            ts = item.get("ts") if isinstance(item.get("ts"), datetime) else None
            undo_supported = undo_supported or bool(item.get("undo_supported"))
            undo_window_sec = max(undo_window_sec, _safe_float(item.get("undo_window_sec"), 0.0))
            if event == "REQUESTED":
                has_request = True
            elif event == "CONFIRMED":
                has_confirm = True
            elif event == "EXECUTED":
                has_execute = True
                execute_at = ts
                if undo_supported:
                    undo_supported_execute_total += 1
                if not has_request:
                    execute_without_request_total += 1
            elif event == "UNDO_REQUESTED":
                undo_requested_total += 1
                if execute_at is not None and undo_window_sec > 0 and ts is not None:
                    elapsed = max(0.0, (ts - execute_at).total_seconds())
                    if elapsed > undo_window_sec:
                        undo_after_window_total += 1
            elif event == "UNDO_EXECUTED":
                undo_executed_total += 1

        if has_execute and (not has_request or not has_confirm):
            audit_trail_incomplete_total += 1

    undo_success_ratio = 1.0 if undo_requested_total == 0 else float(undo_executed_total) / float(undo_requested_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "action_total": action_total,
        "execute_without_request_total": execute_without_request_total,
        "undo_supported_execute_total": undo_supported_execute_total,
        "undo_requested_total": undo_requested_total,
        "undo_executed_total": undo_executed_total,
        "undo_success_ratio": undo_success_ratio,
        "undo_after_window_total": undo_after_window_total,
        "audit_trail_incomplete_total": audit_trail_incomplete_total,
        "missing_audit_fields_total": missing_audit_fields_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_execute_without_request_total: int,
    max_undo_after_window_total: int,
    min_undo_success_ratio: float,
    max_audit_trail_incomplete_total: int,
    max_missing_audit_fields_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    execute_without_request_total = _safe_int(summary.get("execute_without_request_total"), 0)
    undo_after_window_total = _safe_int(summary.get("undo_after_window_total"), 0)
    undo_success_ratio = _safe_float(summary.get("undo_success_ratio"), 1.0)
    audit_trail_incomplete_total = _safe_int(summary.get("audit_trail_incomplete_total"), 0)
    missing_audit_fields_total = _safe_int(summary.get("missing_audit_fields_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"sensitive action undo-audit window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if execute_without_request_total > max(0, int(max_execute_without_request_total)):
        failures.append(
            f"execute without request total exceeded: {execute_without_request_total} > {int(max_execute_without_request_total)}"
        )
    if undo_after_window_total > max(0, int(max_undo_after_window_total)):
        failures.append(f"undo after window total exceeded: {undo_after_window_total} > {int(max_undo_after_window_total)}")
    if undo_success_ratio < max(0.0, float(min_undo_success_ratio)):
        failures.append(f"undo success ratio below threshold: {undo_success_ratio:.4f} < {float(min_undo_success_ratio):.4f}")
    if audit_trail_incomplete_total > max(0, int(max_audit_trail_incomplete_total)):
        failures.append(
            "audit trail incomplete total exceeded: "
            f"{audit_trail_incomplete_total} > {int(max_audit_trail_incomplete_total)}"
        )
    if missing_audit_fields_total > max(0, int(max_missing_audit_fields_total)):
        failures.append(
            f"missing audit fields total exceeded: {missing_audit_fields_total} > {int(max_missing_audit_fields_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"sensitive action undo-audit events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_execute_without_request_total_increase: int,
    max_undo_after_window_total_increase: int,
    max_undo_success_ratio_drop: float,
    max_audit_trail_incomplete_total_increase: int,
    max_missing_audit_fields_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_execute_without_request_total = _safe_int(base_summary.get("execute_without_request_total"), 0)
    cur_execute_without_request_total = _safe_int(current_summary.get("execute_without_request_total"), 0)
    execute_without_request_total_increase = max(0, cur_execute_without_request_total - base_execute_without_request_total)
    if execute_without_request_total_increase > max(0, int(max_execute_without_request_total_increase)):
        failures.append(
            "execute without request total regression: "
            f"baseline={base_execute_without_request_total}, current={cur_execute_without_request_total}, "
            f"allowed_increase={max(0, int(max_execute_without_request_total_increase))}"
        )

    base_undo_after_window_total = _safe_int(base_summary.get("undo_after_window_total"), 0)
    cur_undo_after_window_total = _safe_int(current_summary.get("undo_after_window_total"), 0)
    undo_after_window_total_increase = max(0, cur_undo_after_window_total - base_undo_after_window_total)
    if undo_after_window_total_increase > max(0, int(max_undo_after_window_total_increase)):
        failures.append(
            "undo after window total regression: "
            f"baseline={base_undo_after_window_total}, current={cur_undo_after_window_total}, "
            f"allowed_increase={max(0, int(max_undo_after_window_total_increase))}"
        )

    base_undo_success_ratio = _safe_float(base_summary.get("undo_success_ratio"), 1.0)
    cur_undo_success_ratio = _safe_float(current_summary.get("undo_success_ratio"), 1.0)
    undo_success_ratio_drop = max(0.0, base_undo_success_ratio - cur_undo_success_ratio)
    if undo_success_ratio_drop > max(0.0, float(max_undo_success_ratio_drop)):
        failures.append(
            "undo success ratio regression: "
            f"baseline={base_undo_success_ratio:.6f}, current={cur_undo_success_ratio:.6f}, "
            f"allowed_drop={float(max_undo_success_ratio_drop):.6f}"
        )

    base_audit_trail_incomplete_total = _safe_int(base_summary.get("audit_trail_incomplete_total"), 0)
    cur_audit_trail_incomplete_total = _safe_int(current_summary.get("audit_trail_incomplete_total"), 0)
    audit_trail_incomplete_total_increase = max(
        0,
        cur_audit_trail_incomplete_total - base_audit_trail_incomplete_total,
    )
    if audit_trail_incomplete_total_increase > max(0, int(max_audit_trail_incomplete_total_increase)):
        failures.append(
            "audit trail incomplete total regression: "
            f"baseline={base_audit_trail_incomplete_total}, current={cur_audit_trail_incomplete_total}, "
            f"allowed_increase={max(0, int(max_audit_trail_incomplete_total_increase))}"
        )

    base_missing_audit_fields_total = _safe_int(base_summary.get("missing_audit_fields_total"), 0)
    cur_missing_audit_fields_total = _safe_int(current_summary.get("missing_audit_fields_total"), 0)
    missing_audit_fields_total_increase = max(0, cur_missing_audit_fields_total - base_missing_audit_fields_total)
    if missing_audit_fields_total_increase > max(0, int(max_missing_audit_fields_total_increase)):
        failures.append(
            "missing audit fields total regression: "
            f"baseline={base_missing_audit_fields_total}, current={cur_missing_audit_fields_total}, "
            f"allowed_increase={max(0, int(max_missing_audit_fields_total_increase))}"
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
    lines.append("# Chat Sensitive Action Undo Audit")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- action_total: {_safe_int(summary.get('action_total'), 0)}")
    lines.append(f"- undo_requested_total: {_safe_int(summary.get('undo_requested_total'), 0)}")
    lines.append(f"- undo_executed_total: {_safe_int(summary.get('undo_executed_total'), 0)}")
    lines.append(f"- undo_success_ratio: {_safe_float(summary.get('undo_success_ratio'), 1.0):.4f}")
    lines.append(f"- missing_audit_fields_total: {_safe_int(summary.get('missing_audit_fields_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate sensitive-action undo window and audit trail integrity.")
    parser.add_argument("--events-jsonl", default="var/chat_actions/sensitive_action_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_sensitive_action_undo_audit")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-execute-without-request-total", type=int, default=0)
    parser.add_argument("--max-undo-after-window-total", type=int, default=0)
    parser.add_argument("--min-undo-success-ratio", type=float, default=0.80)
    parser.add_argument("--max-audit-trail-incomplete-total", type=int, default=0)
    parser.add_argument("--max-missing-audit-fields-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-execute-without-request-total-increase", type=int, default=0)
    parser.add_argument("--max-undo-after-window-total-increase", type=int, default=0)
    parser.add_argument("--max-undo-success-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-audit-trail-incomplete-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-audit-fields-total-increase", type=int, default=0)
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
    summary = summarize_undo_audit(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_execute_without_request_total=max(0, int(args.max_execute_without_request_total)),
        max_undo_after_window_total=max(0, int(args.max_undo_after_window_total)),
        min_undo_success_ratio=max(0.0, float(args.min_undo_success_ratio)),
        max_audit_trail_incomplete_total=max(0, int(args.max_audit_trail_incomplete_total)),
        max_missing_audit_fields_total=max(0, int(args.max_missing_audit_fields_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_execute_without_request_total_increase=max(0, int(args.max_execute_without_request_total_increase)),
            max_undo_after_window_total_increase=max(0, int(args.max_undo_after_window_total_increase)),
            max_undo_success_ratio_drop=max(0.0, float(args.max_undo_success_ratio_drop)),
            max_audit_trail_incomplete_total_increase=max(0, int(args.max_audit_trail_incomplete_total_increase)),
            max_missing_audit_fields_total_increase=max(0, int(args.max_missing_audit_fields_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": max(1, int(args.window_hours)),
            "limit": max(1, int(args.limit)),
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
                "max_execute_without_request_total": int(args.max_execute_without_request_total),
                "max_undo_after_window_total": int(args.max_undo_after_window_total),
                "min_undo_success_ratio": float(args.min_undo_success_ratio),
                "max_audit_trail_incomplete_total": int(args.max_audit_trail_incomplete_total),
                "max_missing_audit_fields_total": int(args.max_missing_audit_fields_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_execute_without_request_total_increase": int(args.max_execute_without_request_total_increase),
                "max_undo_after_window_total_increase": int(args.max_undo_after_window_total_increase),
                "max_undo_success_ratio_drop": float(args.max_undo_success_ratio_drop),
                "max_audit_trail_incomplete_total_increase": int(args.max_audit_trail_incomplete_total_increase),
                "max_missing_audit_fields_total_increase": int(args.max_missing_audit_fields_total_increase),
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
    print(f"undo_requested_total={_safe_int(summary.get('undo_requested_total'), 0)}")
    print(f"undo_executed_total={_safe_int(summary.get('undo_executed_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
