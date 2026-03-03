#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


DEFAULT_PREFLIGHT_CHECKS = {"authz", "inventory", "state_transition"}


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


def _is_write_action(row: Mapping[str, Any]) -> bool:
    risk = str(row.get("risk_level") or "").strip().upper()
    if risk.startswith("WRITE"):
        return True
    action_type = str(row.get("action_type") or "").strip()
    return bool(action_type)


def _required_preflight_checks(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("required_preflight_checks")
    if isinstance(raw, list):
        values = {str(item).strip().lower() for item in raw if str(item).strip()}
        if values:
            return values
    return set(DEFAULT_PREFLIGHT_CHECKS)


def _preflight_check_keys(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("preflight_checks")
    if isinstance(raw, Mapping):
        return {str(key).strip().lower() for key in raw.keys() if str(key).strip()}
    if isinstance(raw, list):
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    text = str(row.get("preflight_check_names") or "").strip()
    if text:
        return {item.strip().lower() for item in text.split(",") if item.strip()}
    keys: set[str] = set()
    if row.get("authz_passed") is not None:
        keys.add("authz")
    if row.get("inventory_passed") is not None:
        keys.add("inventory")
    if row.get("state_transition_passed") is not None:
        keys.add("state_transition")
    return keys


def _preflight_passed(row: Mapping[str, Any]) -> bool:
    explicit = row.get("preflight_passed")
    if explicit is not None:
        return _safe_bool(explicit)
    authz = row.get("authz_passed")
    inventory = row.get("inventory_passed")
    transition = row.get("state_transition_passed")
    values = [item for item in (authz, inventory, transition) if item is not None]
    if values:
        return all(_safe_bool(item) for item in values)
    return True


def _execution_attempted(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("execution_attempted")):
        return True
    status = str(row.get("execution_status") or "").strip().upper()
    if status in {"EXECUTED", "FAILED", "ABORTED"}:
        return True
    return row.get("executed_value") is not None


def _simulation_mismatch(row: Mapping[str, Any], *, max_outcome_drift: float) -> bool:
    simulated = row.get("simulated_value")
    executed = row.get("executed_value")
    if simulated is None or executed is None:
        return False
    return abs(_safe_float(simulated, 0.0) - _safe_float(executed, 0.0)) > max(0.0, float(max_outcome_drift))


def _execution_aborted(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("execution_aborted")):
        return True
    status = str(row.get("execution_status") or "").strip().upper()
    return status == "ABORTED"


def _ops_alert_sent(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("ops_alert_sent")):
        return True
    return _safe_bool(row.get("operator_alerted"))


def _idempotency_key_present(row: Mapping[str, Any]) -> bool:
    key = str(row.get("idempotency_key") or "").strip()
    return bool(key)


def _duplicate_detected(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("duplicate_request")):
        return True
    if _safe_bool(row.get("is_duplicate")):
        return True
    return False


def _idempotency_replayed(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("idempotency_replayed")):
        return True
    if _safe_bool(row.get("dedup_applied")):
        return True
    result = str(row.get("execution_result") or "").strip().upper()
    return result == "IDEMPOTENT_REPLAY"


def summarize_execution_safety_contract_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    max_outcome_drift: float = 0.0,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    write_action_total = 0
    preflight_checked_total = 0
    missing_preflight_checks_total = 0
    preflight_block_violation_total = 0
    simulation_mismatch_total = 0
    mismatch_abort_missing_total = 0
    mismatch_alert_missing_total = 0
    idempotency_missing_total = 0
    duplicate_unsafe_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        if not _is_write_action(row):
            continue
        write_action_total += 1

        required_checks = _required_preflight_checks(row)
        present_checks = _preflight_check_keys(row)
        if required_checks.issubset(present_checks):
            preflight_checked_total += 1
        else:
            missing_preflight_checks_total += 1

        preflight_passed = _preflight_passed(row)
        execution_attempted = _execution_attempted(row)
        if (not preflight_passed) and execution_attempted:
            preflight_block_violation_total += 1

        if _simulation_mismatch(row, max_outcome_drift=max_outcome_drift):
            simulation_mismatch_total += 1
            if not _execution_aborted(row):
                mismatch_abort_missing_total += 1
            if not _ops_alert_sent(row):
                mismatch_alert_missing_total += 1

        if not _idempotency_key_present(row):
            idempotency_missing_total += 1

        if _duplicate_detected(row) and execution_attempted and not _idempotency_replayed(row):
            duplicate_unsafe_total += 1

    preflight_check_coverage_ratio = (
        1.0 if write_action_total == 0 else float(preflight_checked_total) / float(write_action_total)
    )
    idempotency_coverage_ratio = (
        1.0 if write_action_total == 0 else 1.0 - (float(idempotency_missing_total) / float(write_action_total))
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "write_action_total": write_action_total,
        "preflight_checked_total": preflight_checked_total,
        "preflight_check_coverage_ratio": preflight_check_coverage_ratio,
        "missing_preflight_checks_total": missing_preflight_checks_total,
        "preflight_block_violation_total": preflight_block_violation_total,
        "simulation_mismatch_total": simulation_mismatch_total,
        "mismatch_abort_missing_total": mismatch_abort_missing_total,
        "mismatch_alert_missing_total": mismatch_alert_missing_total,
        "idempotency_missing_total": idempotency_missing_total,
        "idempotency_coverage_ratio": idempotency_coverage_ratio,
        "duplicate_unsafe_total": duplicate_unsafe_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_preflight_check_coverage_ratio: float,
    min_idempotency_coverage_ratio: float,
    max_preflight_block_violation_total: int,
    max_mismatch_abort_missing_total: int,
    max_mismatch_alert_missing_total: int,
    max_duplicate_unsafe_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    preflight_check_coverage_ratio = _safe_float(summary.get("preflight_check_coverage_ratio"), 0.0)
    idempotency_coverage_ratio = _safe_float(summary.get("idempotency_coverage_ratio"), 0.0)
    preflight_block_violation_total = _safe_int(summary.get("preflight_block_violation_total"), 0)
    mismatch_abort_missing_total = _safe_int(summary.get("mismatch_abort_missing_total"), 0)
    mismatch_alert_missing_total = _safe_int(summary.get("mismatch_alert_missing_total"), 0)
    duplicate_unsafe_total = _safe_int(summary.get("duplicate_unsafe_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"execution safety window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"execution safety event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if preflight_check_coverage_ratio < max(0.0, float(min_preflight_check_coverage_ratio)):
        failures.append(
            "execution safety preflight-check coverage below minimum: "
            f"{preflight_check_coverage_ratio:.4f} < {float(min_preflight_check_coverage_ratio):.4f}"
        )
    if idempotency_coverage_ratio < max(0.0, float(min_idempotency_coverage_ratio)):
        failures.append(
            "execution safety idempotency coverage below minimum: "
            f"{idempotency_coverage_ratio:.4f} < {float(min_idempotency_coverage_ratio):.4f}"
        )
    if preflight_block_violation_total > max(0, int(max_preflight_block_violation_total)):
        failures.append(
            f"execution safety preflight-block violation exceeded: {preflight_block_violation_total} > {int(max_preflight_block_violation_total)}"
        )
    if mismatch_abort_missing_total > max(0, int(max_mismatch_abort_missing_total)):
        failures.append(
            f"execution safety mismatch-abort-missing exceeded: {mismatch_abort_missing_total} > {int(max_mismatch_abort_missing_total)}"
        )
    if mismatch_alert_missing_total > max(0, int(max_mismatch_alert_missing_total)):
        failures.append(
            f"execution safety mismatch-alert-missing exceeded: {mismatch_alert_missing_total} > {int(max_mismatch_alert_missing_total)}"
        )
    if duplicate_unsafe_total > max(0, int(max_duplicate_unsafe_total)):
        failures.append(
            f"execution safety duplicate-unsafe exceeded: {duplicate_unsafe_total} > {int(max_duplicate_unsafe_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"execution safety stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Execution Safety Contract Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- preflight_check_coverage_ratio: {_safe_float(summary.get('preflight_check_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- idempotency_coverage_ratio: {_safe_float(summary.get('idempotency_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- preflight_block_violation_total: {_safe_int(summary.get('preflight_block_violation_total'), 0)}")
    lines.append(f"- mismatch_abort_missing_total: {_safe_int(summary.get('mismatch_abort_missing_total'), 0)}")
    lines.append(f"- mismatch_alert_missing_total: {_safe_int(summary.get('mismatch_alert_missing_total'), 0)}")
    lines.append(f"- duplicate_unsafe_total: {_safe_int(summary.get('duplicate_unsafe_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate execution safety contract.")
    parser.add_argument("--events-jsonl", default="var/resolution_plan/execution_safety_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_execution_safety_contract_guard")
    parser.add_argument("--max-outcome-drift", type=float, default=0.0)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-preflight-check-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-idempotency-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-preflight-block-violation-total", type=int, default=1000000)
    parser.add_argument("--max-mismatch-abort-missing-total", type=int, default=1000000)
    parser.add_argument("--max-mismatch-alert-missing-total", type=int, default=1000000)
    parser.add_argument("--max-duplicate-unsafe-total", type=int, default=1000000)
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
    summary = summarize_execution_safety_contract_guard(
        rows,
        max_outcome_drift=max(0.0, float(args.max_outcome_drift)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_preflight_check_coverage_ratio=max(0.0, float(args.min_preflight_check_coverage_ratio)),
        min_idempotency_coverage_ratio=max(0.0, float(args.min_idempotency_coverage_ratio)),
        max_preflight_block_violation_total=max(0, int(args.max_preflight_block_violation_total)),
        max_mismatch_abort_missing_total=max(0, int(args.max_mismatch_abort_missing_total)),
        max_mismatch_alert_missing_total=max(0, int(args.max_mismatch_alert_missing_total)),
        max_duplicate_unsafe_total=max(0, int(args.max_duplicate_unsafe_total)),
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
                "max_outcome_drift": float(args.max_outcome_drift),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_preflight_check_coverage_ratio": float(args.min_preflight_check_coverage_ratio),
                "min_idempotency_coverage_ratio": float(args.min_idempotency_coverage_ratio),
                "max_preflight_block_violation_total": int(args.max_preflight_block_violation_total),
                "max_mismatch_abort_missing_total": int(args.max_mismatch_abort_missing_total),
                "max_mismatch_alert_missing_total": int(args.max_mismatch_alert_missing_total),
                "max_duplicate_unsafe_total": int(args.max_duplicate_unsafe_total),
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
    print(f"preflight_check_coverage_ratio={_safe_float(summary.get('preflight_check_coverage_ratio'), 0.0):.4f}")
    print(f"idempotency_coverage_ratio={_safe_float(summary.get('idempotency_coverage_ratio'), 0.0):.4f}")
    print(f"preflight_block_violation_total={_safe_int(summary.get('preflight_block_violation_total'), 0)}")
    print(f"mismatch_abort_missing_total={_safe_int(summary.get('mismatch_abort_missing_total'), 0)}")
    print(f"mismatch_alert_missing_total={_safe_int(summary.get('mismatch_alert_missing_total'), 0)}")
    print(f"duplicate_unsafe_total={_safe_int(summary.get('duplicate_unsafe_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
