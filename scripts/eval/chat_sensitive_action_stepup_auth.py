#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

HIGH_RISK_VALUES = {"HIGH", "WRITE_SENSITIVE"}


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
        "stepup_challenge_issued": "STEPUP_CHALLENGE_ISSUED",
        "stepup_required": "STEPUP_CHALLENGE_ISSUED",
        "stepup_verified": "STEPUP_VERIFIED",
        "stepup_passed": "STEPUP_VERIFIED",
        "stepup_failed": "STEPUP_FAILED",
        "stepup_timeout": "STEPUP_TIMEOUT",
        "auth_timeout": "STEPUP_TIMEOUT",
        "blocked": "BLOCKED",
        "deny": "BLOCKED",
        "handoff": "HANDOFF",
        "escalate": "HANDOFF",
        "execute": "EXECUTED",
        "executed": "EXECUTED",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _normalize_risk(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "H": "HIGH",
        "M": "MEDIUM",
        "L": "LOW",
        "WRITE_SENSITIVE": "WRITE_SENSITIVE",
        "WRITE": "MEDIUM",
    }
    return aliases.get(text, text or "UNKNOWN")


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


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * min(1.0, max(0.0, ratio))))
    index = max(0, min(len(ordered) - 1, index))
    return float(ordered[index])


