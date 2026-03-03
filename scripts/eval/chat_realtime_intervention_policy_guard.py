#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


STATE_AT_RISK = "AT_RISK"
STATE_DEGRADED = "DEGRADED"

AT_RISK_REQUIRED_TYPES = {
    "SUMMARY_RECONFIRM",
    "QUICK_ACTION_BUTTONS",
}

DEGRADED_REQUIRED_TYPES = {
    "SAFE_MODE",
    "OPEN_SUPPORT_TICKET",
    "ESCALATE_TO_HUMAN",
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


def _normalize_state(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {STATE_AT_RISK, STATE_DEGRADED}:
        return text
    return text


def _intervention_types(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("intervention_types")
    if isinstance(raw, list):
        return {str(item).strip().upper() for item in raw if str(item).strip()}
    text = str(row.get("intervention_type") or "").strip()
    if not text:
        return set()
    return {item.strip().upper() for item in text.split(",") if item.strip()}


def _intervention_triggered(row: Mapping[str, Any], *, types: set[str]) -> bool:
    if _safe_bool(row.get("intervention_triggered")):
        return True
    return bool(types)


def summarize_realtime_intervention_policy_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    escalation_failure_threshold: int = 3,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    intervention_triggered_total = 0
    at_risk_total = 0
    degraded_total = 0
    at_risk_intervention_missing_total = 0
    degraded_intervention_missing_total = 0
    escalation_required_total = 0
    escalation_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        state = _normalize_state(row.get("session_state"))
        types = _intervention_types(row)
        triggered = _intervention_triggered(row, types=types)
        if triggered:
            intervention_triggered_total += 1

        if state == STATE_AT_RISK:
            at_risk_total += 1
            if not (types & AT_RISK_REQUIRED_TYPES):
                at_risk_intervention_missing_total += 1
        elif state == STATE_DEGRADED:
            degraded_total += 1
            if not (types & DEGRADED_REQUIRED_TYPES):
                degraded_intervention_missing_total += 1

        consecutive_failures = _safe_int(row.get("consecutive_failures"), 0)
        if consecutive_failures >= max(1, int(escalation_failure_threshold)):
            escalation_required_total += 1
            escalated = _safe_bool(row.get("escalated")) or "ESCALATE_TO_HUMAN" in types
            if not escalated:
                escalation_missing_total += 1

    intervention_trigger_rate = (
        0.0 if event_total == 0 else float(intervention_triggered_total) / float(event_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)
    return {
        "window_size": len(rows),
        "event_total": event_total,
        "intervention_triggered_total": intervention_triggered_total,
        "intervention_trigger_rate": intervention_trigger_rate,
        "at_risk_total": at_risk_total,
        "degraded_total": degraded_total,
        "at_risk_intervention_missing_total": at_risk_intervention_missing_total,
        "degraded_intervention_missing_total": degraded_intervention_missing_total,
        "escalation_required_total": escalation_required_total,
        "escalation_missing_total": escalation_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_intervention_trigger_rate: float,
    max_at_risk_intervention_missing_total: int,
    max_degraded_intervention_missing_total: int,
    max_escalation_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    intervention_trigger_rate = _safe_float(summary.get("intervention_trigger_rate"), 0.0)
    at_risk_intervention_missing_total = _safe_int(summary.get("at_risk_intervention_missing_total"), 0)
    degraded_intervention_missing_total = _safe_int(summary.get("degraded_intervention_missing_total"), 0)
    escalation_missing_total = _safe_int(summary.get("escalation_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"realtime intervention window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"realtime intervention event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if intervention_trigger_rate < max(0.0, float(min_intervention_trigger_rate)):
        failures.append(
            "realtime intervention trigger-rate below minimum: "
            f"{intervention_trigger_rate:.4f} < {float(min_intervention_trigger_rate):.4f}"
        )
    if at_risk_intervention_missing_total > max(0, int(max_at_risk_intervention_missing_total)):
        failures.append(
            "realtime intervention at-risk-missing total exceeded: "
            f"{at_risk_intervention_missing_total} > {int(max_at_risk_intervention_missing_total)}"
        )
    if degraded_intervention_missing_total > max(0, int(max_degraded_intervention_missing_total)):
        failures.append(
            "realtime intervention degraded-missing total exceeded: "
            f"{degraded_intervention_missing_total} > {int(max_degraded_intervention_missing_total)}"
        )
    if escalation_missing_total > max(0, int(max_escalation_missing_total)):
        failures.append(
            f"realtime intervention escalation-missing total exceeded: {escalation_missing_total} > {int(max_escalation_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"realtime intervention stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Realtime Intervention Policy Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- intervention_trigger_rate: {_safe_float(summary.get('intervention_trigger_rate'), 0.0):.4f}")
    lines.append(f"- at_risk_intervention_missing_total: {_safe_int(summary.get('at_risk_intervention_missing_total'), 0)}")
    lines.append(f"- degraded_intervention_missing_total: {_safe_int(summary.get('degraded_intervention_missing_total'), 0)}")
    lines.append(f"- escalation_missing_total: {_safe_int(summary.get('escalation_missing_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate realtime intervention policy.")
    parser.add_argument("--events-jsonl", default="var/session_quality/intervention_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_realtime_intervention_policy_guard")
    parser.add_argument("--escalation-failure-threshold", type=int, default=3)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-intervention-trigger-rate", type=float, default=0.0)
    parser.add_argument("--max-at-risk-intervention-missing-total", type=int, default=1000000)
    parser.add_argument("--max-degraded-intervention-missing-total", type=int, default=1000000)
    parser.add_argument("--max-escalation-missing-total", type=int, default=1000000)
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
    summary = summarize_realtime_intervention_policy_guard(
        rows,
        escalation_failure_threshold=max(1, int(args.escalation_failure_threshold)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_intervention_trigger_rate=max(0.0, float(args.min_intervention_trigger_rate)),
        max_at_risk_intervention_missing_total=max(0, int(args.max_at_risk_intervention_missing_total)),
        max_degraded_intervention_missing_total=max(0, int(args.max_degraded_intervention_missing_total)),
        max_escalation_missing_total=max(0, int(args.max_escalation_missing_total)),
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
                "escalation_failure_threshold": int(args.escalation_failure_threshold),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_intervention_trigger_rate": float(args.min_intervention_trigger_rate),
                "max_at_risk_intervention_missing_total": int(args.max_at_risk_intervention_missing_total),
                "max_degraded_intervention_missing_total": int(args.max_degraded_intervention_missing_total),
                "max_escalation_missing_total": int(args.max_escalation_missing_total),
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
    print(f"event_total={_safe_int(summary.get('event_total'), 0)}")
    print(f"intervention_trigger_rate={_safe_float(summary.get('intervention_trigger_rate'), 0.0):.4f}")
    print(f"at_risk_intervention_missing_total={_safe_int(summary.get('at_risk_intervention_missing_total'), 0)}")
    print(f"degraded_intervention_missing_total={_safe_int(summary.get('degraded_intervention_missing_total'), 0)}")
    print(f"escalation_missing_total={_safe_int(summary.get('escalation_missing_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
