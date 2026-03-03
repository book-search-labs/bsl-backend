#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

WRITE_ACTION_TYPES = {"WRITE", "WRITE_SENSITIVE", "MUTATION"}
TERMINAL_PHASES = {"COMMIT", "ABORT", "COMPENSATION_SUCCESS", "COMPENSATION_FAILED", "SAFE_STOP"}
ALLOWED_NEXT_PHASES = {
    "PREPARE": {"VALIDATE", "ABORT"},
    "VALIDATE": {"COMMIT", "ABORT", "COMPENSATION_REQUIRED"},
    "COMPENSATION_REQUIRED": {"COMPENSATION_START", "ABORT"},
    "COMPENSATION_START": {"COMPENSATION_SUCCESS", "COMPENSATION_FAILED"},
    "COMPENSATION_FAILED": {"SAFE_STOP", "ALERT", "ABORT"},
    "SAFE_STOP": {"ALERT", "ABORT"},
    "ALERT": {"ABORT"},
    "COMPENSATION_SUCCESS": set(),
    "COMMIT": set(),
    "ABORT": set(),
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


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _normalize_phase(row: Mapping[str, Any]) -> str:
    aliases = {
        "START": "PREPARE",
        "PREPARED": "PREPARE",
        "CHECK": "VALIDATE",
        "VALIDATED": "VALIDATE",
        "EXECUTE": "COMMIT",
        "COMMITTED": "COMMIT",
        "COMMIT_DONE": "COMMIT",
        "ABORTED": "ABORT",
        "CANCELLED": "ABORT",
        "COMPENSATE": "COMPENSATION_START",
        "COMPENSATE_START": "COMPENSATION_START",
        "COMPENSATE_STARTED": "COMPENSATION_START",
        "COMPENSATE_SUCCESS": "COMPENSATION_SUCCESS",
        "COMPENSATE_FAILED": "COMPENSATION_FAILED",
        "ROLLBACK_REQUIRED": "COMPENSATION_REQUIRED",
        "ROLLBACK_STARTED": "COMPENSATION_START",
        "ROLLBACK_COMPLETED": "COMPENSATION_SUCCESS",
        "ROLLBACK_FAILED": "COMPENSATION_FAILED",
        "OPERATOR_ALERTED": "ALERT",
        "ALERT_SENT": "ALERT",
        "INCIDENT_OPENED": "ALERT",
        "SAFE_STOPPED": "SAFE_STOP",
        "SAFETY_HALT": "SAFE_STOP",
        "HALTED_SAFE": "SAFE_STOP",
    }
    for key in ("phase", "event_type", "status", "step", "result"):
        token = _normalize_token(row.get(key))
        if not token:
            continue
        return aliases.get(token, token)
    return "UNKNOWN"


def _tx_key(row: Mapping[str, Any]) -> str:
    tx_id = str(row.get("tx_id") or row.get("transaction_id") or "").strip()
    if tx_id:
        return tx_id
    workflow = str(row.get("workflow_id") or row.get("conversation_id") or "").strip()
    request = str(row.get("request_id") or "").strip()
    return "|".join([workflow, request]).strip("|") or "__missing__"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def _requires_actor(row: Mapping[str, Any], phase: str) -> bool:
    action_type = _normalize_token(row.get("action_type") or row.get("risk_level"))
    if action_type in WRITE_ACTION_TYPES:
        return True
    return phase.startswith("COMPENSATION") or phase in {"COMMIT", "ABORT"}


def summarize_tool_tx_audit_replayability(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    flows: dict[str, dict[str, Any]] = {}
    missing_trace_id_total = 0
    missing_request_id_total = 0
    missing_reason_code_total = 0
    missing_phase_total = 0
    missing_actor_total = 0
    unknown_phase_total = 0

    for row in rows:
        ts = _event_ts(row) or now_dt
        observed_ts = _event_ts(row)
        if observed_ts is not None and (latest_ts is None or observed_ts > latest_ts):
            latest_ts = observed_ts

        trace_id = str(row.get("trace_id") or "").strip()
        request_id = str(row.get("request_id") or "").strip()
        reason_code = str(row.get("reason_code") or "").strip()
        phase = _normalize_phase(row)
        actor_id = str(row.get("actor_id") or row.get("actor") or row.get("user_id") or "").strip()

        flow = flows.setdefault(_tx_key(row), {"events": [], "has_missing_required": False})
        flow["events"].append((ts, phase))

        if not trace_id:
            missing_trace_id_total += 1
            flow["has_missing_required"] = True
        if not request_id:
            missing_request_id_total += 1
            flow["has_missing_required"] = True
        if not reason_code:
            missing_reason_code_total += 1
            flow["has_missing_required"] = True
        if phase == "UNKNOWN":
            missing_phase_total += 1
            unknown_phase_total += 1
            flow["has_missing_required"] = True
        if _requires_actor(row, phase) and not actor_id:
            missing_actor_total += 1
            flow["has_missing_required"] = True

    tx_total = 0
    replayable_tx_total = 0
    non_replayable_tx_total = 0
    transition_gap_total = 0
    p95_replay_span_samples: list[float] = []

    for flow in flows.values():
        events = sorted(flow.get("events") or [], key=lambda item: item[0])
        tx_total += 1
        has_missing_required = bool(flow.get("has_missing_required"))

        has_terminal = any(phase in TERMINAL_PHASES for _, phase in events)
        tx_transition_gaps = 0
        for idx in range(1, len(events)):
            prev_phase = events[idx - 1][1]
            curr_phase = events[idx][1]
            allowed = ALLOWED_NEXT_PHASES.get(prev_phase)
            if allowed is None:
                continue
            if not allowed and curr_phase != prev_phase:
                tx_transition_gaps += 1
                continue
            if allowed and curr_phase not in allowed and curr_phase != prev_phase:
                tx_transition_gaps += 1
        transition_gap_total += tx_transition_gaps

        replayable = bool(events) and has_terminal and not has_missing_required and tx_transition_gaps == 0
        if replayable:
            replayable_tx_total += 1
            start_ts = events[0][0]
            end_ts = events[-1][0]
            p95_replay_span_samples.append(max(0.0, (end_ts - start_ts).total_seconds() * 1000.0))
        else:
            non_replayable_tx_total += 1

    replayable_ratio = 1.0 if tx_total == 0 else float(replayable_tx_total) / float(tx_total)
    p95_replay_span_ms = _p95(p95_replay_span_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "tx_total": tx_total,
        "replayable_tx_total": replayable_tx_total,
        "non_replayable_tx_total": non_replayable_tx_total,
        "replayable_ratio": replayable_ratio,
        "missing_trace_id_total": missing_trace_id_total,
        "missing_request_id_total": missing_request_id_total,
        "missing_reason_code_total": missing_reason_code_total,
        "missing_phase_total": missing_phase_total,
        "missing_actor_total": missing_actor_total,
        "unknown_phase_total": unknown_phase_total,
        "transition_gap_total": transition_gap_total,
        "p95_replay_span_ms": p95_replay_span_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_tx_total: int,
    min_replayable_ratio: float,
    max_missing_trace_id_total: int,
    max_missing_request_id_total: int,
    max_missing_reason_code_total: int,
    max_missing_phase_total: int,
    max_missing_actor_total: int,
    max_transition_gap_total: int,
    max_non_replayable_tx_total: int,
    max_p95_replay_span_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    tx_total = _safe_int(summary.get("tx_total"), 0)
    replayable_ratio = _safe_float(summary.get("replayable_ratio"), 0.0)
    missing_trace_id_total = _safe_int(summary.get("missing_trace_id_total"), 0)
    missing_request_id_total = _safe_int(summary.get("missing_request_id_total"), 0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    missing_phase_total = _safe_int(summary.get("missing_phase_total"), 0)
    missing_actor_total = _safe_int(summary.get("missing_actor_total"), 0)
    transition_gap_total = _safe_int(summary.get("transition_gap_total"), 0)
    non_replayable_tx_total = _safe_int(summary.get("non_replayable_tx_total"), 0)
    p95_replay_span_ms = _safe_float(summary.get("p95_replay_span_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat tool tx audit window too small: {window_size} < {int(min_window)}")
    if tx_total < max(0, int(min_tx_total)):
        failures.append(f"chat tool tx total too small: {tx_total} < {int(min_tx_total)}")
    if window_size == 0:
        return failures

    if replayable_ratio < max(0.0, float(min_replayable_ratio)):
        failures.append(
            f"chat tool tx replayable ratio below minimum: {replayable_ratio:.4f} < {float(min_replayable_ratio):.4f}"
        )
    if missing_trace_id_total > max(0, int(max_missing_trace_id_total)):
        failures.append(
            f"chat tool tx missing trace_id total exceeded: {missing_trace_id_total} > {int(max_missing_trace_id_total)}"
        )
    if missing_request_id_total > max(0, int(max_missing_request_id_total)):
        failures.append(
            "chat tool tx missing request_id total exceeded: "
            f"{missing_request_id_total} > {int(max_missing_request_id_total)}"
        )
    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(
            "chat tool tx missing reason_code total exceeded: "
            f"{missing_reason_code_total} > {int(max_missing_reason_code_total)}"
        )
    if missing_phase_total > max(0, int(max_missing_phase_total)):
        failures.append(f"chat tool tx missing phase total exceeded: {missing_phase_total} > {int(max_missing_phase_total)}")
    if missing_actor_total > max(0, int(max_missing_actor_total)):
        failures.append(f"chat tool tx missing actor total exceeded: {missing_actor_total} > {int(max_missing_actor_total)}")
    if transition_gap_total > max(0, int(max_transition_gap_total)):
        failures.append(f"chat tool tx transition gap total exceeded: {transition_gap_total} > {int(max_transition_gap_total)}")
    if non_replayable_tx_total > max(0, int(max_non_replayable_tx_total)):
        failures.append(
            f"chat tool tx non-replayable total exceeded: {non_replayable_tx_total} > {int(max_non_replayable_tx_total)}"
        )
    if p95_replay_span_ms > max(0.0, float(max_p95_replay_span_ms)):
        failures.append(f"chat tool tx replay span p95 exceeded: {p95_replay_span_ms:.2f}ms > {float(max_p95_replay_span_ms):.2f}ms")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat tool tx audit stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Tool Transaction Audit Replayability")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- tx_total: {_safe_int(summary.get('tx_total'), 0)}")
    lines.append(f"- replayable_tx_total: {_safe_int(summary.get('replayable_tx_total'), 0)}")
    lines.append(f"- non_replayable_tx_total: {_safe_int(summary.get('non_replayable_tx_total'), 0)}")
    lines.append(f"- missing_reason_code_total: {_safe_int(summary.get('missing_reason_code_total'), 0)}")
    lines.append(f"- transition_gap_total: {_safe_int(summary.get('transition_gap_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat tool transaction audit replayability signals.")
    parser.add_argument("--events-jsonl", default="var/chat_tool_tx/tx_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_tx_audit_replayability")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-tx-total", type=int, default=0)
    parser.add_argument("--min-replayable-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-trace-id-total", type=int, default=0)
    parser.add_argument("--max-missing-request-id-total", type=int, default=0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--max-missing-phase-total", type=int, default=0)
    parser.add_argument("--max-missing-actor-total", type=int, default=0)
    parser.add_argument("--max-transition-gap-total", type=int, default=0)
    parser.add_argument("--max-non-replayable-tx-total", type=int, default=0)
    parser.add_argument("--max-p95-replay-span-ms", type=float, default=1000000.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_tool_tx_audit_replayability(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_tx_total=max(0, int(args.min_tx_total)),
        min_replayable_ratio=max(0.0, float(args.min_replayable_ratio)),
        max_missing_trace_id_total=max(0, int(args.max_missing_trace_id_total)),
        max_missing_request_id_total=max(0, int(args.max_missing_request_id_total)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        max_missing_phase_total=max(0, int(args.max_missing_phase_total)),
        max_missing_actor_total=max(0, int(args.max_missing_actor_total)),
        max_transition_gap_total=max(0, int(args.max_transition_gap_total)),
        max_non_replayable_tx_total=max(0, int(args.max_non_replayable_tx_total)),
        max_p95_replay_span_ms=max(0.0, float(args.max_p95_replay_span_ms)),
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
                "min_tx_total": int(args.min_tx_total),
                "min_replayable_ratio": float(args.min_replayable_ratio),
                "max_missing_trace_id_total": int(args.max_missing_trace_id_total),
                "max_missing_request_id_total": int(args.max_missing_request_id_total),
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "max_missing_phase_total": int(args.max_missing_phase_total),
                "max_missing_actor_total": int(args.max_missing_actor_total),
                "max_transition_gap_total": int(args.max_transition_gap_total),
                "max_non_replayable_tx_total": int(args.max_non_replayable_tx_total),
                "max_p95_replay_span_ms": float(args.max_p95_replay_span_ms),
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
    print(f"tx_total={_safe_int(summary.get('tx_total'), 0)}")
    print(f"replayable_tx_total={_safe_int(summary.get('replayable_tx_total'), 0)}")
    print(f"missing_reason_code_total={_safe_int(summary.get('missing_reason_code_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
