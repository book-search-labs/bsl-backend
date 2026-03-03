#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SENSITIVE_TYPES = {"CANCEL_ORDER", "REFUND_REQUEST", "ADDRESS_CHANGE", "PAYMENT_CHANGE"}


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
        "confirm_requested": "CONFIRM_REQUESTED",
        "confirmation_requested": "CONFIRM_REQUESTED",
        "confirm_received": "CONFIRMED",
        "confirmed": "CONFIRMED",
        "approve": "CONFIRMED",
        "execute": "EXECUTE",
        "executed": "EXECUTE",
        "timeout": "TIMEOUT",
        "confirmation_timeout": "TIMEOUT",
        "cancelled": "CANCELLED",
        "canceled": "CANCELLED",
        "auto_cancelled": "AUTO_CANCELLED",
        "auto_canceled": "AUTO_CANCELLED",
    }
    if text.upper() in {"CONFIRM_REQUESTED", "CONFIRMED", "EXECUTE", "TIMEOUT", "CANCELLED", "AUTO_CANCELLED"}:
        return text.upper()
    return aliases.get(text, text.upper() or "UNKNOWN")


def _normalize_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "ORDER_CANCEL": "CANCEL_ORDER",
        "REFUND": "REFUND_REQUEST",
        "ADDRESS_UPDATE": "ADDRESS_CHANGE",
    }
    if text in SENSITIVE_TYPES:
        return text
    return aliases.get(text, text or "UNKNOWN")


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


