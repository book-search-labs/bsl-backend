#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

TTL_POLICY = {
    "SHORT": (30, 300),
    "MEDIUM": (301, 3600),
    "LONG": (3601, 86400),
}


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


def _event_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "hit": "CACHE_HIT",
        "cache_hit": "CACHE_HIT",
        "miss": "CACHE_MISS",
        "cache_miss": "CACHE_MISS",
        "set": "CACHE_SET",
        "cache_set": "CACHE_SET",
        "invalidate": "CACHE_INVALIDATE",
        "cache_invalidate": "CACHE_INVALIDATE",
        "bypass": "CACHE_BYPASS",
        "cache_bypass": "CACHE_BYPASS",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _ttl_class(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in TTL_POLICY:
        return text
    return "UNKNOWN"


def _key_missing_fields(row: Mapping[str, Any]) -> int:
    missing = 0
    user_id = str(row.get("user_id") or row.get("actor_id") or "").strip()
    tool = str(row.get("tool") or row.get("tool_name") or "").strip()
    params_hash = str(row.get("params_hash") or row.get("args_hash") or "").strip()
    if not user_id:
        missing += 1
    if not tool:
        missing += 1
    if not params_hash:
        missing += 1
    return missing


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


def summarize_cache_strategy(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    lookup_total = 0
    cache_hit_total = 0
    cache_miss_total = 0
    cache_bypass_total = 0
    key_missing_field_total = 0
    ttl_class_unknown_total = 0
    ttl_out_of_policy_total = 0

    for row in events:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event = _event_type(row.get("event_type") or row.get("event") or row.get("status"))
        if event in {"CACHE_HIT", "CACHE_MISS", "CACHE_BYPASS"}:
            lookup_total += 1
        if event == "CACHE_HIT":
            cache_hit_total += 1
        elif event == "CACHE_MISS":
            cache_miss_total += 1
        elif event == "CACHE_BYPASS":
            cache_bypass_total += 1

        if event in {"CACHE_HIT", "CACHE_MISS", "CACHE_SET"}:
            key_missing_field_total += _key_missing_fields(row)
            ttl_class = _ttl_class(row.get("ttl_class"))
            ttl_seconds = _safe_int(row.get("ttl_seconds"), -1)
            if ttl_class == "UNKNOWN":
                ttl_class_unknown_total += 1
            else:
                lower, upper = TTL_POLICY[ttl_class]
                if ttl_seconds < lower or ttl_seconds > upper:
                    ttl_out_of_policy_total += 1

    hit_ratio = 1.0 if lookup_total == 0 else float(cache_hit_total) / float(lookup_total)
    bypass_ratio = 0.0 if lookup_total == 0 else float(cache_bypass_total) / float(lookup_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "lookup_total": lookup_total,
        "cache_hit_total": cache_hit_total,
        "cache_miss_total": cache_miss_total,
        "cache_bypass_total": cache_bypass_total,
        "hit_ratio": hit_ratio,
        "bypass_ratio": bypass_ratio,
        "key_missing_field_total": key_missing_field_total,
        "ttl_class_unknown_total": ttl_class_unknown_total,
        "ttl_out_of_policy_total": ttl_out_of_policy_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_hit_ratio: float,
    max_bypass_ratio: float,
    max_key_missing_field_total: int,
    max_ttl_class_unknown_total: int,
    max_ttl_out_of_policy_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    lookup_total = _safe_int(summary.get("lookup_total"), 0)
    hit_ratio = _safe_float(summary.get("hit_ratio"), 1.0)
    bypass_ratio = _safe_float(summary.get("bypass_ratio"), 0.0)
    key_missing_field_total = _safe_int(summary.get("key_missing_field_total"), 0)
    ttl_class_unknown_total = _safe_int(summary.get("ttl_class_unknown_total"), 0)
    ttl_out_of_policy_total = _safe_int(summary.get("ttl_out_of_policy_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"tool cache window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if lookup_total > 0 and hit_ratio < max(0.0, float(min_hit_ratio)):
        failures.append(f"tool cache hit ratio below threshold: {hit_ratio:.4f} < {float(min_hit_ratio):.4f}")
    if lookup_total > 0 and bypass_ratio > max(0.0, float(max_bypass_ratio)):
        failures.append(f"tool cache bypass ratio exceeded: {bypass_ratio:.4f} > {float(max_bypass_ratio):.4f}")
    if key_missing_field_total > max(0, int(max_key_missing_field_total)):
        failures.append(
            f"tool cache key missing field total exceeded: {key_missing_field_total} > {int(max_key_missing_field_total)}"
        )
    if ttl_class_unknown_total > max(0, int(max_ttl_class_unknown_total)):
        failures.append(f"tool cache unknown ttl_class total exceeded: {ttl_class_unknown_total} > {int(max_ttl_class_unknown_total)}")
    if ttl_out_of_policy_total > max(0, int(max_ttl_out_of_policy_total)):
        failures.append(
            f"tool cache ttl out-of-policy total exceeded: {ttl_out_of_policy_total} > {int(max_ttl_out_of_policy_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"tool cache events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Tool Cache Strategy")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- lookup_total: {_safe_int(summary.get('lookup_total'), 0)}")
    lines.append(f"- cache_hit_total: {_safe_int(summary.get('cache_hit_total'), 0)}")
    lines.append(f"- hit_ratio: {_safe_float(summary.get('hit_ratio'), 1.0):.4f}")
    lines.append(f"- ttl_out_of_policy_total: {_safe_int(summary.get('ttl_out_of_policy_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat tool cache strategy quality.")
    parser.add_argument("--events-jsonl", default="var/chat_tool/cache_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_cache_strategy")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-hit-ratio", type=float, default=0.5)
    parser.add_argument("--max-bypass-ratio", type=float, default=0.3)
    parser.add_argument("--max-key-missing-field-total", type=int, default=0)
    parser.add_argument("--max-ttl-class-unknown-total", type=int, default=0)
    parser.add_argument("--max-ttl-out-of-policy-total", type=int, default=0)
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
    summary = summarize_cache_strategy(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_hit_ratio=max(0.0, float(args.min_hit_ratio)),
        max_bypass_ratio=max(0.0, float(args.max_bypass_ratio)),
        max_key_missing_field_total=max(0, int(args.max_key_missing_field_total)),
        max_ttl_class_unknown_total=max(0, int(args.max_ttl_class_unknown_total)),
        max_ttl_out_of_policy_total=max(0, int(args.max_ttl_out_of_policy_total)),
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
                "min_hit_ratio": float(args.min_hit_ratio),
                "max_bypass_ratio": float(args.max_bypass_ratio),
                "max_key_missing_field_total": int(args.max_key_missing_field_total),
                "max_ttl_class_unknown_total": int(args.max_ttl_class_unknown_total),
                "max_ttl_out_of_policy_total": int(args.max_ttl_out_of_policy_total),
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
    print(f"lookup_total={_safe_int(summary.get('lookup_total'), 0)}")
    print(f"hit_ratio={_safe_float(summary.get('hit_ratio'), 1.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
