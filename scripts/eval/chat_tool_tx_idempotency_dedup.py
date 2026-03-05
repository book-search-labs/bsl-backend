#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

WRITE_ACTION_TYPES = {"WRITE", "WRITE_SENSITIVE", "MUTATION"}


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


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return {str(k): v for k, v in payload.items()}


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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "resolved_at", "generated_at"):
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


def _is_write(row: Mapping[str, Any]) -> bool:
    action_type = str(row.get("action_type") or row.get("risk_level") or "").strip().upper()
    if action_type in WRITE_ACTION_TYPES:
        return True
    return _safe_bool(row.get("is_write"), False)


def _dedup_hit(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("dedup_hit"), False) or _safe_bool(row.get("idempotent_replay"), False):
        return True
    decision = str(row.get("dedup_result") or row.get("dedup_decision") or "").strip().upper()
    return decision in {"HIT", "REUSED", "REPLAY", "SKIP_SIDE_EFFECT"}


def _is_retry(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("is_retry"), False) or _safe_bool(row.get("retry"), False):
        return True
    return _safe_int(row.get("retry_count"), 0) > 0


def _side_effect_applied(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("side_effect_applied"), False):
        return True
    return _safe_int(row.get("side_effect_count"), 0) > 0


def _retry_latency_ms(row: Mapping[str, Any]) -> float:
    value = row.get("retry_resolution_latency_ms")
    if value is not None:
        return max(0.0, _safe_float(value, 0.0))
    seconds = row.get("retry_resolution_latency_seconds")
    if seconds is not None:
        return max(0.0, _safe_float(seconds, 0.0) * 1000.0)
    return 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_tool_tx_idempotency_dedup(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    tool_call_total = 0
    write_call_total = 0
    missing_idempotency_key_total = 0
    retry_call_total = 0
    dedup_hit_total = 0
    duplicate_side_effect_total = 0
    key_reuse_cross_payload_total = 0
    retry_latency_samples: list[float] = []

    key_stats: dict[str, dict[str, Any]] = {}

    for row in rows:
        tool_call_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        write_call = _is_write(row)
        if not write_call:
            continue
        write_call_total += 1

        key = str(row.get("idempotency_key") or "").strip()
        if not key:
            missing_idempotency_key_total += 1
        else:
            payload_hash = str(row.get("payload_hash") or row.get("request_hash") or "").strip()
            stats = key_stats.setdefault(key, {"payload_hashes": set(), "side_effect_applied": 0})
            if payload_hash:
                stats["payload_hashes"].add(payload_hash)
            if _side_effect_applied(row):
                stats["side_effect_applied"] += 1

        retry = _is_retry(row)
        if retry:
            retry_call_total += 1
            retry_latency_samples.append(_retry_latency_ms(row))
            if _dedup_hit(row):
                dedup_hit_total += 1

    for stats in key_stats.values():
        payload_hashes = stats.get("payload_hashes") or set()
        if len(payload_hashes) > 1:
            key_reuse_cross_payload_total += 1
        side_effect_applied = _safe_int(stats.get("side_effect_applied"), 0)
        if side_effect_applied > 1:
            duplicate_side_effect_total += side_effect_applied - 1

    retry_safe_ratio = 1.0 if retry_call_total == 0 else float(dedup_hit_total) / float(retry_call_total)
    p95_retry_resolution_latency_ms = _p95(retry_latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "tool_call_total": tool_call_total,
        "write_call_total": write_call_total,
        "missing_idempotency_key_total": missing_idempotency_key_total,
        "retry_call_total": retry_call_total,
        "dedup_hit_total": dedup_hit_total,
        "retry_safe_ratio": retry_safe_ratio,
        "duplicate_side_effect_total": duplicate_side_effect_total,
        "key_reuse_cross_payload_total": key_reuse_cross_payload_total,
        "p95_retry_resolution_latency_ms": p95_retry_resolution_latency_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_write_call_total: int,
    min_retry_safe_ratio: float,
    max_missing_idempotency_key_total: int,
    max_duplicate_side_effect_total: int,
    max_key_reuse_cross_payload_total: int,
    max_p95_retry_resolution_latency_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    write_call_total = _safe_int(summary.get("write_call_total"), 0)
    retry_safe_ratio = _safe_float(summary.get("retry_safe_ratio"), 1.0)
    missing_idempotency_key_total = _safe_int(summary.get("missing_idempotency_key_total"), 0)
    duplicate_side_effect_total = _safe_int(summary.get("duplicate_side_effect_total"), 0)
    key_reuse_cross_payload_total = _safe_int(summary.get("key_reuse_cross_payload_total"), 0)
    p95_retry_resolution_latency_ms = _safe_float(summary.get("p95_retry_resolution_latency_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat tool tx idempotency window too small: {window_size} < {int(min_window)}")
    if write_call_total < max(0, int(min_write_call_total)):
        failures.append(f"chat tool tx write call total too small: {write_call_total} < {int(min_write_call_total)}")
    if window_size == 0:
        return failures

    if retry_safe_ratio < max(0.0, float(min_retry_safe_ratio)):
        failures.append(f"chat tool tx retry-safe ratio below minimum: {retry_safe_ratio:.4f} < {float(min_retry_safe_ratio):.4f}")
    if missing_idempotency_key_total > max(0, int(max_missing_idempotency_key_total)):
        failures.append(
            f"chat tool tx missing idempotency key total exceeded: {missing_idempotency_key_total} > {int(max_missing_idempotency_key_total)}"
        )
    if duplicate_side_effect_total > max(0, int(max_duplicate_side_effect_total)):
        failures.append(
            f"chat tool tx duplicate side effect total exceeded: {duplicate_side_effect_total} > {int(max_duplicate_side_effect_total)}"
        )
    if key_reuse_cross_payload_total > max(0, int(max_key_reuse_cross_payload_total)):
        failures.append(
            "chat tool tx cross-payload key reuse total exceeded: "
            f"{key_reuse_cross_payload_total} > {int(max_key_reuse_cross_payload_total)}"
        )
    if p95_retry_resolution_latency_ms > max(0.0, float(max_p95_retry_resolution_latency_ms)):
        failures.append(
            "chat tool tx retry-resolution p95 latency exceeded: "
            f"{p95_retry_resolution_latency_ms:.2f}ms > {float(max_p95_retry_resolution_latency_ms):.2f}ms"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat tool tx idempotency stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_write_call_total_drop: int,
    max_dedup_hit_total_drop: int,
    max_retry_safe_ratio_drop: float,
    max_missing_idempotency_key_total_increase: int,
    max_duplicate_side_effect_total_increase: int,
    max_key_reuse_cross_payload_total_increase: int,
    max_p95_retry_resolution_latency_ms_increase: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("write_call_total", max_write_call_total_drop),
        ("dedup_hit_total", max_dedup_hit_total_drop),
    ]
    for key, allowed_drop in baseline_drop_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        drop = max(0, base_value - cur_value)
        if drop > max(0, int(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_drop={max(0, int(allowed_drop))}"
            )

    base_retry_safe_ratio = _safe_float(base_summary.get("retry_safe_ratio"), 1.0)
    cur_retry_safe_ratio = _safe_float(current_summary.get("retry_safe_ratio"), 1.0)
    retry_safe_ratio_drop = max(0.0, base_retry_safe_ratio - cur_retry_safe_ratio)
    if retry_safe_ratio_drop > max(0.0, float(max_retry_safe_ratio_drop)):
        failures.append(
            "retry_safe_ratio regression: "
            f"baseline={base_retry_safe_ratio:.6f}, current={cur_retry_safe_ratio:.6f}, "
            f"allowed_drop={float(max_retry_safe_ratio_drop):.6f}"
        )

    baseline_increase_pairs = [
        ("missing_idempotency_key_total", max_missing_idempotency_key_total_increase),
        ("duplicate_side_effect_total", max_duplicate_side_effect_total_increase),
        ("key_reuse_cross_payload_total", max_key_reuse_cross_payload_total_increase),
    ]
    for key, allowed_increase in baseline_increase_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        increase = max(0, cur_value - base_value)
        if increase > max(0, int(allowed_increase)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_increase={max(0, int(allowed_increase))}"
            )

    base_p95_retry_resolution_latency_ms = _safe_float(base_summary.get("p95_retry_resolution_latency_ms"), 0.0)
    cur_p95_retry_resolution_latency_ms = _safe_float(current_summary.get("p95_retry_resolution_latency_ms"), 0.0)
    p95_retry_resolution_latency_ms_increase = max(
        0.0, cur_p95_retry_resolution_latency_ms - base_p95_retry_resolution_latency_ms
    )
    if p95_retry_resolution_latency_ms_increase > max(0.0, float(max_p95_retry_resolution_latency_ms_increase)):
        failures.append(
            "p95_retry_resolution_latency_ms regression: "
            f"baseline={base_p95_retry_resolution_latency_ms:.6f}, current={cur_p95_retry_resolution_latency_ms:.6f}, "
            f"allowed_increase={float(max_p95_retry_resolution_latency_ms_increase):.6f}"
        )

    base_stale_minutes = _safe_float(base_summary.get("stale_minutes"), 0.0)
    cur_stale_minutes = _safe_float(current_summary.get("stale_minutes"), 0.0)
    stale_minutes_increase = max(0.0, cur_stale_minutes - base_stale_minutes)
    if stale_minutes_increase > max(0.0, float(max_stale_minutes_increase)):
        failures.append(
            "stale minutes regression: "
            f"baseline={base_stale_minutes:.6f}, current={cur_stale_minutes:.6f}, "
            f"allowed_increase={float(max_stale_minutes_increase):.6f}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Tool Transaction Idempotency + Dedup")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- write_call_total: {_safe_int(summary.get('write_call_total'), 0)}")
    lines.append(f"- missing_idempotency_key_total: {_safe_int(summary.get('missing_idempotency_key_total'), 0)}")
    lines.append(f"- duplicate_side_effect_total: {_safe_int(summary.get('duplicate_side_effect_total'), 0)}")
    lines.append(f"- key_reuse_cross_payload_total: {_safe_int(summary.get('key_reuse_cross_payload_total'), 0)}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    if not failures and not baseline_failures:
        lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat tool transaction idempotency/dedup quality.")
    parser.add_argument("--events-jsonl", default="var/chat_tool_tx/tx_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_tx_idempotency_dedup")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-write-call-total", type=int, default=0)
    parser.add_argument("--min-retry-safe-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-idempotency-key-total", type=int, default=0)
    parser.add_argument("--max-duplicate-side-effect-total", type=int, default=0)
    parser.add_argument("--max-key-reuse-cross-payload-total", type=int, default=0)
    parser.add_argument("--max-p95-retry-resolution-latency-ms", type=float, default=1000000.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-write-call-total-drop", type=int, default=10)
    parser.add_argument("--max-dedup-hit-total-drop", type=int, default=10)
    parser.add_argument("--max-retry-safe-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-missing-idempotency-key-total-increase", type=int, default=0)
    parser.add_argument("--max-duplicate-side-effect-total-increase", type=int, default=0)
    parser.add_argument("--max-key-reuse-cross-payload-total-increase", type=int, default=0)
    parser.add_argument("--max-p95-retry-resolution-latency-ms-increase", type=float, default=100.0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_tool_tx_idempotency_dedup(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_write_call_total=max(0, int(args.min_write_call_total)),
        min_retry_safe_ratio=max(0.0, float(args.min_retry_safe_ratio)),
        max_missing_idempotency_key_total=max(0, int(args.max_missing_idempotency_key_total)),
        max_duplicate_side_effect_total=max(0, int(args.max_duplicate_side_effect_total)),
        max_key_reuse_cross_payload_total=max(0, int(args.max_key_reuse_cross_payload_total)),
        max_p95_retry_resolution_latency_ms=max(0.0, float(args.max_p95_retry_resolution_latency_ms)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_write_call_total_drop=max(0, int(args.max_write_call_total_drop)),
            max_dedup_hit_total_drop=max(0, int(args.max_dedup_hit_total_drop)),
            max_retry_safe_ratio_drop=max(0.0, float(args.max_retry_safe_ratio_drop)),
            max_missing_idempotency_key_total_increase=max(
                0, int(args.max_missing_idempotency_key_total_increase)
            ),
            max_duplicate_side_effect_total_increase=max(0, int(args.max_duplicate_side_effect_total_increase)),
            max_key_reuse_cross_payload_total_increase=max(0, int(args.max_key_reuse_cross_payload_total_increase)),
            max_p95_retry_resolution_latency_ms_increase=max(
                0.0, float(args.max_p95_retry_resolution_latency_ms_increase)
            ),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(args.events_jsonl),
        "source": {
            "events_jsonl": str(args.events_jsonl),
            "window_hours": int(args.window_hours),
            "limit": int(args.limit),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": summary,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_write_call_total": int(args.min_write_call_total),
                "min_retry_safe_ratio": float(args.min_retry_safe_ratio),
                "max_missing_idempotency_key_total": int(args.max_missing_idempotency_key_total),
                "max_duplicate_side_effect_total": int(args.max_duplicate_side_effect_total),
                "max_key_reuse_cross_payload_total": int(args.max_key_reuse_cross_payload_total),
                "max_p95_retry_resolution_latency_ms": float(args.max_p95_retry_resolution_latency_ms),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_write_call_total_drop": int(args.max_write_call_total_drop),
                "max_dedup_hit_total_drop": int(args.max_dedup_hit_total_drop),
                "max_retry_safe_ratio_drop": float(args.max_retry_safe_ratio_drop),
                "max_missing_idempotency_key_total_increase": int(args.max_missing_idempotency_key_total_increase),
                "max_duplicate_side_effect_total_increase": int(args.max_duplicate_side_effect_total_increase),
                "max_key_reuse_cross_payload_total_increase": int(args.max_key_reuse_cross_payload_total_increase),
                "max_p95_retry_resolution_latency_ms_increase": float(args.max_p95_retry_resolution_latency_ms_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
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
    print(f"write_call_total={_safe_int(summary.get('write_call_total'), 0)}")
    print(f"missing_idempotency_key_total={_safe_int(summary.get('missing_idempotency_key_total'), 0)}")
    print(f"duplicate_side_effect_total={_safe_int(summary.get('duplicate_side_effect_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