def summarize_stepup_auth(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None
    grouped: dict[str, list[dict[str, Any]]] = {}

    for row in events:
        action_id = _action_id(row)
        if not action_id:
            continue
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        grouped.setdefault(action_id, []).append(
            {
                "event": _normalize_event(row.get("event_type") or row.get("event") or row.get("status")),
                "risk": _normalize_risk(row.get("risk_level") or row.get("risk")),
                "stepup_required": bool(row.get("stepup_required") or row.get("requires_stepup_auth")),
                "ts": ts,
            }
        )

    high_risk_total = 0
    stepup_required_total = 0
    stepup_challenge_total = 0
    stepup_verified_total = 0
    stepup_failure_total = 0
    stepup_failure_blocked_total = 0
    high_risk_execute_without_stepup_total = 0
    stepup_failed_then_execute_total = 0
    stepup_latency_samples: list[float] = []

    for rows in grouped.values():
        ordered = sorted(
            rows,
            key=lambda item: item["ts"] if isinstance(item["ts"], datetime) else datetime.min.replace(tzinfo=timezone.utc),
        )
        high_risk = any(str(item.get("risk")) in HIGH_RISK_VALUES for item in ordered)
        requires_stepup = any(bool(item.get("stepup_required")) for item in ordered) or high_risk

        if high_risk:
            high_risk_total += 1
        if requires_stepup:
            stepup_required_total += 1

        challenge_at: datetime | None = None
        verified = False
        failed = False
        blocked_or_handoff = False

        for item in ordered:
            event = str(item.get("event") or "UNKNOWN")
            ts = item.get("ts") if isinstance(item.get("ts"), datetime) else None
            if event == "STEPUP_CHALLENGE_ISSUED":
                stepup_challenge_total += 1
                challenge_at = ts
            elif event == "STEPUP_VERIFIED":
                stepup_verified_total += 1
                verified = True
                if challenge_at is not None and ts is not None:
                    stepup_latency_samples.append(max(0.0, (ts - challenge_at).total_seconds()))
            elif event in {"STEPUP_FAILED", "STEPUP_TIMEOUT"}:
                stepup_failure_total += 1
                failed = True
            elif event in {"BLOCKED", "HANDOFF"}:
                blocked_or_handoff = True
            elif event == "EXECUTED":
                if high_risk and not verified:
                    high_risk_execute_without_stepup_total += 1
                if failed and not blocked_or_handoff:
                    stepup_failed_then_execute_total += 1

        if failed and blocked_or_handoff:
            stepup_failure_blocked_total += 1

    stepup_failure_block_ratio = (
        1.0 if stepup_failure_total == 0 else float(stepup_failure_blocked_total) / float(stepup_failure_total)
    )
    stepup_latency_p95_sec = _percentile(stepup_latency_samples, 0.95)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "action_total": len(grouped),
        "high_risk_total": high_risk_total,
        "stepup_required_total": stepup_required_total,
        "stepup_challenge_total": stepup_challenge_total,
        "stepup_verified_total": stepup_verified_total,
        "stepup_failure_total": stepup_failure_total,
        "stepup_failure_blocked_total": stepup_failure_blocked_total,
        "stepup_failure_block_ratio": stepup_failure_block_ratio,
        "high_risk_execute_without_stepup_total": high_risk_execute_without_stepup_total,
        "stepup_failed_then_execute_total": stepup_failed_then_execute_total,
        "stepup_latency_p95_sec": stepup_latency_p95_sec,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_high_risk_execute_without_stepup_total: int,
    max_stepup_failed_then_execute_total: int,
    min_stepup_failure_block_ratio: float,
    max_stepup_latency_p95_sec: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    high_risk_execute_without_stepup_total = _safe_int(summary.get("high_risk_execute_without_stepup_total"), 0)
    stepup_failed_then_execute_total = _safe_int(summary.get("stepup_failed_then_execute_total"), 0)
    stepup_failure_block_ratio = _safe_float(summary.get("stepup_failure_block_ratio"), 1.0)
    stepup_latency_p95_sec = _safe_float(summary.get("stepup_latency_p95_sec"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"sensitive step-up auth window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if high_risk_execute_without_stepup_total > max(0, int(max_high_risk_execute_without_stepup_total)):
        failures.append(
            "high risk execute without step-up total exceeded: "
            f"{high_risk_execute_without_stepup_total} > {int(max_high_risk_execute_without_stepup_total)}"
        )
    if stepup_failed_then_execute_total > max(0, int(max_stepup_failed_then_execute_total)):
        failures.append(
            "step-up failed but execute continued total exceeded: "
            f"{stepup_failed_then_execute_total} > {int(max_stepup_failed_then_execute_total)}"
        )
    if stepup_failure_block_ratio < max(0.0, float(min_stepup_failure_block_ratio)):
        failures.append(
            f"step-up failure block ratio below threshold: {stepup_failure_block_ratio:.4f} < {float(min_stepup_failure_block_ratio):.4f}"
        )
    if stepup_latency_p95_sec > max(0.0, float(max_stepup_latency_p95_sec)):
        failures.append(
            f"step-up auth latency p95 exceeded: {stepup_latency_p95_sec:.1f}s > {float(max_stepup_latency_p95_sec):.1f}s"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"sensitive step-up auth events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Sensitive Action Step-up Auth")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- high_risk_total: {_safe_int(summary.get('high_risk_total'), 0)}")
    lines.append(f"- stepup_required_total: {_safe_int(summary.get('stepup_required_total'), 0)}")
    lines.append(
        f"- high_risk_execute_without_stepup_total: {_safe_int(summary.get('high_risk_execute_without_stepup_total'), 0)}"
    )
    lines.append(f"- stepup_failure_block_ratio: {_safe_float(summary.get('stepup_failure_block_ratio'), 1.0):.4f}")
    lines.append(f"- stepup_latency_p95_sec: {_safe_float(summary.get('stepup_latency_p95_sec'), 0.0):.1f}")
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
    parser = argparse.ArgumentParser(description="Evaluate high-risk step-up authentication policy.")
    parser.add_argument("--events-jsonl", default="var/chat_actions/sensitive_action_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_sensitive_action_stepup_auth")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-high-risk-execute-without-stepup-total", type=int, default=0)
    parser.add_argument("--max-stepup-failed-then-execute-total", type=int, default=0)
    parser.add_argument("--min-stepup-failure-block-ratio", type=float, default=1.0)
    parser.add_argument("--max-stepup-latency-p95-sec", type=float, default=300.0)
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
    summary = summarize_stepup_auth(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_high_risk_execute_without_stepup_total=max(0, int(args.max_high_risk_execute_without_stepup_total)),
        max_stepup_failed_then_execute_total=max(0, int(args.max_stepup_failed_then_execute_total)),
        min_stepup_failure_block_ratio=max(0.0, float(args.min_stepup_failure_block_ratio)),
        max_stepup_latency_p95_sec=max(0.0, float(args.max_stepup_latency_p95_sec)),
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
                "max_high_risk_execute_without_stepup_total": int(args.max_high_risk_execute_without_stepup_total),
                "max_stepup_failed_then_execute_total": int(args.max_stepup_failed_then_execute_total),
                "min_stepup_failure_block_ratio": float(args.min_stepup_failure_block_ratio),
                "max_stepup_latency_p95_sec": float(args.max_stepup_latency_p95_sec),
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
    print(f"high_risk_total={_safe_int(summary.get('high_risk_total'), 0)}")
    print(
        "high_risk_execute_without_stepup_total="
        f"{_safe_int(summary.get('high_risk_execute_without_stepup_total'), 0)}"
    )

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
