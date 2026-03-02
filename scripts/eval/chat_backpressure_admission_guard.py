#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

CORE_PRIORITIES = {"P0", "CRITICAL", "HIGH"}


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


def _priority(row: Mapping[str, Any]) -> str:
    text = str(row.get("priority") or row.get("priority_class") or "NORMAL").strip().upper()
    if text in {"CRITICAL", "P0"}:
        return "CRITICAL"
    if text in {"HIGH", "P1"}:
        return "HIGH"
    if text in {"LOW", "P3"}:
        return "LOW"
    return "NORMAL"


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


def summarize_backpressure(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    drop_total = 0
    admitted_total = 0
    critical_drop_total = 0
    core_total = 0
    core_admitted_total = 0
    circuit_open_total = 0
    guidance_missing_total = 0

    by_priority: dict[str, dict[str, int]] = {}
    mode_counts: dict[str, int] = {}
    queue_depth_samples: list[float] = []
    queue_latency_samples: list[float] = []
    latest_ts: datetime | None = None

    for row in events:
        priority = _priority(row)
        dropped = _safe_bool(row.get("dropped"), False)
        admitted = _safe_bool(row.get("admitted"), not dropped)
        queue_depth = max(0, _safe_float(row.get("queue_depth"), 0.0))
        queue_latency_ms = max(0, _safe_float(row.get("queue_latency_ms"), 0.0))
        mode = str(row.get("backpressure_mode") or row.get("mode") or "NORMAL").strip().upper() or "NORMAL"
        circuit_open = _safe_bool(row.get("circuit_open"), mode in {"OPEN", "FAIL_CLOSED"})
        guidance_sent = _safe_bool(row.get("user_guidance_sent"), False)
        core_intent = _safe_bool(row.get("core_intent"), priority in CORE_PRIORITIES)
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        queue_depth_samples.append(queue_depth)
        queue_latency_samples.append(queue_latency_ms)
        mode_counts[mode] = mode_counts.get(mode, 0) + 1

        pri_row = by_priority.setdefault(priority, {"total": 0, "dropped": 0, "admitted": 0})
        pri_row["total"] += 1

        if admitted:
            admitted_total += 1
            pri_row["admitted"] += 1
        if dropped:
            drop_total += 1
            pri_row["dropped"] += 1
            if priority in CORE_PRIORITIES:
                critical_drop_total += 1

        if core_intent:
            core_total += 1
            if admitted:
                core_admitted_total += 1

        if circuit_open:
            circuit_open_total += 1
            if not guidance_sent:
                guidance_missing_total += 1

    window_size = len(events)
    drop_ratio = 0.0 if window_size == 0 else float(drop_total) / float(window_size)
    core_protected_ratio = 1.0 if core_total == 0 else float(core_admitted_total) / float(core_total)
    p95_queue_depth = _percentile(queue_depth_samples, 0.95)
    p95_queue_latency_ms = _percentile(queue_latency_samples, 0.95)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    priority_rows = [
        {
            "priority": priority,
            "total": values["total"],
            "dropped": values["dropped"],
            "admitted": values["admitted"],
        }
        for priority, values in sorted(by_priority.items(), key=lambda item: (-item[1]["dropped"], -item[1]["total"], item[0]))
    ]

    mode_rows = [
        {"mode": mode, "count": count}
        for mode, count in sorted(mode_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "window_size": window_size,
        "drop_total": drop_total,
        "admitted_total": admitted_total,
        "drop_ratio": drop_ratio,
        "critical_drop_total": critical_drop_total,
        "core_total": core_total,
        "core_admitted_total": core_admitted_total,
        "core_protected_ratio": core_protected_ratio,
        "p95_queue_depth": p95_queue_depth,
        "p95_queue_latency_ms": p95_queue_latency_ms,
        "circuit_open_total": circuit_open_total,
        "guidance_missing_total": guidance_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
        "by_priority": priority_rows,
        "modes": mode_rows,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_drop_ratio: float,
    max_critical_drop_total: int,
    min_core_protected_ratio: float,
    max_p95_queue_depth: float,
    max_p95_queue_latency_ms: float,
    max_guidance_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []

    window_size = _safe_int(summary.get("window_size"), 0)
    drop_ratio = _safe_float(summary.get("drop_ratio"), 0.0)
    critical_drop_total = _safe_int(summary.get("critical_drop_total"), 0)
    core_protected_ratio = _safe_float(summary.get("core_protected_ratio"), 1.0)
    p95_queue_depth = _safe_float(summary.get("p95_queue_depth"), 0.0)
    p95_queue_latency_ms = _safe_float(summary.get("p95_queue_latency_ms"), 0.0)
    guidance_missing_total = _safe_int(summary.get("guidance_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"backpressure window too small: {window_size} < {int(min_window)}")
    if drop_ratio > max(0.0, float(max_drop_ratio)):
        failures.append(f"drop ratio exceeded: {drop_ratio:.4f} > {float(max_drop_ratio):.4f}")
    if critical_drop_total > max(0, int(max_critical_drop_total)):
        failures.append(f"critical drop count exceeded: {critical_drop_total} > {int(max_critical_drop_total)}")
    if core_protected_ratio < max(0.0, float(min_core_protected_ratio)):
        failures.append(
            f"core intent protected ratio below threshold: {core_protected_ratio:.4f} < {float(min_core_protected_ratio):.4f}"
        )
    if p95_queue_depth > max(0.0, float(max_p95_queue_depth)):
        failures.append(f"p95 queue depth exceeded: {p95_queue_depth:.1f} > {float(max_p95_queue_depth):.1f}")
    if p95_queue_latency_ms > max(0.0, float(max_p95_queue_latency_ms)):
        failures.append(
            f"p95 queue latency exceeded: {p95_queue_latency_ms:.1f} > {float(max_p95_queue_latency_ms):.1f}"
        )
    if guidance_missing_total > max(0, int(max_guidance_missing_total)):
        failures.append(
            f"circuit-open guidance missing exceeded: {guidance_missing_total} > {int(max_guidance_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"backpressure logs stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Backpressure Admission Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- drop_ratio: {_safe_float(summary.get('drop_ratio'), 0.0):.4f}")
    lines.append(f"- critical_drop_total: {_safe_int(summary.get('critical_drop_total'), 0)}")
    lines.append(f"- core_protected_ratio: {_safe_float(summary.get('core_protected_ratio'), 0.0):.4f}")
    lines.append(f"- p95_queue_depth: {_safe_float(summary.get('p95_queue_depth'), 0.0):.1f}")
    lines.append(f"- p95_queue_latency_ms: {_safe_float(summary.get('p95_queue_latency_ms'), 0.0):.1f}")
    lines.append(f"- guidance_missing_total: {_safe_int(summary.get('guidance_missing_total'), 0)}")

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
    parser = argparse.ArgumentParser(description="Evaluate chat backpressure/admission control behavior from runtime events.")
    parser.add_argument("--events-jsonl", default="var/chat_governance/backpressure_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_backpressure_admission_guard")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-drop-ratio", type=float, default=0.20)
    parser.add_argument("--max-critical-drop-total", type=int, default=0)
    parser.add_argument("--min-core-protected-ratio", type=float, default=0.98)
    parser.add_argument("--max-p95-queue-depth", type=float, default=80.0)
    parser.add_argument("--max-p95-queue-latency-ms", type=float, default=3000.0)
    parser.add_argument("--max-guidance-missing-total", type=int, default=0)
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

    summary = summarize_backpressure(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_drop_ratio=max(0.0, float(args.max_drop_ratio)),
        max_critical_drop_total=max(0, int(args.max_critical_drop_total)),
        min_core_protected_ratio=max(0.0, float(args.min_core_protected_ratio)),
        max_p95_queue_depth=max(0.0, float(args.max_p95_queue_depth)),
        max_p95_queue_latency_ms=max(0.0, float(args.max_p95_queue_latency_ms)),
        max_guidance_missing_total=max(0, int(args.max_guidance_missing_total)),
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
                "max_drop_ratio": float(args.max_drop_ratio),
                "max_critical_drop_total": int(args.max_critical_drop_total),
                "min_core_protected_ratio": float(args.min_core_protected_ratio),
                "max_p95_queue_depth": float(args.max_p95_queue_depth),
                "max_p95_queue_latency_ms": float(args.max_p95_queue_latency_ms),
                "max_guidance_missing_total": int(args.max_guidance_missing_total),
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
    print(f"core_protected_ratio={_safe_float(summary.get('core_protected_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
