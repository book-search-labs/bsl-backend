#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

PHASE_ORDER: dict[str, int] = {
    "INTENT_CONFIRM": 0,
    "INPUT_COLLECTION": 1,
    "VALIDATION": 2,
    "EXECUTE": 3,
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
    for key in ("timestamp", "event_time", "ts", "created_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_phase(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "INTENT": "INTENT_CONFIRM",
        "CONFIRM_INTENT": "INTENT_CONFIRM",
        "COLLECT_INPUT": "INPUT_COLLECTION",
        "COLLECT": "INPUT_COLLECTION",
        "VERIFY": "VALIDATION",
        "CHECK": "VALIDATION",
        "ACTION": "EXECUTE",
        "TOOL_EXECUTE": "EXECUTE",
    }
    if text in PHASE_ORDER:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _normalize_result(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"ok", "success", "succeeded", "completed"}:
        return "SUCCESS"
    if text in {"error", "failed", "timeout"}:
        return "FAILED"
    return "UNKNOWN"


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
        if isinstance(payload, dict):
            rows.append(payload)

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


def summarize_plan_execute(events: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    workflows: dict[str, list[dict[str, Any]]] = {}
    step_error_counts: dict[str, int] = {}

    for row in events:
        workflow_id = str(row.get("workflow_id") or row.get("id") or "").strip()
        if not workflow_id:
            continue
        phase = _normalize_phase(row.get("phase") or row.get("step"))
        result = _normalize_result(row.get("result") or row.get("status"))
        ts = _event_ts(row)

        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        workflows.setdefault(workflow_id, []).append(
            {
                "phase": phase,
                "result": result,
                "reentry_attempt": _safe_bool(row.get("reentry_attempt"), False) or _safe_bool(row.get("retry"), False),
                "reentry_success": _safe_bool(row.get("reentry_success"), False),
                "timestamp": ts,
            }
        )

        if result == "FAILED":
            step_error_counts[phase] = step_error_counts.get(phase, 0) + 1

    workflow_total = len(workflows)
    sequence_valid_total = 0
    execute_workflow_total = 0
    validation_before_execute_total = 0
    step_error_total = sum(step_error_counts.values())
    reentry_attempt_total = 0
    reentry_success_total = 0

    for items in workflows.values():
        ordered = sorted(
            items,
            key=lambda item: (
                item["timestamp"] if isinstance(item["timestamp"], datetime) else datetime.min.replace(tzinfo=timezone.utc)
            ),
        )
        phase_sequence = [str(item["phase"]) for item in ordered]
        phase_first_seen: list[str] = []
        for phase in phase_sequence:
            if not phase_first_seen or phase_first_seen[-1] != phase:
                phase_first_seen.append(phase)

        is_sequence_valid = True
        last_order = -1
        for phase in phase_first_seen:
            phase_order = PHASE_ORDER.get(phase)
            if phase_order is None:
                is_sequence_valid = False
                break
            if phase_order < last_order:
                is_sequence_valid = False
                break
            last_order = phase_order
        if is_sequence_valid:
            sequence_valid_total += 1

        first_validation_index = next((idx for idx, phase in enumerate(phase_sequence) if phase == "VALIDATION"), None)
        first_execute_index = next((idx for idx, phase in enumerate(phase_sequence) if phase == "EXECUTE"), None)
        if first_execute_index is not None:
            execute_workflow_total += 1
            if first_validation_index is not None and first_validation_index < first_execute_index:
                validation_before_execute_total += 1

        had_failure = any(item["result"] == "FAILED" for item in ordered)
        had_reentry_attempt = any(bool(item["reentry_attempt"]) for item in ordered)
        had_reentry_success = any(bool(item["reentry_success"]) for item in ordered)
        if had_failure or had_reentry_attempt:
            reentry_attempt_total += 1
            if had_reentry_success:
                reentry_success_total += 1

    sequence_valid_ratio = 1.0 if workflow_total == 0 else float(sequence_valid_total) / float(workflow_total)
    validation_before_execute_ratio = (
        1.0 if execute_workflow_total == 0 else float(validation_before_execute_total) / float(execute_workflow_total)
    )
    reentry_success_ratio = 1.0 if reentry_attempt_total == 0 else float(reentry_success_total) / float(reentry_attempt_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(events),
        "workflow_total": workflow_total,
        "sequence_valid_total": sequence_valid_total,
        "sequence_valid_ratio": sequence_valid_ratio,
        "execute_workflow_total": execute_workflow_total,
        "validation_before_execute_total": validation_before_execute_total,
        "validation_before_execute_ratio": validation_before_execute_ratio,
        "step_error_total": step_error_total,
        "reentry_attempt_total": reentry_attempt_total,
        "reentry_success_total": reentry_success_total,
        "reentry_success_ratio": reentry_success_ratio,
        "step_errors": [
            {"phase": phase, "count": count}
            for phase, count in sorted(step_error_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_sequence_valid_ratio: float,
    min_validation_before_execute_ratio: float,
    max_step_error_total: int,
    min_reentry_success_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    sequence_valid_ratio = _safe_float(summary.get("sequence_valid_ratio"), 0.0)
    validation_before_execute_ratio = _safe_float(summary.get("validation_before_execute_ratio"), 0.0)
    step_error_total = _safe_int(summary.get("step_error_total"), 0)
    reentry_success_ratio = _safe_float(summary.get("reentry_success_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"workflow plan-execute window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if sequence_valid_ratio < max(0.0, float(min_sequence_valid_ratio)):
        failures.append(
            f"plan-execute sequence valid ratio below threshold: {sequence_valid_ratio:.4f} < {float(min_sequence_valid_ratio):.4f}"
        )
    if validation_before_execute_ratio < max(0.0, float(min_validation_before_execute_ratio)):
        failures.append(
            "validation-before-execute ratio below threshold: "
            f"{validation_before_execute_ratio:.4f} < {float(min_validation_before_execute_ratio):.4f}"
        )
    if step_error_total > max(0, int(max_step_error_total)):
        failures.append(f"workflow step error total exceeded: {step_error_total} > {int(max_step_error_total)}")
    if reentry_success_ratio < max(0.0, float(min_reentry_success_ratio)):
        failures.append(
            f"workflow reentry success ratio below threshold: {reentry_success_ratio:.4f} < {float(min_reentry_success_ratio):.4f}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"workflow plan-execute events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Workflow Plan Execute")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- workflow_total: {_safe_int(summary.get('workflow_total'), 0)}")
    lines.append(f"- sequence_valid_ratio: {_safe_float(summary.get('sequence_valid_ratio'), 0.0):.4f}")
    lines.append(
        f"- validation_before_execute_ratio: {_safe_float(summary.get('validation_before_execute_ratio'), 0.0):.4f}"
    )
    lines.append(f"- step_error_total: {_safe_int(summary.get('step_error_total'), 0)}")
    lines.append(f"- reentry_success_ratio: {_safe_float(summary.get('reentry_success_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate workflow plan-and-execute step orchestration quality.")
    parser.add_argument("--events-jsonl", default="var/chat_workflow/workflow_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_workflow_plan_execute")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--min-sequence-valid-ratio", type=float, default=0.95)
    parser.add_argument("--min-validation-before-execute-ratio", type=float, default=0.99)
    parser.add_argument("--max-step-error-total", type=int, default=0)
    parser.add_argument("--min-reentry-success-ratio", type=float, default=0.80)
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
    summary = summarize_plan_execute(events)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_sequence_valid_ratio=max(0.0, float(args.min_sequence_valid_ratio)),
        min_validation_before_execute_ratio=max(0.0, float(args.min_validation_before_execute_ratio)),
        max_step_error_total=max(0, int(args.max_step_error_total)),
        min_reentry_success_ratio=max(0.0, float(args.min_reentry_success_ratio)),
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
                "min_sequence_valid_ratio": float(args.min_sequence_valid_ratio),
                "min_validation_before_execute_ratio": float(args.min_validation_before_execute_ratio),
                "max_step_error_total": int(args.max_step_error_total),
                "min_reentry_success_ratio": float(args.min_reentry_success_ratio),
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
    print(f"workflow_total={_safe_int(summary.get('workflow_total'), 0)}")
    print(f"sequence_valid_ratio={_safe_float(summary.get('sequence_valid_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
