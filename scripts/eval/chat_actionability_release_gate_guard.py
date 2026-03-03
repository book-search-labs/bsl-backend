#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


MAX_LOW_ACTIONABILITY_RATIO_BY_BUCKET: dict[str, float] = {
    "ORDER": 0.10,
    "SHIPPING": 0.15,
    "REFUND": 0.10,
    "GENERAL": 0.20,
}

BLOCK_DECISIONS = {"BLOCK", "ROLLBACK", "HOLD", "PARTIAL_ROLLBACK", "PARTIAL_ISOLATION"}
PARTIAL_ISOLATION_DECISIONS = {"PARTIAL_ROLLBACK", "PARTIAL_ISOLATION", "ISOLATE_BUCKET"}


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


def _bucket(row: Mapping[str, Any]) -> str:
    raw = str(row.get("intent_bucket") or row.get("intent") or row.get("bucket") or "").upper()
    if "REFUND" in raw or "RETURN" in raw:
        return "REFUND"
    if "SHIP" in raw or "DELIVERY" in raw or "TRACK" in raw:
        return "SHIPPING"
    if "ORDER" in raw or "CANCEL" in raw or "PAY" in raw:
        return "ORDER"
    return "GENERAL"


def _low_actionability_ratio(row: Mapping[str, Any]) -> float:
    return max(0.0, _safe_float(row.get("low_actionability_ratio"), 0.0))


def _sample_count(row: Mapping[str, Any]) -> int:
    return max(0, _safe_int(row.get("sample_count"), _safe_int(row.get("event_count"), 0)))


def _release_decision(row: Mapping[str, Any]) -> str:
    return str(row.get("release_decision") or row.get("decision") or "").strip().upper()


def _promotion_blocked(row: Mapping[str, Any]) -> bool:
    if row.get("promotion_blocked") is not None:
        return _safe_bool(row.get("promotion_blocked"))
    if row.get("canary_promotion_allowed") is not None:
        return not _safe_bool(row.get("canary_promotion_allowed"))
    return _release_decision(row) in BLOCK_DECISIONS


def _partial_isolation_applied(row: Mapping[str, Any]) -> bool:
    if row.get("partial_isolation_applied") is not None:
        return _safe_bool(row.get("partial_isolation_applied"))
    if row.get("bucket_rollback_applied") is not None:
        return _safe_bool(row.get("bucket_rollback_applied"))
    return _release_decision(row) in PARTIAL_ISOLATION_DECISIONS


