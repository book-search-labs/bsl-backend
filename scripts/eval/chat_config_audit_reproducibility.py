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


def summarize_audit_reproducibility(
    events: list[Mapping[str, Any]],
    *,
    snapshots_dir: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)

    missing_actor_total = 0
    missing_bundle_total = 0
    missing_request_total = 0
    missing_trace_total = 0
    immutable_violation_total = 0
    snapshot_ref_total = 0
    snapshot_replayable_total = 0
    diff_evidence_total = 0
    latest_ts: datetime | None = None
    action_counts: dict[str, int] = {}

    for row in events:
        actor = str(row.get("actor") or row.get("user_id") or "").strip()
        bundle_id = str(row.get("bundle_id") or row.get("target") or "").strip()
        request_id = str(row.get("request_id") or "").strip()
        trace_id = str(row.get("trace_id") or "").strip()
        immutable = _safe_bool(row.get("immutable"), True)
        replayable = _safe_bool(row.get("replayable"), False)
        snapshot_id = str(row.get("snapshot_id") or "").strip()
        snapshot_path = str(row.get("snapshot_path") or "").strip()
        diff_hash = str(row.get("diff_hash") or row.get("change_diff_hash") or "").strip()
        action = str(row.get("action") or row.get("event_type") or "UNKNOWN").strip().upper() or "UNKNOWN"
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        action_counts[action] = action_counts.get(action, 0) + 1

        if not actor:
            missing_actor_total += 1
        if not bundle_id:
            missing_bundle_total += 1
        if not request_id:
            missing_request_total += 1
        if not trace_id:
            missing_trace_total += 1
        if not immutable:
            immutable_violation_total += 1

        if diff_hash:
            diff_evidence_total += 1

        snapshot_file_exists = False
        if snapshot_path:
            snapshot_file_exists = Path(snapshot_path).exists()
        elif snapshot_id:
            snapshot_file_exists = (snapshots_dir / f"{snapshot_id}.json").exists()

        if snapshot_id or snapshot_path:
            snapshot_ref_total += 1
            if replayable or snapshot_file_exists:
                snapshot_replayable_total += 1

    window_size = len(events)
    diff_coverage_ratio = 1.0 if window_size == 0 else float(diff_evidence_total) / float(window_size)
    snapshot_replay_ratio = 1.0 if snapshot_ref_total == 0 else float(snapshot_replayable_total) / float(snapshot_ref_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": window_size,
        "missing_actor_total": missing_actor_total,
        "missing_bundle_total": missing_bundle_total,
        "missing_request_total": missing_request_total,
        "missing_trace_total": missing_trace_total,
        "immutable_violation_total": immutable_violation_total,
        "snapshot_ref_total": snapshot_ref_total,
        "snapshot_replayable_total": snapshot_replayable_total,
        "snapshot_replay_ratio": snapshot_replay_ratio,
        "diff_evidence_total": diff_evidence_total,
        "diff_coverage_ratio": diff_coverage_ratio,
        "actions": [{"action": action, "count": count} for action, count in sorted(action_counts.items(), key=lambda item: item[1], reverse=True)],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_missing_actor_total: int,
    max_missing_trace_total: int,
    max_immutable_violation_total: int,
    min_snapshot_replay_ratio: float,
    min_diff_coverage_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    missing_actor_total = _safe_int(summary.get("missing_actor_total"), 0)
    missing_trace_total = _safe_int(summary.get("missing_trace_total"), 0)
    immutable_violation_total = _safe_int(summary.get("immutable_violation_total"), 0)
    snapshot_replay_ratio = _safe_float(summary.get("snapshot_replay_ratio"), 0.0)
    diff_coverage_ratio = _safe_float(summary.get("diff_coverage_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"config audit window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if missing_actor_total > max(0, int(max_missing_actor_total)):
        failures.append(f"missing actor total exceeded: {missing_actor_total} > {int(max_missing_actor_total)}")
    if missing_trace_total > max(0, int(max_missing_trace_total)):
        failures.append(f"missing trace_id total exceeded: {missing_trace_total} > {int(max_missing_trace_total)}")
    if immutable_violation_total > max(0, int(max_immutable_violation_total)):
        failures.append(
            f"immutable violation total exceeded: {immutable_violation_total} > {int(max_immutable_violation_total)}"
        )
    if snapshot_replay_ratio < max(0.0, float(min_snapshot_replay_ratio)):
        failures.append(
            f"snapshot replay ratio below threshold: {snapshot_replay_ratio:.4f} < {float(min_snapshot_replay_ratio):.4f}"
        )
    if diff_coverage_ratio < max(0.0, float(min_diff_coverage_ratio)):
        failures.append(
            f"diff coverage ratio below threshold: {diff_coverage_ratio:.4f} < {float(min_diff_coverage_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"config audit events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Config Audit Reproducibility")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- snapshots_dir: {payload.get('snapshots_dir')}")
    lines.append(f"- window_size: {_safe_int(summary.get('window_size'), 0)}")
    lines.append(f"- missing_actor_total: {_safe_int(summary.get('missing_actor_total'), 0)}")
    lines.append(f"- missing_trace_total: {_safe_int(summary.get('missing_trace_total'), 0)}")
    lines.append(f"- immutable_violation_total: {_safe_int(summary.get('immutable_violation_total'), 0)}")
    lines.append(f"- snapshot_replay_ratio: {_safe_float(summary.get('snapshot_replay_ratio'), 0.0):.4f}")
    lines.append(f"- diff_coverage_ratio: {_safe_float(summary.get('diff_coverage_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate config audit completeness and snapshot reproducibility.")
    parser.add_argument("--events-jsonl", default="var/chat_control/config_audit_events.jsonl")
    parser.add_argument("--snapshots-dir", default="var/chat_control/snapshots")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_config_audit_reproducibility")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-missing-actor-total", type=int, default=0)
    parser.add_argument("--max-missing-trace-total", type=int, default=0)
    parser.add_argument("--max-immutable-violation-total", type=int, default=0)
    parser.add_argument("--min-snapshot-replay-ratio", type=float, default=0.95)
    parser.add_argument("--min-diff-coverage-ratio", type=float, default=0.95)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    events_path = Path(args.events_jsonl)
    snapshots_dir = Path(args.snapshots_dir)

    events = read_events(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_audit_reproducibility(events, snapshots_dir=snapshots_dir)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_missing_actor_total=max(0, int(args.max_missing_actor_total)),
        max_missing_trace_total=max(0, int(args.max_missing_trace_total)),
        max_immutable_violation_total=max(0, int(args.max_immutable_violation_total)),
        min_snapshot_replay_ratio=max(0.0, float(args.min_snapshot_replay_ratio)),
        min_diff_coverage_ratio=max(0.0, float(args.min_diff_coverage_ratio)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "snapshots_dir": str(snapshots_dir),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_missing_actor_total": int(args.max_missing_actor_total),
                "max_missing_trace_total": int(args.max_missing_trace_total),
                "max_immutable_violation_total": int(args.max_immutable_violation_total),
                "min_snapshot_replay_ratio": float(args.min_snapshot_replay_ratio),
                "min_diff_coverage_ratio": float(args.min_diff_coverage_ratio),
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
    print(f"snapshot_replay_ratio={_safe_float(summary.get('snapshot_replay_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
