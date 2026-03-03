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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _event_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "cache_hit": "CACHE_HIT",
        "cache_response": "CACHE_RESPONSE",
        "response": "CACHE_RESPONSE",
        "origin_fetch": "ORIGIN_FETCH",
        "fallback_origin": "ORIGIN_FETCH",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _is_cache_response(event: str) -> bool:
    return event in {"CACHE_HIT", "CACHE_RESPONSE"}


def _is_stale(row: Mapping[str, Any], *, stale_threshold_seconds: int) -> bool:
    cache_age_seconds = _safe_int(row.get("cache_age_seconds") or row.get("age_seconds"), -1)
    threshold = _safe_int(row.get("stale_threshold_seconds"), stale_threshold_seconds)
    if cache_age_seconds < 0:
        return False
    return cache_age_seconds > max(0, threshold)


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
        if isinstance(payload, Mapping):
            rows.append({str(k): v for k, v in payload.items()})
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


def summarize_staleness_guard(
    events: list[Mapping[str, Any]],
    *,
    stale_threshold_seconds: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    cache_response_total = 0
    stale_response_total = 0
    stale_block_total = 0
    stale_leak_total = 0
    freshness_stamp_missing_total = 0
    forced_origin_fetch_total = 0

    for row in events:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event = _event_type(row.get("event_type") or row.get("event") or row.get("status"))
        if not _is_cache_response(event):
            continue

        cache_response_total += 1
        freshness_stamp = str(row.get("freshness_stamp") or row.get("cached_at") or row.get("cache_timestamp") or "").strip()
        if not freshness_stamp:
            freshness_stamp_missing_total += 1

        stale = _is_stale(row, stale_threshold_seconds=stale_threshold_seconds)
        if not stale:
            continue
        stale_response_total += 1

        stale_blocked = _safe_bool(row.get("stale_blocked"), False)
        forced_origin = _safe_bool(row.get("forced_origin_fetch") or row.get("origin_fetch"), False)
        served_from_cache = _safe_bool(row.get("served_from_cache"), True)

        if stale_blocked or forced_origin:
            stale_block_total += 1
        if forced_origin:
            forced_origin_fetch_total += 1
        if served_from_cache and not stale_blocked and not forced_origin:
            stale_leak_total += 1

    stale_block_ratio = (
        1.0 if stale_response_total == 0 else float(stale_block_total) / float(stale_response_total)
    )
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "cache_response_total": cache_response_total,
        "stale_response_total": stale_response_total,
        "stale_block_total": stale_block_total,
        "stale_leak_total": stale_leak_total,
        "stale_block_ratio": stale_block_ratio,
        "freshness_stamp_missing_total": freshness_stamp_missing_total,
        "forced_origin_fetch_total": forced_origin_fetch_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_stale_leak_total: int,
    min_stale_block_ratio: float,
    max_freshness_stamp_missing_total: int,
    min_forced_origin_fetch_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    stale_response_total = _safe_int(summary.get("stale_response_total"), 0)
    stale_leak_total = _safe_int(summary.get("stale_leak_total"), 0)
    stale_block_ratio = _safe_float(summary.get("stale_block_ratio"), 1.0)
    freshness_stamp_missing_total = _safe_int(summary.get("freshness_stamp_missing_total"), 0)
    forced_origin_fetch_total = _safe_int(summary.get("forced_origin_fetch_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"tool cache staleness window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if stale_leak_total > max(0, int(max_stale_leak_total)):
        failures.append(f"tool cache stale leak total exceeded: {stale_leak_total} > {int(max_stale_leak_total)}")
    if stale_response_total > 0 and stale_block_ratio < max(0.0, float(min_stale_block_ratio)):
        failures.append(
            f"tool cache stale block ratio below threshold: {stale_block_ratio:.4f} < {float(min_stale_block_ratio):.4f}"
        )
    if freshness_stamp_missing_total > max(0, int(max_freshness_stamp_missing_total)):
        failures.append(
            "tool cache freshness stamp missing total exceeded: "
            f"{freshness_stamp_missing_total} > {int(max_freshness_stamp_missing_total)}"
        )
    if forced_origin_fetch_total < max(0, int(min_forced_origin_fetch_total)):
        failures.append(
            f"tool cache forced origin fetch total below threshold: {forced_origin_fetch_total} < {int(min_forced_origin_fetch_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"tool cache staleness events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Tool Cache Staleness Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- stale_response_total: {_safe_int(summary.get('stale_response_total'), 0)}")
    lines.append(f"- stale_block_total: {_safe_int(summary.get('stale_block_total'), 0)}")
    lines.append(f"- stale_leak_total: {_safe_int(summary.get('stale_leak_total'), 0)}")
    lines.append(f"- stale_block_ratio: {_safe_float(summary.get('stale_block_ratio'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat tool cache staleness guard behavior.")
    parser.add_argument("--events-jsonl", default="var/chat_tool/cache_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--stale-threshold-seconds", type=int, default=300)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_cache_staleness_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-stale-leak-total", type=int, default=0)
    parser.add_argument("--min-stale-block-ratio", type=float, default=0.95)
    parser.add_argument("--max-freshness-stamp-missing-total", type=int, default=0)
    parser.add_argument("--min-forced-origin-fetch-total", type=int, default=0)
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
    summary = summarize_staleness_guard(
        events,
        stale_threshold_seconds=max(0, int(args.stale_threshold_seconds)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_stale_leak_total=max(0, int(args.max_stale_leak_total)),
        min_stale_block_ratio=max(0.0, float(args.min_stale_block_ratio)),
        max_freshness_stamp_missing_total=max(0, int(args.max_freshness_stamp_missing_total)),
        min_forced_origin_fetch_total=max(0, int(args.min_forced_origin_fetch_total)),
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
                "max_stale_leak_total": int(args.max_stale_leak_total),
                "min_stale_block_ratio": float(args.min_stale_block_ratio),
                "max_freshness_stamp_missing_total": int(args.max_freshness_stamp_missing_total),
                "min_forced_origin_fetch_total": int(args.min_forced_origin_fetch_total),
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
    print(f"stale_response_total={_safe_int(summary.get('stale_response_total'), 0)}")
    print(f"stale_leak_total={_safe_int(summary.get('stale_leak_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