def summarize_actionability_release_gate_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    min_samples_per_bucket: int = 20,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    bucket_total = 0
    over_threshold_total = 0
    blocked_promotion_total = 0
    missed_block_total = 0
    partial_isolation_applied_total = 0
    partial_isolation_missing_total = 0
    false_block_total = 0
    not_over_threshold_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        bucket = _bucket(row)
        ratio = _low_actionability_ratio(row)
        sample_count = _sample_count(row)
        threshold = MAX_LOW_ACTIONABILITY_RATIO_BY_BUCKET.get(bucket, MAX_LOW_ACTIONABILITY_RATIO_BY_BUCKET["GENERAL"])
        over_threshold = sample_count >= max(0, int(min_samples_per_bucket)) and ratio > threshold

        bucket_total += 1
        blocked = _promotion_blocked(row)
        isolated = _partial_isolation_applied(row)

        if over_threshold:
            over_threshold_total += 1
            if blocked:
                blocked_promotion_total += 1
            else:
                missed_block_total += 1
            if isolated:
                partial_isolation_applied_total += 1
            else:
                partial_isolation_missing_total += 1
        else:
            not_over_threshold_total += 1
            if blocked:
                false_block_total += 1

    block_coverage_ratio = 1.0 if over_threshold_total == 0 else float(blocked_promotion_total) / float(over_threshold_total)
    partial_isolation_ratio = (
        1.0 if over_threshold_total == 0 else float(partial_isolation_applied_total) / float(over_threshold_total)
    )
    false_block_ratio = 0.0 if not_over_threshold_total == 0 else float(false_block_total) / float(not_over_threshold_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "bucket_total": bucket_total,
        "over_threshold_total": over_threshold_total,
        "blocked_promotion_total": blocked_promotion_total,
        "missed_block_total": missed_block_total,
        "block_coverage_ratio": block_coverage_ratio,
        "partial_isolation_applied_total": partial_isolation_applied_total,
        "partial_isolation_missing_total": partial_isolation_missing_total,
        "partial_isolation_ratio": partial_isolation_ratio,
        "false_block_total": false_block_total,
        "false_block_ratio": false_block_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_block_coverage_ratio: float,
    min_partial_isolation_ratio: float,
    max_missed_block_total: int,
    max_partial_isolation_missing_total: int,
    max_false_block_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    block_coverage_ratio = _safe_float(summary.get("block_coverage_ratio"), 0.0)
    partial_isolation_ratio = _safe_float(summary.get("partial_isolation_ratio"), 0.0)
    missed_block_total = _safe_int(summary.get("missed_block_total"), 0)
    partial_isolation_missing_total = _safe_int(summary.get("partial_isolation_missing_total"), 0)
    false_block_ratio = _safe_float(summary.get("false_block_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"actionability release gate window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"actionability release gate event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if block_coverage_ratio < max(0.0, float(min_block_coverage_ratio)):
        failures.append(
            f"actionability release gate block coverage ratio below minimum: {block_coverage_ratio:.4f} < {float(min_block_coverage_ratio):.4f}"
        )
    if partial_isolation_ratio < max(0.0, float(min_partial_isolation_ratio)):
        failures.append(
            "actionability release gate partial isolation ratio below minimum: "
            f"{partial_isolation_ratio:.4f} < {float(min_partial_isolation_ratio):.4f}"
        )
    if missed_block_total > max(0, int(max_missed_block_total)):
        failures.append(f"actionability release gate missed-block total exceeded: {missed_block_total} > {int(max_missed_block_total)}")
    if partial_isolation_missing_total > max(0, int(max_partial_isolation_missing_total)):
        failures.append(
            "actionability release gate partial-isolation-missing total exceeded: "
            f"{partial_isolation_missing_total} > {int(max_partial_isolation_missing_total)}"
        )
    if false_block_ratio > max(0.0, float(max_false_block_ratio)):
        failures.append(
            f"actionability release gate false-block ratio exceeded: {false_block_ratio:.4f} > {float(max_false_block_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"actionability release gate stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Actionability Release Gate Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- over_threshold_total: {_safe_int(summary.get('over_threshold_total'), 0)}")
    lines.append(f"- block_coverage_ratio: {_safe_float(summary.get('block_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- partial_isolation_ratio: {_safe_float(summary.get('partial_isolation_ratio'), 0.0):.4f}")
    lines.append(f"- false_block_ratio: {_safe_float(summary.get('false_block_ratio'), 0.0):.4f}")
    lines.append(f"- missed_block_total: {_safe_int(summary.get('missed_block_total'), 0)}")
    lines.append(f"- partial_isolation_missing_total: {_safe_int(summary.get('partial_isolation_missing_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate actionability release gate integration quality.")
    parser.add_argument("--events-jsonl", default="var/actionability/release_gate_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_actionability_release_gate_guard")
    parser.add_argument("--min-samples-per-bucket", type=int, default=20)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-block-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-partial-isolation-ratio", type=float, default=0.0)
    parser.add_argument("--max-missed-block-total", type=int, default=1000000)
    parser.add_argument("--max-partial-isolation-missing-total", type=int, default=1000000)
    parser.add_argument("--max-false-block-ratio", type=float, default=1.0)
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
    summary = summarize_actionability_release_gate_guard(
        rows,
        min_samples_per_bucket=max(0, int(args.min_samples_per_bucket)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_block_coverage_ratio=max(0.0, float(args.min_block_coverage_ratio)),
        min_partial_isolation_ratio=max(0.0, float(args.min_partial_isolation_ratio)),
        max_missed_block_total=max(0, int(args.max_missed_block_total)),
        max_partial_isolation_missing_total=max(0, int(args.max_partial_isolation_missing_total)),
        max_false_block_ratio=max(0.0, float(args.max_false_block_ratio)),
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
                "min_samples_per_bucket": int(args.min_samples_per_bucket),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_block_coverage_ratio": float(args.min_block_coverage_ratio),
                "min_partial_isolation_ratio": float(args.min_partial_isolation_ratio),
                "max_missed_block_total": int(args.max_missed_block_total),
                "max_partial_isolation_missing_total": int(args.max_partial_isolation_missing_total),
                "max_false_block_ratio": float(args.max_false_block_ratio),
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
    print(f"block_coverage_ratio={_safe_float(summary.get('block_coverage_ratio'), 0.0):.4f}")
    print(f"partial_isolation_ratio={_safe_float(summary.get('partial_isolation_ratio'), 0.0):.4f}")
    print(f"false_block_ratio={_safe_float(summary.get('false_block_ratio'), 0.0):.4f}")
    print(f"missed_block_total={_safe_int(summary.get('missed_block_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
