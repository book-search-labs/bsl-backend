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


def _event_type(row: Mapping[str, Any]) -> str:
    text = str(row.get("event_type") or row.get("type") or "unknown").strip().lower()
    aliases = {
        "connect": "connect",
        "open": "connect",
        "disconnect": "disconnect",
        "close": "disconnect",
        "heartbeat": "heartbeat",
        "ping": "heartbeat",
        "pong": "heartbeat",
        "reconnect": "reconnect",
        "resume": "resume",
        "failover": "failover",
    }
    return aliases.get(text, text or "unknown")


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


def summarize_durability(events: list[Mapping[str, Any]], *, heartbeat_lag_threshold_ms: float, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    open_total = 0
    close_total = 0
    heartbeat_total = 0
    heartbeat_miss_total = 0
    reconnect_total = 0
    reconnect_success_total = 0
    resume_total = 0
    resume_success_total = 0
    failover_total = 0
    affinity_miss_total = 0

    latest_ts: datetime | None = None
    reasons: dict[str, int] = {}
    active_sessions: set[str] = set()
    touched_sessions: set[str] = set()

    for row in events:
        event_type = _event_type(row)
        session_id = str(row.get("session_id") or "").strip()
        reconnect_reason = str(row.get("reconnect_reason") or row.get("reason") or "none").strip().upper()
        ts = _event_ts(row)

        if session_id:
            touched_sessions.add(session_id)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if event_type == "connect":
            open_total += 1
            if session_id:
                active_sessions.add(session_id)
        elif event_type == "disconnect":
            close_total += 1
            if session_id in active_sessions:
                active_sessions.remove(session_id)
        elif event_type == "heartbeat":
            heartbeat_total += 1
            lag_ms = max(0.0, _safe_float(row.get("heartbeat_lag_ms"), 0.0))
            if lag_ms > max(0.0, float(heartbeat_lag_threshold_ms)):
                heartbeat_miss_total += 1
        elif event_type == "reconnect":
            reconnect_total += 1
            if _safe_bool(row.get("success"), False):
                reconnect_success_total += 1
            reasons[reconnect_reason] = reasons.get(reconnect_reason, 0) + 1
        elif event_type == "resume":
            resume_total += 1
            if _safe_bool(row.get("success"), False):
                resume_success_total += 1
        elif event_type == "failover":
            failover_total += 1

        if _safe_bool(row.get("affinity_miss"), False):
            affinity_miss_total += 1

    window_size = len(events)
    reconnect_success_rate = 1.0 if reconnect_total == 0 else float(reconnect_success_total) / float(reconnect_total)
    resume_success_rate = 1.0 if resume_total == 0 else float(resume_success_total) / float(resume_total)
    heartbeat_miss_ratio = 0.0 if heartbeat_total == 0 else float(heartbeat_miss_total) / float(heartbeat_total)
    affinity_miss_ratio = 0.0 if window_size == 0 else float(affinity_miss_total) / float(window_size)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    reason_rows = [
        {"reason": reason, "count": count}
        for reason, count in sorted(reasons.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "window_size": window_size,
        "session_total": len(touched_sessions),
        "active_connection_total": len(active_sessions),
        "connect_total": open_total,
        "disconnect_total": close_total,
        "heartbeat_total": heartbeat_total,
        "heartbeat_miss_total": heartbeat_miss_total,
        "heartbeat_miss_ratio": heartbeat_miss_ratio,
        "reconnect_total": reconnect_total,
        "reconnect_success_total": reconnect_success_total,
        "reconnect_success_rate": reconnect_success_rate,
        "resume_total": resume_total,
        "resume_success_total": resume_success_total,
        "resume_success_rate": resume_success_rate,
        "failover_total": failover_total,
        "affinity_miss_total": affinity_miss_total,
        "affinity_miss_ratio": affinity_miss_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
        "reconnect_reasons": reason_rows,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_reconnect_success_rate: float,
    min_resume_success_rate: float,
    max_heartbeat_miss_ratio: float,
    max_affinity_miss_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    reconnect_success_rate = _safe_float(summary.get("reconnect_success_rate"), 1.0)
    resume_success_rate = _safe_float(summary.get("resume_success_rate"), 1.0)
    heartbeat_miss_ratio = _safe_float(summary.get("heartbeat_miss_ratio"), 0.0)
    affinity_miss_ratio = _safe_float(summary.get("affinity_miss_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"session durability window too small: {window_size} < {int(min_window)}")
    if reconnect_success_rate < max(0.0, float(min_reconnect_success_rate)):
        failures.append(
            f"reconnect success rate below threshold: {reconnect_success_rate:.4f} < {float(min_reconnect_success_rate):.4f}"
        )
    if resume_success_rate < max(0.0, float(min_resume_success_rate)):
        failures.append(f"resume success rate below threshold: {resume_success_rate:.4f} < {float(min_resume_success_rate):.4f}")
    if heartbeat_miss_ratio > max(0.0, float(max_heartbeat_miss_ratio)):
        failures.append(
            f"heartbeat miss ratio exceeded: {heartbeat_miss_ratio:.4f} > {float(max_heartbeat_miss_ratio):.4f}"
        )
    if affinity_miss_ratio > max(0.0, float(max_affinity_miss_ratio)):
        failures.append(
            f"affinity miss ratio exceeded: {affinity_miss_ratio:.4f} > {float(max_affinity_miss_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"session durability events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Session Gateway Durability")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- active_connection_total: {_safe_int(summary.get('active_connection_total'), 0)}")
    lines.append(f"- reconnect_success_rate: {_safe_float(summary.get('reconnect_success_rate'), 0.0):.4f}")
    lines.append(f"- resume_success_rate: {_safe_float(summary.get('resume_success_rate'), 0.0):.4f}")
    lines.append(f"- heartbeat_miss_ratio: {_safe_float(summary.get('heartbeat_miss_ratio'), 0.0):.4f}")
    lines.append(f"- affinity_miss_ratio: {_safe_float(summary.get('affinity_miss_ratio'), 0.0):.4f}")
    lines.append(f"- stale_minutes: {_safe_float(summary.get('stale_minutes'), 0.0):.1f}")

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
    parser = argparse.ArgumentParser(description="Evaluate chat session gateway durability/resume metrics.")
    parser.add_argument("--events-jsonl", default="var/chat_governance/session_gateway_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--heartbeat-lag-threshold-ms", type=float, default=30000.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_session_gateway_durability")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--min-reconnect-success-rate", type=float, default=0.95)
    parser.add_argument("--min-resume-success-rate", type=float, default=0.98)
    parser.add_argument("--max-heartbeat-miss-ratio", type=float, default=0.05)
    parser.add_argument("--max-affinity-miss-ratio", type=float, default=0.02)
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

    summary = summarize_durability(
        events,
        heartbeat_lag_threshold_ms=max(0.0, float(args.heartbeat_lag_threshold_ms)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_reconnect_success_rate=max(0.0, float(args.min_reconnect_success_rate)),
        min_resume_success_rate=max(0.0, float(args.min_resume_success_rate)),
        max_heartbeat_miss_ratio=max(0.0, float(args.max_heartbeat_miss_ratio)),
        max_affinity_miss_ratio=max(0.0, float(args.max_affinity_miss_ratio)),
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
                "min_reconnect_success_rate": float(args.min_reconnect_success_rate),
                "min_resume_success_rate": float(args.min_resume_success_rate),
                "max_heartbeat_miss_ratio": float(args.max_heartbeat_miss_ratio),
                "max_affinity_miss_ratio": float(args.max_affinity_miss_ratio),
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
    print(f"window_size={_safe_int(summary.get('window_size'), 0)}")
    print(f"resume_success_rate={_safe_float(summary.get('resume_success_rate'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
