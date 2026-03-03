#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

DOMAIN_EVENT_TYPES = {
    "ORDER_STATUS_EVENT",
    "SHIPPING_STATUS_EVENT",
    "ORDER_UPDATED",
    "SHIPPING_UPDATED",
    "TOOL_DOMAIN_EVENT",
}
INVALIDATE_EVENT_TYPES = {"CACHE_INVALIDATE", "INVALIDATE"}


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
        "domain_event": "TOOL_DOMAIN_EVENT",
        "order_status_event": "ORDER_STATUS_EVENT",
        "shipping_status_event": "SHIPPING_STATUS_EVENT",
        "order_updated": "ORDER_UPDATED",
        "shipping_updated": "SHIPPING_UPDATED",
        "cache_invalidate": "CACHE_INVALIDATE",
        "invalidate": "INVALIDATE",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _resource_key(row: Mapping[str, Any]) -> str:
    for key in ("order_id", "shipment_id", "resource_id", "entity_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def summarize_cache_invalidation(
    events: list[Mapping[str, Any]],
    *,
    max_invalidate_lag_minutes: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    domain_event_total = 0
    invalidate_total = 0
    domain_key_missing_total = 0
    invalidation_reason_missing_total = 0
    missing_invalidate_total = 0
    late_invalidate_total = 0

    domain_events: list[tuple[str, datetime]] = []
    invalidate_by_key: dict[str, list[datetime]] = {}

    for row in events:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event = _event_type(row.get("event_type") or row.get("event") or row.get("status"))
        if event in DOMAIN_EVENT_TYPES:
            if _safe_bool(row.get("requires_invalidation"), True):
                domain_event_total += 1
                key = _resource_key(row)
                if not key:
                    domain_key_missing_total += 1
                elif ts is not None:
                    domain_events.append((key, ts))
        elif event in INVALIDATE_EVENT_TYPES:
            invalidate_total += 1
            key = _resource_key(row)
            if key and ts is not None:
                invalidate_by_key.setdefault(key, []).append(ts)
            reason = str(row.get("reason") or row.get("invalidate_reason") or "").strip()
            if not reason:
                invalidation_reason_missing_total += 1

    max_lag_seconds = max(0.0, float(max_invalidate_lag_minutes) * 60.0)
    for key, domain_ts in domain_events:
        candidates = invalidate_by_key.get(key, [])
        matched: datetime | None = None
        for invalidate_ts in candidates:
            if invalidate_ts >= domain_ts:
                matched = invalidate_ts
                break
        if matched is None:
            missing_invalidate_total += 1
            continue
        lag_seconds = (matched - domain_ts).total_seconds()
        if lag_seconds > max_lag_seconds:
            late_invalidate_total += 1

    coverage_ratio = (
        1.0 if domain_event_total == 0 else float(domain_event_total - missing_invalidate_total) / float(domain_event_total)
    )
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "domain_event_total": domain_event_total,
        "invalidate_total": invalidate_total,
        "coverage_ratio": coverage_ratio,
        "domain_key_missing_total": domain_key_missing_total,
        "invalidation_reason_missing_total": invalidation_reason_missing_total,
        "missing_invalidate_total": missing_invalidate_total,
        "late_invalidate_total": late_invalidate_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_coverage_ratio: float,
    max_domain_key_missing_total: int,
    max_invalidation_reason_missing_total: int,
    max_missing_invalidate_total: int,
    max_late_invalidate_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    domain_event_total = _safe_int(summary.get("domain_event_total"), 0)
    coverage_ratio = _safe_float(summary.get("coverage_ratio"), 1.0)
    domain_key_missing_total = _safe_int(summary.get("domain_key_missing_total"), 0)
    invalidation_reason_missing_total = _safe_int(summary.get("invalidation_reason_missing_total"), 0)
    missing_invalidate_total = _safe_int(summary.get("missing_invalidate_total"), 0)
    late_invalidate_total = _safe_int(summary.get("late_invalidate_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"tool cache invalidation window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if domain_event_total > 0 and coverage_ratio < max(0.0, float(min_coverage_ratio)):
        failures.append(
            f"tool cache invalidation coverage ratio below threshold: {coverage_ratio:.4f} < {float(min_coverage_ratio):.4f}"
        )
    if domain_key_missing_total > max(0, int(max_domain_key_missing_total)):
        failures.append(
            f"tool cache invalidation domain key missing total exceeded: {domain_key_missing_total} > {int(max_domain_key_missing_total)}"
        )
    if invalidation_reason_missing_total > max(0, int(max_invalidation_reason_missing_total)):
        failures.append(
            "tool cache invalidation reason missing total exceeded: "
            f"{invalidation_reason_missing_total} > {int(max_invalidation_reason_missing_total)}"
        )
    if missing_invalidate_total > max(0, int(max_missing_invalidate_total)):
        failures.append(
            f"tool cache invalidation missing invalidate total exceeded: {missing_invalidate_total} > {int(max_missing_invalidate_total)}"
        )
    if late_invalidate_total > max(0, int(max_late_invalidate_total)):
        failures.append(
            f"tool cache invalidation late invalidate total exceeded: {late_invalidate_total} > {int(max_late_invalidate_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"tool cache invalidation events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_coverage_ratio_drop: float,
    max_domain_key_missing_total_increase: int,
    max_invalidation_reason_missing_total_increase: int,
    max_missing_invalidate_total_increase: int,
    max_late_invalidate_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_coverage_ratio = _safe_float(base_summary.get("coverage_ratio"), 1.0)
    cur_coverage_ratio = _safe_float(current_summary.get("coverage_ratio"), 1.0)
    coverage_ratio_drop = max(0.0, base_coverage_ratio - cur_coverage_ratio)
    if coverage_ratio_drop > max(0.0, float(max_coverage_ratio_drop)):
        failures.append(
            "coverage ratio regression: "
            f"baseline={base_coverage_ratio:.6f}, current={cur_coverage_ratio:.6f}, "
            f"allowed_drop={float(max_coverage_ratio_drop):.6f}"
        )

    baseline_pairs = [
        ("domain_key_missing_total", max_domain_key_missing_total_increase),
        ("invalidation_reason_missing_total", max_invalidation_reason_missing_total_increase),
        ("missing_invalidate_total", max_missing_invalidate_total_increase),
        ("late_invalidate_total", max_late_invalidate_total_increase),
    ]
    for key, allowed_increase in baseline_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        increase = max(0, cur_value - base_value)
        if increase > max(0, int(allowed_increase)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_increase={max(0, int(allowed_increase))}"
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
    lines.append("# Chat Tool Cache Invalidation")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- domain_event_total: {_safe_int(summary.get('domain_event_total'), 0)}")
    lines.append(f"- invalidate_total: {_safe_int(summary.get('invalidate_total'), 0)}")
    lines.append(f"- coverage_ratio: {_safe_float(summary.get('coverage_ratio'), 1.0):.4f}")
    lines.append(f"- late_invalidate_total: {_safe_int(summary.get('late_invalidate_total'), 0)}")
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
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate event-driven chat tool cache invalidation quality.")
    parser.add_argument("--events-jsonl", default="var/chat_tool/cache_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--max-invalidate-lag-minutes", type=float, default=5.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_cache_invalidation")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-coverage-ratio", type=float, default=0.95)
    parser.add_argument("--max-domain-key-missing-total", type=int, default=0)
    parser.add_argument("--max-invalidation-reason-missing-total", type=int, default=0)
    parser.add_argument("--max-missing-invalidate-total", type=int, default=0)
    parser.add_argument("--max-late-invalidate-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-coverage-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-domain-key-missing-total-increase", type=int, default=0)
    parser.add_argument("--max-invalidation-reason-missing-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-invalidate-total-increase", type=int, default=0)
    parser.add_argument("--max-late-invalidate-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
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
    summary = summarize_cache_invalidation(
        events,
        max_invalidate_lag_minutes=max(0.0, float(args.max_invalidate_lag_minutes)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_coverage_ratio=max(0.0, float(args.min_coverage_ratio)),
        max_domain_key_missing_total=max(0, int(args.max_domain_key_missing_total)),
        max_invalidation_reason_missing_total=max(0, int(args.max_invalidation_reason_missing_total)),
        max_missing_invalidate_total=max(0, int(args.max_missing_invalidate_total)),
        max_late_invalidate_total=max(0, int(args.max_late_invalidate_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_coverage_ratio_drop=max(0.0, float(args.max_coverage_ratio_drop)),
            max_domain_key_missing_total_increase=max(0, int(args.max_domain_key_missing_total_increase)),
            max_invalidation_reason_missing_total_increase=max(
                0, int(args.max_invalidation_reason_missing_total_increase)
            ),
            max_missing_invalidate_total_increase=max(0, int(args.max_missing_invalidate_total_increase)),
            max_late_invalidate_total_increase=max(0, int(args.max_late_invalidate_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": max(1, int(args.window_hours)),
            "limit": max(1, int(args.limit)),
            "max_invalidate_lag_minutes": max(0.0, float(args.max_invalidate_lag_minutes)),
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
                "min_coverage_ratio": float(args.min_coverage_ratio),
                "max_domain_key_missing_total": int(args.max_domain_key_missing_total),
                "max_invalidation_reason_missing_total": int(args.max_invalidation_reason_missing_total),
                "max_missing_invalidate_total": int(args.max_missing_invalidate_total),
                "max_late_invalidate_total": int(args.max_late_invalidate_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_coverage_ratio_drop": float(args.max_coverage_ratio_drop),
                "max_domain_key_missing_total_increase": int(args.max_domain_key_missing_total_increase),
                "max_invalidation_reason_missing_total_increase": int(
                    args.max_invalidation_reason_missing_total_increase
                ),
                "max_missing_invalidate_total_increase": int(args.max_missing_invalidate_total_increase),
                "max_late_invalidate_total_increase": int(args.max_late_invalidate_total_increase),
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
    print(f"domain_event_total={_safe_int(summary.get('domain_event_total'), 0)}")
    print(f"coverage_ratio={_safe_float(summary.get('coverage_ratio'), 1.0):.4f}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
