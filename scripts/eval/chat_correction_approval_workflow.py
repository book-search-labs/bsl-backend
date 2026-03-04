#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_EVENT_TYPES = {
    "CREATED",
    "SUBMITTED",
    "REVIEW_REQUESTED",
    "APPROVED",
    "ACTIVATED",
    "DEACTIVATED",
    "ROLLED_BACK",
    "REJECTED",
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


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return {str(k): v for k, v in payload.items()}


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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "approved_at", "activated_at"):
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


def _event_type(row: Mapping[str, Any]) -> str:
    text = str(row.get("event_type") or row.get("action") or row.get("status_change") or "").strip().upper()
    aliases = {
        "CREATE": "CREATED",
        "SUBMIT": "SUBMITTED",
        "APPROVE": "APPROVED",
        "ACTIVATE": "ACTIVATED",
        "DEACTIVATE": "DEACTIVATED",
        "ROLLBACK": "ROLLED_BACK",
        "REJECT": "REJECTED",
    }
    return aliases.get(text, text or "UNKNOWN")


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_correction_approval_workflow(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    correction_ids: set[str] = set()
    submitted_total = 0
    approved_total = 0
    activated_total = 0
    rollback_total = 0
    invalid_event_type_total = 0
    invalid_transition_total = 0
    missing_actor_total = 0
    missing_reviewer_total = 0

    events_by_correction: dict[str, list[tuple[datetime, str, Mapping[str, Any]]]] = {}

    for row in rows:
        event_total += 1
        ts = _event_ts(row)
        if ts is None:
            ts = now_dt
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts

        correction_id = str(row.get("correction_id") or "").strip()
        if correction_id:
            correction_ids.add(correction_id)
        else:
            correction_id = "__missing__"

        event_type = _event_type(row)
        if event_type not in VALID_EVENT_TYPES:
            invalid_event_type_total += 1

        if event_type == "SUBMITTED":
            submitted_total += 1
        elif event_type == "APPROVED":
            approved_total += 1
        elif event_type == "ACTIVATED":
            activated_total += 1
        elif event_type == "ROLLED_BACK":
            rollback_total += 1

        if not str(row.get("actor_id") or row.get("actor") or "").strip():
            missing_actor_total += 1
        if event_type == "APPROVED":
            reviewer = str(row.get("reviewer_id") or row.get("reviewer") or "").strip()
            if not reviewer:
                missing_reviewer_total += 1

        events_by_correction.setdefault(correction_id, []).append((ts, event_type, row))

    approval_latencies: list[float] = []
    activation_latencies: list[float] = []

    for sequence in events_by_correction.values():
        ordered = sorted(sequence, key=lambda x: x[0])
        submitted_at: datetime | None = None
        approved_at: datetime | None = None
        activated_at: datetime | None = None

        for ts, event_type, _row in ordered:
            if event_type == "SUBMITTED":
                submitted_at = ts
            elif event_type == "APPROVED":
                if submitted_at is None:
                    invalid_transition_total += 1
                else:
                    approval_latencies.append(max(0.0, (ts - submitted_at).total_seconds() / 60.0))
                approved_at = ts
            elif event_type == "ACTIVATED":
                if approved_at is None:
                    invalid_transition_total += 1
                else:
                    activation_latencies.append(max(0.0, (ts - approved_at).total_seconds() / 60.0))
                activated_at = ts
            elif event_type == "ROLLED_BACK":
                if activated_at is None:
                    invalid_transition_total += 1

    p95_approval_latency_minutes = _p95(approval_latencies)
    p95_activation_latency_minutes = _p95(activation_latencies)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "correction_total": len(correction_ids),
        "submitted_total": submitted_total,
        "approved_total": approved_total,
        "activated_total": activated_total,
        "rollback_total": rollback_total,
        "invalid_event_type_total": invalid_event_type_total,
        "invalid_transition_total": invalid_transition_total,
        "missing_actor_total": missing_actor_total,
        "missing_reviewer_total": missing_reviewer_total,
        "p95_approval_latency_minutes": p95_approval_latency_minutes,
        "p95_activation_latency_minutes": p95_activation_latency_minutes,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_correction_total: int,
    min_submitted_total: int,
    max_invalid_event_type_total: int,
    max_invalid_transition_total: int,
    max_missing_actor_total: int,
    max_missing_reviewer_total: int,
    max_p95_approval_latency_minutes: float,
    max_p95_activation_latency_minutes: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    correction_total = _safe_int(summary.get("correction_total"), 0)
    submitted_total = _safe_int(summary.get("submitted_total"), 0)
    invalid_event_type_total = _safe_int(summary.get("invalid_event_type_total"), 0)
    invalid_transition_total = _safe_int(summary.get("invalid_transition_total"), 0)
    missing_actor_total = _safe_int(summary.get("missing_actor_total"), 0)
    missing_reviewer_total = _safe_int(summary.get("missing_reviewer_total"), 0)
    p95_approval_latency_minutes = _safe_float(summary.get("p95_approval_latency_minutes"), 0.0)
    p95_activation_latency_minutes = _safe_float(summary.get("p95_activation_latency_minutes"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat correction approval window too small: {window_size} < {int(min_window)}")
    if correction_total < max(0, int(min_correction_total)):
        failures.append(f"chat correction approval correction total too small: {correction_total} < {int(min_correction_total)}")
    if submitted_total < max(0, int(min_submitted_total)):
        failures.append(f"chat correction approval submitted total too small: {submitted_total} < {int(min_submitted_total)}")
    if window_size == 0:
        return failures

    if invalid_event_type_total > max(0, int(max_invalid_event_type_total)):
        failures.append(
            f"chat correction approval invalid event type total exceeded: {invalid_event_type_total} > {int(max_invalid_event_type_total)}"
        )
    if invalid_transition_total > max(0, int(max_invalid_transition_total)):
        failures.append(
            f"chat correction approval invalid transition total exceeded: {invalid_transition_total} > {int(max_invalid_transition_total)}"
        )
    if missing_actor_total > max(0, int(max_missing_actor_total)):
        failures.append(f"chat correction approval missing actor total exceeded: {missing_actor_total} > {int(max_missing_actor_total)}")
    if missing_reviewer_total > max(0, int(max_missing_reviewer_total)):
        failures.append(
            f"chat correction approval missing reviewer total exceeded: {missing_reviewer_total} > {int(max_missing_reviewer_total)}"
        )
    if p95_approval_latency_minutes > max(0.0, float(max_p95_approval_latency_minutes)):
        failures.append(
            "chat correction approval p95 approval latency exceeded: "
            f"{p95_approval_latency_minutes:.2f}m > {float(max_p95_approval_latency_minutes):.2f}m"
        )
    if p95_activation_latency_minutes > max(0.0, float(max_p95_activation_latency_minutes)):
        failures.append(
            "chat correction approval p95 activation latency exceeded: "
            f"{p95_activation_latency_minutes:.2f}m > {float(max_p95_activation_latency_minutes):.2f}m"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat correction approval workflow stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_correction_total_drop: int,
    max_submitted_total_drop: int,
    max_approved_total_drop: int,
    max_activated_total_drop: int,
    max_invalid_event_type_total_increase: int,
    max_invalid_transition_total_increase: int,
    max_missing_actor_total_increase: int,
    max_missing_reviewer_total_increase: int,
    max_p95_approval_latency_minutes_increase: float,
    max_p95_activation_latency_minutes_increase: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("correction_total", max_correction_total_drop),
        ("submitted_total", max_submitted_total_drop),
        ("approved_total", max_approved_total_drop),
        ("activated_total", max_activated_total_drop),
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

    baseline_increase_pairs = [
        ("invalid_event_type_total", max_invalid_event_type_total_increase),
        ("invalid_transition_total", max_invalid_transition_total_increase),
        ("missing_actor_total", max_missing_actor_total_increase),
        ("missing_reviewer_total", max_missing_reviewer_total_increase),
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

    base_p95_approval_latency_minutes = _safe_float(base_summary.get("p95_approval_latency_minutes"), 0.0)
    cur_p95_approval_latency_minutes = _safe_float(current_summary.get("p95_approval_latency_minutes"), 0.0)
    p95_approval_latency_minutes_increase = max(0.0, cur_p95_approval_latency_minutes - base_p95_approval_latency_minutes)
    if p95_approval_latency_minutes_increase > max(0.0, float(max_p95_approval_latency_minutes_increase)):
        failures.append(
            "p95_approval_latency_minutes regression: "
            f"baseline={base_p95_approval_latency_minutes:.6f}, current={cur_p95_approval_latency_minutes:.6f}, "
            f"allowed_increase={float(max_p95_approval_latency_minutes_increase):.6f}"
        )

    base_p95_activation_latency_minutes = _safe_float(base_summary.get("p95_activation_latency_minutes"), 0.0)
    cur_p95_activation_latency_minutes = _safe_float(current_summary.get("p95_activation_latency_minutes"), 0.0)
    p95_activation_latency_minutes_increase = max(0.0, cur_p95_activation_latency_minutes - base_p95_activation_latency_minutes)
    if p95_activation_latency_minutes_increase > max(0.0, float(max_p95_activation_latency_minutes_increase)):
        failures.append(
            "p95_activation_latency_minutes regression: "
            f"baseline={base_p95_activation_latency_minutes:.6f}, current={cur_p95_activation_latency_minutes:.6f}, "
            f"allowed_increase={float(max_p95_activation_latency_minutes_increase):.6f}"
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
    lines.append("# Chat Correction Approval Workflow")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- correction_total: {_safe_int(summary.get('correction_total'), 0)}")
    lines.append(f"- submitted_total: {_safe_int(summary.get('submitted_total'), 0)}")
    lines.append(f"- approved_total: {_safe_int(summary.get('approved_total'), 0)}")
    lines.append(f"- invalid_transition_total: {_safe_int(summary.get('invalid_transition_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate correction memory approval workflow.")
    parser.add_argument("--events-jsonl", default="var/chat_correction/correction_approval_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_correction_approval_workflow")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-correction-total", type=int, default=0)
    parser.add_argument("--min-submitted-total", type=int, default=0)
    parser.add_argument("--max-invalid-event-type-total", type=int, default=0)
    parser.add_argument("--max-invalid-transition-total", type=int, default=0)
    parser.add_argument("--max-missing-actor-total", type=int, default=0)
    parser.add_argument("--max-missing-reviewer-total", type=int, default=0)
    parser.add_argument("--max-p95-approval-latency-minutes", type=float, default=1000000.0)
    parser.add_argument("--max-p95-activation-latency-minutes", type=float, default=1000000.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-correction-total-drop", type=int, default=10)
    parser.add_argument("--max-submitted-total-drop", type=int, default=10)
    parser.add_argument("--max-approved-total-drop", type=int, default=10)
    parser.add_argument("--max-activated-total-drop", type=int, default=10)
    parser.add_argument("--max-invalid-event-type-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-transition-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-actor-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-reviewer-total-increase", type=int, default=0)
    parser.add_argument("--max-p95-approval-latency-minutes-increase", type=float, default=30.0)
    parser.add_argument("--max-p95-activation-latency-minutes-increase", type=float, default=30.0)
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
    summary = summarize_correction_approval_workflow(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_correction_total=max(0, int(args.min_correction_total)),
        min_submitted_total=max(0, int(args.min_submitted_total)),
        max_invalid_event_type_total=max(0, int(args.max_invalid_event_type_total)),
        max_invalid_transition_total=max(0, int(args.max_invalid_transition_total)),
        max_missing_actor_total=max(0, int(args.max_missing_actor_total)),
        max_missing_reviewer_total=max(0, int(args.max_missing_reviewer_total)),
        max_p95_approval_latency_minutes=max(0.0, float(args.max_p95_approval_latency_minutes)),
        max_p95_activation_latency_minutes=max(0.0, float(args.max_p95_activation_latency_minutes)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_correction_total_drop=max(0, int(args.max_correction_total_drop)),
            max_submitted_total_drop=max(0, int(args.max_submitted_total_drop)),
            max_approved_total_drop=max(0, int(args.max_approved_total_drop)),
            max_activated_total_drop=max(0, int(args.max_activated_total_drop)),
            max_invalid_event_type_total_increase=max(0, int(args.max_invalid_event_type_total_increase)),
            max_invalid_transition_total_increase=max(0, int(args.max_invalid_transition_total_increase)),
            max_missing_actor_total_increase=max(0, int(args.max_missing_actor_total_increase)),
            max_missing_reviewer_total_increase=max(0, int(args.max_missing_reviewer_total_increase)),
            max_p95_approval_latency_minutes_increase=max(0.0, float(args.max_p95_approval_latency_minutes_increase)),
            max_p95_activation_latency_minutes_increase=max(0.0, float(args.max_p95_activation_latency_minutes_increase)),
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
                "min_correction_total": int(args.min_correction_total),
                "min_submitted_total": int(args.min_submitted_total),
                "max_invalid_event_type_total": int(args.max_invalid_event_type_total),
                "max_invalid_transition_total": int(args.max_invalid_transition_total),
                "max_missing_actor_total": int(args.max_missing_actor_total),
                "max_missing_reviewer_total": int(args.max_missing_reviewer_total),
                "max_p95_approval_latency_minutes": float(args.max_p95_approval_latency_minutes),
                "max_p95_activation_latency_minutes": float(args.max_p95_activation_latency_minutes),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_correction_total_drop": int(args.max_correction_total_drop),
                "max_submitted_total_drop": int(args.max_submitted_total_drop),
                "max_approved_total_drop": int(args.max_approved_total_drop),
                "max_activated_total_drop": int(args.max_activated_total_drop),
                "max_invalid_event_type_total_increase": int(args.max_invalid_event_type_total_increase),
                "max_invalid_transition_total_increase": int(args.max_invalid_transition_total_increase),
                "max_missing_actor_total_increase": int(args.max_missing_actor_total_increase),
                "max_missing_reviewer_total_increase": int(args.max_missing_reviewer_total_increase),
                "max_p95_approval_latency_minutes_increase": float(args.max_p95_approval_latency_minutes_increase),
                "max_p95_activation_latency_minutes_increase": float(args.max_p95_activation_latency_minutes_increase),
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
    print(f"correction_total={_safe_int(summary.get('correction_total'), 0)}")
    print(f"invalid_transition_total={_safe_int(summary.get('invalid_transition_total'), 0)}")
    print(f"missing_reviewer_total={_safe_int(summary.get('missing_reviewer_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
