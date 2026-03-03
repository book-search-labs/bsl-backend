#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


ALT_PATH_ACTIONS = {
    "PARTIAL_REFUND",
    "EXCHANGE",
    "OPEN_SUPPORT_TICKET",
}


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


def _action_type(row: Mapping[str, Any]) -> str:
    return str(row.get("action_type") or row.get("simulation_action") or "").strip().upper()


def _is_simulation_event(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("simulation_run")):
        return True
    return bool(_action_type(row))


def _is_refund_action(action_type: str) -> bool:
    return "REFUND" in action_type


def _is_shipping_option_action(action_type: str) -> bool:
    return "SHIPPING" in action_type or "DELIVERY_OPTION" in action_type


def _policy_blocked(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("policy_blocked")):
        return True
    result = str(row.get("simulation_result") or "").strip().upper()
    return result in {"BLOCKED", "DENIED", "NOT_ALLOWED"}


def _has_alternative_path(row: Mapping[str, Any]) -> bool:
    alt = row.get("alternative_paths")
    if isinstance(alt, list):
        return any(str(item).strip() for item in alt)
    next_action = str(row.get("next_action") or "").strip().upper()
    return next_action in ALT_PATH_ACTIONS


def _refund_estimate_present(row: Mapping[str, Any]) -> bool:
    amount = row.get("estimated_refund_amount")
    fee = row.get("estimated_fee")
    return amount is not None and fee is not None


def _shipping_estimate_present(row: Mapping[str, Any]) -> bool:
    fee = row.get("estimated_shipping_fee")
    eta = row.get("estimated_arrival_days")
    return fee is not None and eta is not None


def _simulation_executed(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("execution_done")) or row.get("executed_value") is not None


def _estimate_value(row: Mapping[str, Any]) -> float | None:
    if row.get("estimated_value") is not None:
        return _safe_float(row.get("estimated_value"), 0.0)
    if row.get("estimated_refund_amount") is not None:
        return _safe_float(row.get("estimated_refund_amount"), 0.0)
    if row.get("estimated_shipping_fee") is not None:
        return _safe_float(row.get("estimated_shipping_fee"), 0.0)
    return None


def _executed_value(row: Mapping[str, Any]) -> float | None:
    if row.get("executed_value") is not None:
        return _safe_float(row.get("executed_value"), 0.0)
    if row.get("executed_refund_amount") is not None:
        return _safe_float(row.get("executed_refund_amount"), 0.0)
    if row.get("executed_shipping_fee") is not None:
        return _safe_float(row.get("executed_shipping_fee"), 0.0)
    return None


