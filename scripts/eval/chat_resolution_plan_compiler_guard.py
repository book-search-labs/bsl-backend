#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


REASON_REQUIRED_FIELDS: dict[str, set[str]] = {
    "REFUND": {"order_id", "received", "request_date"},
    "RETURN": {"order_id", "received"},
    "SHIPPING": {"order_id", "shipping_option"},
    "ORDER": {"order_id"},
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


def _reason_group(row: Mapping[str, Any]) -> str:
    reason = str(row.get("reason_code") or "").upper()
    for key in REASON_REQUIRED_FIELDS:
        if key in reason:
            return key
    return ""


def _required_checks(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("required_checks")
    if isinstance(raw, list):
        values = {str(item).strip().lower() for item in raw if str(item).strip()}
        if values:
            return values
    group = _reason_group(row)
    return {item.lower() for item in REASON_REQUIRED_FIELDS.get(group, set())}


def _provided_checks(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("provided_checks")
    if isinstance(raw, list):
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    slots = row.get("slots")
    if isinstance(slots, Mapping):
        return {str(key).strip().lower() for key in slots.keys() if str(key).strip()}
    text = str(row.get("provided_check_names") or "").strip()
    if not text:
        return set()
    return {item.strip().lower() for item in text.split(",") if item.strip()}


def _plan_created(row: Mapping[str, Any]) -> bool:
    explicit = row.get("plan_created")
    if explicit is not None:
        return _safe_bool(explicit)
    return bool(row.get("plan_steps"))


def _plan_deterministic(row: Mapping[str, Any]) -> bool:
    explicit = row.get("plan_deterministic")
    if explicit is not None:
        return _safe_bool(explicit)
    return _safe_bool(row.get("deterministic"))


def _plan_executable(row: Mapping[str, Any]) -> bool:
    explicit = row.get("plan_executable")
    if explicit is not None:
        return _safe_bool(explicit)
    status = str(row.get("plan_status") or "").strip().upper()
    return status in {"READY", "EXECUTABLE"}


def _insufficient_evidence_count(row: Mapping[str, Any]) -> int:
    value = row.get("insufficient_evidence_items")
    if isinstance(value, list):
        return len(value)
    return _safe_int(row.get("insufficient_evidence_count"), 0)


def summarize_resolution_plan_compiler_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    plan_created_total = 0
    deterministic_plan_total = 0
    missing_required_check_total = 0
    missing_required_block_violation_total = 0
    insufficient_evidence_total = 0
    insufficient_evidence_reroute_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        event_total += 1

        required = _required_checks(row)
        provided = _provided_checks(row)
        missing_required = {item for item in required if item not in provided}
        if missing_required:
            missing_required_check_total += 1

        plan_created = _plan_created(row)
        if plan_created:
            plan_created_total += 1
            if _plan_deterministic(row):
                deterministic_plan_total += 1
            if missing_required and _plan_executable(row):
                missing_required_block_violation_total += 1

        insuff_count = _insufficient_evidence_count(row)
        if insuff_count > 0:
            insufficient_evidence_total += 1
            followup = _safe_bool(row.get("followup_question_asked")) or _safe_bool(row.get("need_info_prompted"))
            if not followup:
                insufficient_evidence_reroute_missing_total += 1

    plan_creation_rate = 0.0 if event_total == 0 else float(plan_created_total) / float(event_total)
    deterministic_plan_ratio = 1.0 if plan_created_total == 0 else float(deterministic_plan_total) / float(plan_created_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "plan_created_total": plan_created_total,
        "plan_creation_rate": plan_creation_rate,
        "deterministic_plan_total": deterministic_plan_total,
        "deterministic_plan_ratio": deterministic_plan_ratio,
        "missing_required_check_total": missing_required_check_total,
        "missing_required_block_violation_total": missing_required_block_violation_total,
        "insufficient_evidence_total": insufficient_evidence_total,
        "insufficient_evidence_reroute_missing_total": insufficient_evidence_reroute_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_plan_creation_rate: float,
    min_deterministic_plan_ratio: float,
    max_missing_required_block_violation_total: int,
    max_insufficient_evidence_reroute_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    plan_creation_rate = _safe_float(summary.get("plan_creation_rate"), 0.0)
    deterministic_plan_ratio = _safe_float(summary.get("deterministic_plan_ratio"), 0.0)
    missing_required_block_violation_total = _safe_int(summary.get("missing_required_block_violation_total"), 0)
    insufficient_evidence_reroute_missing_total = _safe_int(summary.get("insufficient_evidence_reroute_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"resolution plan window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"resolution plan event total too small: {event_total} < {int(min_event_total)}")
    if window_size == 0:
        return failures

    if plan_creation_rate < max(0.0, float(min_plan_creation_rate)):
        failures.append(f"resolution plan creation rate below minimum: {plan_creation_rate:.4f} < {float(min_plan_creation_rate):.4f}")
    if deterministic_plan_ratio < max(0.0, float(min_deterministic_plan_ratio)):
        failures.append(
            f"resolution plan deterministic ratio below minimum: {deterministic_plan_ratio:.4f} < {float(min_deterministic_plan_ratio):.4f}"
        )
    if missing_required_block_violation_total > max(0, int(max_missing_required_block_violation_total)):
        failures.append(
            "resolution plan missing-required-block violation exceeded: "
            f"{missing_required_block_violation_total} > {int(max_missing_required_block_violation_total)}"
        )
    if insufficient_evidence_reroute_missing_total > max(0, int(max_insufficient_evidence_reroute_missing_total)):
        failures.append(
            "resolution plan insufficient-evidence reroute missing exceeded: "
            f"{insufficient_evidence_reroute_missing_total} > {int(max_insufficient_evidence_reroute_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"resolution plan stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Resolution Plan Compiler Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- plan_creation_rate: {_safe_float(summary.get('plan_creation_rate'), 0.0):.4f}")
    lines.append(f"- deterministic_plan_ratio: {_safe_float(summary.get('deterministic_plan_ratio'), 0.0):.4f}")
    lines.append(
        f"- missing_required_block_violation_total: {_safe_int(summary.get('missing_required_block_violation_total'), 0)}"
    )
    lines.append(
        f"- insufficient_evidence_reroute_missing_total: {_safe_int(summary.get('insufficient_evidence_reroute_missing_total'), 0)}"
    )
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
    parser = argparse.ArgumentParser(description="Evaluate resolution plan compiler quality.")
    parser.add_argument("--events-jsonl", default="var/resolution_plan/plan_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_resolution_plan_compiler_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-plan-creation-rate", type=float, default=0.0)
    parser.add_argument("--min-deterministic-plan-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-required-block-violation-total", type=int, default=1000000)
    parser.add_argument("--max-insufficient-evidence-reroute-missing-total", type=int, default=1000000)
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
    summary = summarize_resolution_plan_compiler_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_plan_creation_rate=max(0.0, float(args.min_plan_creation_rate)),
        min_deterministic_plan_ratio=max(0.0, float(args.min_deterministic_plan_ratio)),
        max_missing_required_block_violation_total=max(0, int(args.max_missing_required_block_violation_total)),
        max_insufficient_evidence_reroute_missing_total=max(0, int(args.max_insufficient_evidence_reroute_missing_total)),
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
                "min_event_total": int(args.min_event_total),
                "min_plan_creation_rate": float(args.min_plan_creation_rate),
                "min_deterministic_plan_ratio": float(args.min_deterministic_plan_ratio),
                "max_missing_required_block_violation_total": int(args.max_missing_required_block_violation_total),
                "max_insufficient_evidence_reroute_missing_total": int(args.max_insufficient_evidence_reroute_missing_total),
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
    print(f"event_total={_safe_int(summary.get('event_total'), 0)}")
    print(f"plan_creation_rate={_safe_float(summary.get('plan_creation_rate'), 0.0):.4f}")
    print(f"deterministic_plan_ratio={_safe_float(summary.get('deterministic_plan_ratio'), 0.0):.4f}")
    print(
        "missing_required_block_violation_total="
        f"{_safe_int(summary.get('missing_required_block_violation_total'), 0)}"
    )
    print(
        "insufficient_evidence_reroute_missing_total="
        f"{_safe_int(summary.get('insufficient_evidence_reroute_missing_total'), 0)}"
    )

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
