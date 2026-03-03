#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH"}


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


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
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


def _normalize_severity(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"L": "LOW", "M": "MEDIUM", "H": "HIGH"}
    if text in VALID_SEVERITIES:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _is_queued(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("queued"), False):
        return True
    status = str(row.get("queue_status") or row.get("status") or "").strip().upper()
    if status in {"QUEUED", "ACKED", "IN_PROGRESS", "RESOLVED", "CLOSED"}:
        return True
    return False


def _is_acknowledged(row: Mapping[str, Any]) -> bool:
    if _parse_ts(row.get("acknowledged_at")) is not None:
        return True
    status = str(row.get("queue_status") or row.get("status") or "").strip().upper()
    return status in {"ACKED", "IN_PROGRESS", "RESOLVED", "CLOSED"}


def _is_resolved(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("resolved"), False):
        return True
    if _parse_ts(row.get("resolved_at")) is not None:
        return True
    status = str(row.get("queue_status") or row.get("status") or "").strip().upper()
    return status in {"RESOLVED", "CLOSED"}


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return float(ordered[idx])


def summarize_operator_feedback(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    conflict_total = 0
    queued_total = 0
    acknowledged_total = 0
    resolved_total = 0
    high_conflict_total = 0
    high_conflict_queued_total = 0
    high_conflict_unqueued_total = 0
    missing_operator_note_total = 0
    ack_latencies: list[float] = []
    resolution_latencies: list[float] = []

    for row in rows:
        conflict_id = str(row.get("conflict_id") or row.get("id") or "").strip()
        if not conflict_id:
            continue
        conflict_total += 1

        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        severity = _normalize_severity(row.get("conflict_severity") or row.get("severity"))
        queued = _is_queued(row)
        acknowledged = _is_acknowledged(row)
        resolved = _is_resolved(row)

        if queued:
            queued_total += 1
        if acknowledged:
            acknowledged_total += 1
        if resolved:
            resolved_total += 1

        queued_at = _parse_ts(row.get("queued_at")) or _parse_ts(row.get("queue_time")) or _event_ts(row)
        acknowledged_at = _parse_ts(row.get("acknowledged_at")) or _parse_ts(row.get("ack_at"))
        resolved_at = _parse_ts(row.get("resolved_at")) or _parse_ts(row.get("closed_at"))

        if queued_at is not None and acknowledged_at is not None:
            ack_latencies.append(max(0.0, (acknowledged_at - queued_at).total_seconds() / 60.0))
        if queued_at is not None and resolved_at is not None:
            resolution_latencies.append(max(0.0, (resolved_at - queued_at).total_seconds() / 60.0))

        if severity == "HIGH":
            high_conflict_total += 1
            if queued:
                high_conflict_queued_total += 1
            else:
                high_conflict_unqueued_total += 1

        if resolved and not str(row.get("operator_note") or row.get("resolution_note") or "").strip():
            missing_operator_note_total += 1

    queue_coverage_ratio = 1.0 if conflict_total == 0 else float(queued_total) / float(conflict_total)
    high_queue_coverage_ratio = (
        1.0 if high_conflict_total == 0 else float(high_conflict_queued_total) / float(high_conflict_total)
    )
    resolved_ratio = 1.0 if conflict_total == 0 else float(resolved_total) / float(conflict_total)
    p95_ack_latency_minutes = _p95(ack_latencies)
    p95_resolution_latency_minutes = _p95(resolution_latencies)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "conflict_total": conflict_total,
        "queued_total": queued_total,
        "acknowledged_total": acknowledged_total,
        "resolved_total": resolved_total,
        "high_conflict_total": high_conflict_total,
        "high_conflict_queued_total": high_conflict_queued_total,
        "high_conflict_unqueued_total": high_conflict_unqueued_total,
        "queue_coverage_ratio": queue_coverage_ratio,
        "high_queue_coverage_ratio": high_queue_coverage_ratio,
        "resolved_ratio": resolved_ratio,
        "p95_ack_latency_minutes": p95_ack_latency_minutes,
        "p95_resolution_latency_minutes": p95_resolution_latency_minutes,
        "missing_operator_note_total": missing_operator_note_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_high_conflict_unqueued_total: int,
    min_high_queue_coverage_ratio: float,
    min_resolved_ratio: float,
    max_p95_ack_latency_minutes: float,
    max_missing_operator_note_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    high_conflict_unqueued_total = _safe_int(summary.get("high_conflict_unqueued_total"), 0)
    high_queue_coverage_ratio = _safe_float(summary.get("high_queue_coverage_ratio"), 1.0)
    resolved_ratio = _safe_float(summary.get("resolved_ratio"), 1.0)
    p95_ack_latency_minutes = _safe_float(summary.get("p95_ack_latency_minutes"), 0.0)
    missing_operator_note_total = _safe_int(summary.get("missing_operator_note_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"source conflict operator feedback window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if high_conflict_unqueued_total > max(0, int(max_high_conflict_unqueued_total)):
        failures.append(
            "source conflict high-severity unqueued total exceeded: "
            f"{high_conflict_unqueued_total} > {int(max_high_conflict_unqueued_total)}"
        )
    if high_queue_coverage_ratio < max(0.0, float(min_high_queue_coverage_ratio)):
        failures.append(
            "source conflict high-severity queue coverage below threshold: "
            f"{high_queue_coverage_ratio:.4f} < {float(min_high_queue_coverage_ratio):.4f}"
        )
    if resolved_ratio < max(0.0, float(min_resolved_ratio)):
        failures.append(f"source conflict resolved ratio below threshold: {resolved_ratio:.4f} < {float(min_resolved_ratio):.4f}")
    if p95_ack_latency_minutes > max(0.0, float(max_p95_ack_latency_minutes)):
        failures.append(
            f"source conflict operator ack p95 latency exceeded: {p95_ack_latency_minutes:.1f}m > {float(max_p95_ack_latency_minutes):.1f}m"
        )
    if missing_operator_note_total > max(0, int(max_missing_operator_note_total)):
        failures.append(
            f"source conflict missing operator note total exceeded: {missing_operator_note_total} > {int(max_missing_operator_note_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"source conflict operator feedback stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Source Conflict Operator Feedback")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- conflict_total: {_safe_int(summary.get('conflict_total'), 0)}")
    lines.append(f"- high_conflict_unqueued_total: {_safe_int(summary.get('high_conflict_unqueued_total'), 0)}")
    lines.append(f"- high_queue_coverage_ratio: {_safe_float(summary.get('high_queue_coverage_ratio'), 1.0):.4f}")
    lines.append(f"- resolved_ratio: {_safe_float(summary.get('resolved_ratio'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate source conflict operator feedback loop.")
    parser.add_argument("--events-jsonl", default="var/chat_trust/source_conflict_operator_queue.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_source_conflict_operator_feedback")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-high-conflict-unqueued-total", type=int, default=0)
    parser.add_argument("--min-high-queue-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-resolved-ratio", type=float, default=0.0)
    parser.add_argument("--max-p95-ack-latency-minutes", type=float, default=60.0)
    parser.add_argument("--max-missing-operator-note-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_operator_feedback(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_high_conflict_unqueued_total=max(0, int(args.max_high_conflict_unqueued_total)),
        min_high_queue_coverage_ratio=max(0.0, float(args.min_high_queue_coverage_ratio)),
        min_resolved_ratio=max(0.0, float(args.min_resolved_ratio)),
        max_p95_ack_latency_minutes=max(0.0, float(args.max_p95_ack_latency_minutes)),
        max_missing_operator_note_total=max(0, int(args.max_missing_operator_note_total)),
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
                "min_window": int(args.min_window),
                "max_high_conflict_unqueued_total": int(args.max_high_conflict_unqueued_total),
                "min_high_queue_coverage_ratio": float(args.min_high_queue_coverage_ratio),
                "min_resolved_ratio": float(args.min_resolved_ratio),
                "max_p95_ack_latency_minutes": float(args.max_p95_ack_latency_minutes),
                "max_missing_operator_note_total": int(args.max_missing_operator_note_total),
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
    print(f"high_conflict_unqueued_total={_safe_int(summary.get('high_conflict_unqueued_total'), 0)}")
    print(f"high_queue_coverage_ratio={_safe_float(summary.get('high_queue_coverage_ratio'), 1.0):.4f}")
    print(f"resolved_ratio={_safe_float(summary.get('resolved_ratio'), 1.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