def summarize_confirmation_checkpoint(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    by_workflow: dict[str, list[dict[str, Any]]] = {}
    for row in events:
        workflow_id = str(row.get("workflow_id") or row.get("id") or "").strip()
        if not workflow_id:
            continue
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        by_workflow.setdefault(workflow_id, []).append(
            {
                "event": _normalize_event(row.get("event_type") or row.get("status") or row.get("phase")),
                "workflow_type": _normalize_type(row.get("workflow_type") or row.get("type")),
                "risk_level": str(row.get("risk_level") or "").strip().upper(),
                "auto_cancel": _safe_bool(row.get("auto_cancel"), False) or _safe_bool(row.get("auto_cancelled"), False),
                "ts": ts,
            }
        )

    sensitive_execute_total = 0
    execute_without_confirmation_total = 0
    confirmation_timeout_total = 0
    timeout_auto_cancel_total = 0
    confirmation_latency_samples: list[float] = []

    for rows in by_workflow.values():
        ordered = sorted(
            rows,
            key=lambda item: item["ts"] if isinstance(item["ts"], datetime) else datetime.min.replace(tzinfo=timezone.utc),
        )

        has_confirmed = False
        confirm_requested_at: datetime | None = None
        timeout_seen = False
        auto_cancel_seen = False
        sensitive = False
        for item in ordered:
            workflow_type = str(item.get("workflow_type") or "")
            risk_level = str(item.get("risk_level") or "")
            if workflow_type in SENSITIVE_TYPES or risk_level in {"HIGH", "WRITE_SENSITIVE"}:
                sensitive = True

            event = str(item.get("event") or "UNKNOWN")
            ts = item.get("ts") if isinstance(item.get("ts"), datetime) else None
            if event == "CONFIRM_REQUESTED":
                confirm_requested_at = ts
            elif event == "CONFIRMED":
                has_confirmed = True
                if confirm_requested_at is not None and ts is not None:
                    confirmation_latency_samples.append(max(0.0, (ts - confirm_requested_at).total_seconds()))
            elif event == "TIMEOUT":
                timeout_seen = True
            elif event in {"CANCELLED", "AUTO_CANCELLED"}:
                if timeout_seen or bool(item.get("auto_cancel")):
                    auto_cancel_seen = True
            elif event == "EXECUTE":
                if sensitive:
                    sensitive_execute_total += 1
                    if not has_confirmed:
                        execute_without_confirmation_total += 1

        if timeout_seen:
            confirmation_timeout_total += 1
            if auto_cancel_seen:
                timeout_auto_cancel_total += 1

    timeout_auto_cancel_ratio = (
        1.0 if confirmation_timeout_total == 0 else float(timeout_auto_cancel_total) / float(confirmation_timeout_total)
    )
    confirmation_latency_p95_sec = _percentile(confirmation_latency_samples, 0.95)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "workflow_total": len(by_workflow),
        "sensitive_execute_total": sensitive_execute_total,
        "execute_without_confirmation_total": execute_without_confirmation_total,
        "confirmation_timeout_total": confirmation_timeout_total,
        "timeout_auto_cancel_total": timeout_auto_cancel_total,
        "timeout_auto_cancel_ratio": timeout_auto_cancel_ratio,
        "confirmation_latency_p95_sec": confirmation_latency_p95_sec,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_execute_without_confirmation_total: int,
    min_timeout_auto_cancel_ratio: float,
    max_confirmation_latency_p95_sec: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    execute_without_confirmation_total = _safe_int(summary.get("execute_without_confirmation_total"), 0)
    timeout_auto_cancel_ratio = _safe_float(summary.get("timeout_auto_cancel_ratio"), 0.0)
    confirmation_latency_p95_sec = _safe_float(summary.get("confirmation_latency_p95_sec"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"workflow confirmation window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if execute_without_confirmation_total > max(0, int(max_execute_without_confirmation_total)):
        failures.append(
            "execute without confirmation total exceeded: "
            f"{execute_without_confirmation_total} > {int(max_execute_without_confirmation_total)}"
        )
    if timeout_auto_cancel_ratio < max(0.0, float(min_timeout_auto_cancel_ratio)):
        failures.append(
            f"timeout auto-cancel ratio below threshold: {timeout_auto_cancel_ratio:.4f} < {float(min_timeout_auto_cancel_ratio):.4f}"
        )
    if confirmation_latency_p95_sec > max(0.0, float(max_confirmation_latency_p95_sec)):
        failures.append(
            f"confirmation latency p95 exceeded: {confirmation_latency_p95_sec:.1f}s > {float(max_confirmation_latency_p95_sec):.1f}s"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"workflow confirmation events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Workflow Confirmation Checkpoint")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- workflow_total: {_safe_int(summary.get('workflow_total'), 0)}")
    lines.append(f"- sensitive_execute_total: {_safe_int(summary.get('sensitive_execute_total'), 0)}")
    lines.append(
        f"- execute_without_confirmation_total: {_safe_int(summary.get('execute_without_confirmation_total'), 0)}"
    )
    lines.append(f"- timeout_auto_cancel_ratio: {_safe_float(summary.get('timeout_auto_cancel_ratio'), 0.0):.4f}")
    lines.append(f"- confirmation_latency_p95_sec: {_safe_float(summary.get('confirmation_latency_p95_sec'), 0.0):.1f}")
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
    parser = argparse.ArgumentParser(description="Evaluate workflow confirmation checkpoints for sensitive actions.")
    parser.add_argument("--events-jsonl", default="var/chat_workflow/workflow_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_workflow_confirmation_checkpoint")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-execute-without-confirmation-total", type=int, default=0)
    parser.add_argument("--min-timeout-auto-cancel-ratio", type=float, default=1.0)
    parser.add_argument("--max-confirmation-latency-p95-sec", type=float, default=300.0)
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
    summary = summarize_confirmation_checkpoint(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_execute_without_confirmation_total=max(0, int(args.max_execute_without_confirmation_total)),
        min_timeout_auto_cancel_ratio=max(0.0, float(args.min_timeout_auto_cancel_ratio)),
        max_confirmation_latency_p95_sec=max(0.0, float(args.max_confirmation_latency_p95_sec)),
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
                "max_execute_without_confirmation_total": int(args.max_execute_without_confirmation_total),
                "min_timeout_auto_cancel_ratio": float(args.min_timeout_auto_cancel_ratio),
                "max_confirmation_latency_p95_sec": float(args.max_confirmation_latency_p95_sec),
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
    print(f"workflow_total={_safe_int(summary.get('workflow_total'), 0)}")
    print(f"execute_without_confirmation_total={_safe_int(summary.get('execute_without_confirmation_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
