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
        "cache_corruption_detected": "CORRUPTION_DETECTED",
        "corruption_detected": "CORRUPTION_DETECTED",
        "corruption": "CORRUPTION_DETECTED",
        "cache_fallback_origin": "ORIGIN_FALLBACK",
        "origin_fallback": "ORIGIN_FALLBACK",
        "cache_disabled": "CACHE_DISABLED",
        "disable_cache": "CACHE_DISABLED",
        "cache_fail_open": "FAIL_OPEN",
        "fail_open": "FAIL_OPEN",
        "recovery_failed": "RECOVERY_FAILED",
        "cache_recovery_failed": "RECOVERY_FAILED",
    }
    return aliases.get(text, text.upper() or "UNKNOWN")


def _incident_key(row: Mapping[str, Any]) -> str:
    for key in ("incident_id", "cache_key", "resource_id", "order_id", "shipment_id"):
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


def summarize_safety_fallback(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    corruption_detected_total = 0
    origin_fallback_total = 0
    cache_disabled_total = 0
    fail_open_total = 0
    recovery_failed_total = 0

    incidents: dict[str, dict[str, bool]] = {}

    for row in events:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event = _event_type(row.get("event_type") or row.get("event") or row.get("status"))
        key = _incident_key(row)
        if key:
            incidents.setdefault(key, {"detected": False, "handled": False, "failed": False, "fail_open": False})

        if event == "CORRUPTION_DETECTED":
            corruption_detected_total += 1
            if key:
                incidents[key]["detected"] = True
        elif event == "ORIGIN_FALLBACK":
            origin_fallback_total += 1
            if key:
                incidents[key]["handled"] = True
                if _safe_bool(row.get("success"), True) is False:
                    incidents[key]["failed"] = True
        elif event == "CACHE_DISABLED":
            cache_disabled_total += 1
            if key:
                incidents[key]["handled"] = True
        elif event == "FAIL_OPEN":
            fail_open_total += 1
            if key:
                incidents[key]["fail_open"] = True
        elif event == "RECOVERY_FAILED":
            recovery_failed_total += 1
            if key:
                incidents[key]["failed"] = True

    corruption_unhandled_total = 0
    recovery_success_total = 0
    detected_incident_total = 0
    for state in incidents.values():
        if not state.get("detected"):
            continue
        detected_incident_total += 1
        if not state.get("handled"):
            corruption_unhandled_total += 1
            continue
        if state.get("failed") or state.get("fail_open"):
            continue
        recovery_success_total += 1

    recovery_success_ratio = (
        1.0 if detected_incident_total == 0 else float(recovery_success_total) / float(detected_incident_total)
    )
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "corruption_detected_total": corruption_detected_total,
        "origin_fallback_total": origin_fallback_total,
        "cache_disabled_total": cache_disabled_total,
        "fail_open_total": fail_open_total,
        "recovery_failed_total": recovery_failed_total,
        "corruption_unhandled_total": corruption_unhandled_total,
        "recovery_success_ratio": recovery_success_ratio,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_corruption_unhandled_total: int,
    max_fail_open_total: int,
    min_recovery_success_ratio: float,
    max_recovery_failed_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    corruption_detected_total = _safe_int(summary.get("corruption_detected_total"), 0)
    corruption_unhandled_total = _safe_int(summary.get("corruption_unhandled_total"), 0)
    fail_open_total = _safe_int(summary.get("fail_open_total"), 0)
    recovery_success_ratio = _safe_float(summary.get("recovery_success_ratio"), 1.0)
    recovery_failed_total = _safe_int(summary.get("recovery_failed_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"tool cache safety fallback window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if corruption_unhandled_total > max(0, int(max_corruption_unhandled_total)):
        failures.append(
            f"tool cache corruption unhandled total exceeded: {corruption_unhandled_total} > {int(max_corruption_unhandled_total)}"
        )
    if fail_open_total > max(0, int(max_fail_open_total)):
        failures.append(f"tool cache fail-open total exceeded: {fail_open_total} > {int(max_fail_open_total)}")
    if corruption_detected_total > 0 and recovery_success_ratio < max(0.0, float(min_recovery_success_ratio)):
        failures.append(
            "tool cache recovery success ratio below threshold: "
            f"{recovery_success_ratio:.4f} < {float(min_recovery_success_ratio):.4f}"
        )
    if recovery_failed_total > max(0, int(max_recovery_failed_total)):
        failures.append(
            f"tool cache recovery failed total exceeded: {recovery_failed_total} > {int(max_recovery_failed_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"tool cache safety events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_corruption_unhandled_total_increase: int,
    max_fail_open_total_increase: int,
    max_recovery_success_ratio_drop: float,
    max_recovery_failed_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_pairs = [
        ("corruption_unhandled_total", max_corruption_unhandled_total_increase),
        ("fail_open_total", max_fail_open_total_increase),
        ("recovery_failed_total", max_recovery_failed_total_increase),
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

    base_recovery_success_ratio = _safe_float(base_summary.get("recovery_success_ratio"), 1.0)
    cur_recovery_success_ratio = _safe_float(current_summary.get("recovery_success_ratio"), 1.0)
    recovery_success_ratio_drop = max(0.0, base_recovery_success_ratio - cur_recovery_success_ratio)
    if recovery_success_ratio_drop > max(0.0, float(max_recovery_success_ratio_drop)):
        failures.append(
            "recovery success ratio regression: "
            f"baseline={base_recovery_success_ratio:.6f}, current={cur_recovery_success_ratio:.6f}, "
            f"allowed_drop={float(max_recovery_success_ratio_drop):.6f}"
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
    lines.append("# Chat Tool Cache Safety Fallback")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- corruption_detected_total: {_safe_int(summary.get('corruption_detected_total'), 0)}")
    lines.append(f"- corruption_unhandled_total: {_safe_int(summary.get('corruption_unhandled_total'), 0)}")
    lines.append(f"- fail_open_total: {_safe_int(summary.get('fail_open_total'), 0)}")
    lines.append(f"- recovery_success_ratio: {_safe_float(summary.get('recovery_success_ratio'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate cache corruption safety fallback behavior.")
    parser.add_argument("--events-jsonl", default="var/chat_tool/cache_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_cache_safety_fallback")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-corruption-unhandled-total", type=int, default=0)
    parser.add_argument("--max-fail-open-total", type=int, default=0)
    parser.add_argument("--min-recovery-success-ratio", type=float, default=0.95)
    parser.add_argument("--max-recovery-failed-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-corruption-unhandled-total-increase", type=int, default=0)
    parser.add_argument("--max-fail-open-total-increase", type=int, default=0)
    parser.add_argument("--max-recovery-success-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-recovery-failed-total-increase", type=int, default=0)
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
    summary = summarize_safety_fallback(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_corruption_unhandled_total=max(0, int(args.max_corruption_unhandled_total)),
        max_fail_open_total=max(0, int(args.max_fail_open_total)),
        min_recovery_success_ratio=max(0.0, float(args.min_recovery_success_ratio)),
        max_recovery_failed_total=max(0, int(args.max_recovery_failed_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_corruption_unhandled_total_increase=max(0, int(args.max_corruption_unhandled_total_increase)),
            max_fail_open_total_increase=max(0, int(args.max_fail_open_total_increase)),
            max_recovery_success_ratio_drop=max(0.0, float(args.max_recovery_success_ratio_drop)),
            max_recovery_failed_total_increase=max(0, int(args.max_recovery_failed_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "source": {
            "events_jsonl": str(events_path),
            "window_hours": max(1, int(args.window_hours)),
            "limit": max(1, int(args.limit)),
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
                "max_corruption_unhandled_total": int(args.max_corruption_unhandled_total),
                "max_fail_open_total": int(args.max_fail_open_total),
                "min_recovery_success_ratio": float(args.min_recovery_success_ratio),
                "max_recovery_failed_total": int(args.max_recovery_failed_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_corruption_unhandled_total_increase": int(args.max_corruption_unhandled_total_increase),
                "max_fail_open_total_increase": int(args.max_fail_open_total_increase),
                "max_recovery_success_ratio_drop": float(args.max_recovery_success_ratio_drop),
                "max_recovery_failed_total_increase": int(args.max_recovery_failed_total_increase),
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
    print(f"corruption_detected_total={_safe_int(summary.get('corruption_detected_total'), 0)}")
    print(f"recovery_success_ratio={_safe_float(summary.get('recovery_success_ratio'), 1.0):.4f}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