def summarize_action_simulation_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    max_value_drift: float = 0.0,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    simulation_total = 0
    refund_simulation_total = 0
    shipping_option_simulation_total = 0
    missing_estimate_fields_total = 0
    policy_blocked_total = 0
    policy_blocked_alt_path_missing_total = 0
    execution_drift_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        if not _is_simulation_event(row):
            continue
        simulation_total += 1

        action_type = _action_type(row)
        if _is_refund_action(action_type):
            refund_simulation_total += 1
            if not _refund_estimate_present(row):
                missing_estimate_fields_total += 1
        elif _is_shipping_option_action(action_type):
            shipping_option_simulation_total += 1
            if not _shipping_estimate_present(row):
                missing_estimate_fields_total += 1

        blocked = _policy_blocked(row)
        if blocked:
            policy_blocked_total += 1
            if not _has_alternative_path(row):
                policy_blocked_alt_path_missing_total += 1

        if _simulation_executed(row):
            estimate = _estimate_value(row)
            executed = _executed_value(row)
            if estimate is not None and executed is not None:
                if abs(estimate - executed) > max(0.0, float(max_value_drift)):
                    execution_drift_total += 1

    simulation_coverage_rate = 0.0 if event_total == 0 else float(simulation_total) / float(event_total)
    blocked_alt_path_ratio = 1.0 if policy_blocked_total == 0 else 1.0 - (
        float(policy_blocked_alt_path_missing_total) / float(policy_blocked_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "simulation_total": simulation_total,
        "simulation_coverage_rate": simulation_coverage_rate,
        "refund_simulation_total": refund_simulation_total,
        "shipping_option_simulation_total": shipping_option_simulation_total,
        "missing_estimate_fields_total": missing_estimate_fields_total,
        "policy_blocked_total": policy_blocked_total,
        "policy_blocked_alt_path_missing_total": policy_blocked_alt_path_missing_total,
        "blocked_alt_path_ratio": blocked_alt_path_ratio,
        "execution_drift_total": execution_drift_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_simulation_coverage_rate: float,
    min_blocked_alt_path_ratio: float,
    max_missing_estimate_fields_total: int,
    max_execution_drift_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    simulation_coverage_rate = _safe_float(summary.get("simulation_coverage_rate"), 0.0)
    blocked_alt_path_ratio = _safe_float(summary.get("blocked_alt_path_ratio"), 0.0)
    missing_estimate_fields_total = _safe_int(summary.get("missing_estimate_fields_total"), 0)
    execution_drift_total = _safe_int(summary.get("execution_drift_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"action simulation window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"action simulation event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if simulation_coverage_rate < max(0.0, float(min_simulation_coverage_rate)):
        failures.append(
            f"action simulation coverage rate below minimum: {simulation_coverage_rate:.4f} < {float(min_simulation_coverage_rate):.4f}"
        )
    if blocked_alt_path_ratio < max(0.0, float(min_blocked_alt_path_ratio)):
        failures.append(
            f"action simulation blocked-alt-path ratio below minimum: {blocked_alt_path_ratio:.4f} < {float(min_blocked_alt_path_ratio):.4f}"
        )
    if missing_estimate_fields_total > max(0, int(max_missing_estimate_fields_total)):
        failures.append(
            f"action simulation missing-estimate-fields total exceeded: {missing_estimate_fields_total} > {int(max_missing_estimate_fields_total)}"
        )
    if execution_drift_total > max(0, int(max_execution_drift_total)):
        failures.append(
            f"action simulation execution-drift total exceeded: {execution_drift_total} > {int(max_execution_drift_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"action simulation stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Action Simulation Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- simulation_coverage_rate: {_safe_float(summary.get('simulation_coverage_rate'), 0.0):.4f}")
    lines.append(f"- blocked_alt_path_ratio: {_safe_float(summary.get('blocked_alt_path_ratio'), 0.0):.4f}")
    lines.append(f"- missing_estimate_fields_total: {_safe_int(summary.get('missing_estimate_fields_total'), 0)}")
    lines.append(f"- execution_drift_total: {_safe_int(summary.get('execution_drift_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate action simulation quality.")
    parser.add_argument("--events-jsonl", default="var/resolution_plan/simulation_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_action_simulation_guard")
    parser.add_argument("--max-value-drift", type=float, default=0.0)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-simulation-coverage-rate", type=float, default=0.0)
    parser.add_argument("--min-blocked-alt-path-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-estimate-fields-total", type=int, default=1000000)
    parser.add_argument("--max-execution-drift-total", type=int, default=1000000)
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
    summary = summarize_action_simulation_guard(
        rows,
        max_value_drift=max(0.0, float(args.max_value_drift)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_simulation_coverage_rate=max(0.0, float(args.min_simulation_coverage_rate)),
        min_blocked_alt_path_ratio=max(0.0, float(args.min_blocked_alt_path_ratio)),
        max_missing_estimate_fields_total=max(0, int(args.max_missing_estimate_fields_total)),
        max_execution_drift_total=max(0, int(args.max_execution_drift_total)),
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
                "max_value_drift": float(args.max_value_drift),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_simulation_coverage_rate": float(args.min_simulation_coverage_rate),
                "min_blocked_alt_path_ratio": float(args.min_blocked_alt_path_ratio),
                "max_missing_estimate_fields_total": int(args.max_missing_estimate_fields_total),
                "max_execution_drift_total": int(args.max_execution_drift_total),
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
    print(f"simulation_coverage_rate={_safe_float(summary.get('simulation_coverage_rate'), 0.0):.4f}")
    print(f"blocked_alt_path_ratio={_safe_float(summary.get('blocked_alt_path_ratio'), 0.0):.4f}")
    print(f"missing_estimate_fields_total={_safe_int(summary.get('missing_estimate_fields_total'), 0)}")
    print(f"execution_drift_total={_safe_int(summary.get('execution_drift_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
