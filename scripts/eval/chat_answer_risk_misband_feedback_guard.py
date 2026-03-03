#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


BAND_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
RESOLVED_STATUSES = {"RESOLVED", "CLOSED", "DONE", "COMPLETED", "APPLIED"}


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


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return None


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_band(value: Any) -> str:
    token = _normalize_token(value)
    if token in BAND_ORDER:
        return token
    if token in {"0", "RISK_0"}:
        return "R0"
    if token in {"1", "RISK_1"}:
        return "R1"
    if token in {"2", "RISK_2"}:
        return "R2"
    if token in {"3", "RISK_3"}:
        return "R3"
    return ""


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


def _feedback_created_at(row: Mapping[str, Any]) -> datetime | None:
    return _parse_ts(row.get("feedback_created_at")) or _event_ts(row)


def _resolved_at(row: Mapping[str, Any]) -> datetime | None:
    return _parse_ts(row.get("feedback_resolved_at") or row.get("resolved_at"))


def _is_feedback_event(row: Mapping[str, Any]) -> bool:
    if str(row.get("feedback_id") or "").strip():
        return True
    if row.get("adjudicated_band") is not None:
        return True
    token = _normalize_token(row.get("feedback_type") or row.get("event_type"))
    return token.startswith("FEEDBACK") or token in {"MISBAND", "CORRECTION"}


def _is_misband(row: Mapping[str, Any], *, predicted_band: str, adjudicated_band: str) -> bool:
    explicit = _safe_bool(row.get("misband"))
    if explicit is not None:
        return explicit
    token = _normalize_token(row.get("feedback_type") or row.get("label"))
    if token in {"MISBAND", "MISCLASSIFIED", "WRONG_BAND"}:
        return True
    return bool(predicted_band and adjudicated_band and predicted_band != adjudicated_band)


def _is_resolved(row: Mapping[str, Any]) -> bool:
    explicit = _safe_bool(row.get("resolved"))
    if explicit is not None:
        return explicit
    if _resolved_at(row) is not None:
        return True
    status = _normalize_token(row.get("feedback_status") or row.get("status"))
    return status in RESOLVED_STATUSES


def _has_audit_context(row: Mapping[str, Any]) -> bool:
    trace_id = str(row.get("trace_id") or "").strip()
    request_id = str(row.get("request_id") or "").strip()
    return bool(trace_id and request_id)


def _has_reason(row: Mapping[str, Any]) -> bool:
    reason = str(row.get("risk_reason") or row.get("reason_code") or row.get("reason") or row.get("explanation") or "").strip()
    return bool(reason)


def _has_feedback_link(row: Mapping[str, Any], *, adjudicated_band: str) -> bool:
    response_id = str(row.get("response_id") or row.get("decision_id") or row.get("turn_id") or "").strip()
    return bool(response_id and adjudicated_band)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
    return float(ordered[index])


def summarize_answer_risk_misband_feedback_guard(
    rows: list[Mapping[str, Any]],
    *,
    unresolved_sla_minutes: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    event_total = 0
    feedback_total = 0
    misband_total = 0
    resolved_misband_total = 0
    feedback_linked_total = 0
    reason_missing_total = 0
    audit_context_missing_total = 0
    unresolved_feedback_total = 0
    resolution_latencies: list[float] = []

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        event_total += 1
        if not _has_reason(row):
            reason_missing_total += 1
        if not _has_audit_context(row):
            audit_context_missing_total += 1

        if not _is_feedback_event(row):
            continue

        feedback_total += 1
        predicted_band = _normalize_band(row.get("risk_band") or row.get("predicted_band") or row.get("assigned_band"))
        adjudicated_band = _normalize_band(row.get("adjudicated_band") or row.get("corrected_band"))

        if _has_feedback_link(row, adjudicated_band=adjudicated_band):
            feedback_linked_total += 1

        is_misband = _is_misband(row, predicted_band=predicted_band, adjudicated_band=adjudicated_band)
        resolved = _is_resolved(row)
        if is_misband:
            misband_total += 1
            if resolved:
                resolved_misband_total += 1

        created_at = _feedback_created_at(row)
        resolved_at = _resolved_at(row)
        if created_at is not None and resolved and resolved_at is not None and resolved_at >= created_at:
            resolution_latencies.append((resolved_at - created_at).total_seconds() / 60.0)
        elif created_at is not None and not resolved:
            age_minutes = (now_dt - created_at).total_seconds() / 60.0
            if age_minutes > max(0.0, float(unresolved_sla_minutes)):
                unresolved_feedback_total += 1

    feedback_linkage_ratio = 1.0 if feedback_total == 0 else float(feedback_linked_total) / float(feedback_total)
    misband_resolution_ratio = 1.0 if misband_total == 0 else float(resolved_misband_total) / float(misband_total)
    p95_feedback_latency_minutes = _p95(resolution_latencies)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "event_total": event_total,
        "feedback_total": feedback_total,
        "misband_total": misband_total,
        "resolved_misband_total": resolved_misband_total,
        "misband_resolution_ratio": misband_resolution_ratio,
        "feedback_linked_total": feedback_linked_total,
        "feedback_linkage_ratio": feedback_linkage_ratio,
        "reason_missing_total": reason_missing_total,
        "audit_context_missing_total": audit_context_missing_total,
        "unresolved_feedback_total": unresolved_feedback_total,
        "p95_feedback_latency_minutes": p95_feedback_latency_minutes,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_event_total: int,
    min_feedback_total: int,
    min_feedback_linkage_ratio: float,
    min_misband_resolution_ratio: float,
    max_reason_missing_total: int,
    max_audit_context_missing_total: int,
    max_unresolved_feedback_total: int,
    max_p95_feedback_latency_minutes: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    event_total = _safe_int(summary.get("event_total"), 0)
    feedback_total = _safe_int(summary.get("feedback_total"), 0)
    feedback_linkage_ratio = _safe_float(summary.get("feedback_linkage_ratio"), 0.0)
    misband_resolution_ratio = _safe_float(summary.get("misband_resolution_ratio"), 0.0)
    reason_missing_total = _safe_int(summary.get("reason_missing_total"), 0)
    audit_context_missing_total = _safe_int(summary.get("audit_context_missing_total"), 0)
    unresolved_feedback_total = _safe_int(summary.get("unresolved_feedback_total"), 0)
    p95_feedback_latency_minutes = _safe_float(summary.get("p95_feedback_latency_minutes"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"risk misband feedback window too small: {window_size} < {int(min_window)}")
    if event_total < max(0, int(min_event_total)):
        failures.append(f"risk misband feedback event total too small: {event_total} < {int(min_event_total)}")
    if feedback_total < max(0, int(min_feedback_total)):
        failures.append(f"risk misband feedback total too small: {feedback_total} < {int(min_feedback_total)}")
    if window_size == 0:
        return failures

    if feedback_linkage_ratio < max(0.0, float(min_feedback_linkage_ratio)):
        failures.append(
            f"risk misband feedback linkage ratio below minimum: {feedback_linkage_ratio:.4f} < {float(min_feedback_linkage_ratio):.4f}"
        )
    if misband_resolution_ratio < max(0.0, float(min_misband_resolution_ratio)):
        failures.append(
            "risk misband resolution ratio below minimum: "
            f"{misband_resolution_ratio:.4f} < {float(min_misband_resolution_ratio):.4f}"
        )
    if reason_missing_total > max(0, int(max_reason_missing_total)):
        failures.append(f"risk misband reason-missing total exceeded: {reason_missing_total} > {int(max_reason_missing_total)}")
    if audit_context_missing_total > max(0, int(max_audit_context_missing_total)):
        failures.append(
            "risk misband audit-context-missing total exceeded: "
            f"{audit_context_missing_total} > {int(max_audit_context_missing_total)}"
        )
    if unresolved_feedback_total > max(0, int(max_unresolved_feedback_total)):
        failures.append(
            f"risk misband unresolved-feedback total exceeded: {unresolved_feedback_total} > {int(max_unresolved_feedback_total)}"
        )
    if p95_feedback_latency_minutes > max(0.0, float(max_p95_feedback_latency_minutes)):
        failures.append(
            "risk misband feedback latency p95 exceeded: "
            f"{p95_feedback_latency_minutes:.1f}m > {float(max_p95_feedback_latency_minutes):.1f}m"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"risk misband feedback stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Answer Risk Misband Feedback Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- event_total: {_safe_int(summary.get('event_total'), 0)}")
    lines.append(f"- feedback_total: {_safe_int(summary.get('feedback_total'), 0)}")
    lines.append(f"- misband_total: {_safe_int(summary.get('misband_total'), 0)}")
    lines.append(f"- feedback_linkage_ratio: {_safe_float(summary.get('feedback_linkage_ratio'), 0.0):.4f}")
    lines.append(f"- misband_resolution_ratio: {_safe_float(summary.get('misband_resolution_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate risk misband feedback audit and loop quality.")
    parser.add_argument("--events-jsonl", default="var/risk_banding/misband_feedback_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_answer_risk_misband_feedback_guard")
    parser.add_argument("--unresolved-sla-minutes", type=float, default=60.0)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-event-total", type=int, default=0)
    parser.add_argument("--min-feedback-total", type=int, default=0)
    parser.add_argument("--min-feedback-linkage-ratio", type=float, default=0.0)
    parser.add_argument("--min-misband-resolution-ratio", type=float, default=0.0)
    parser.add_argument("--max-reason-missing-total", type=int, default=1000000)
    parser.add_argument("--max-audit-context-missing-total", type=int, default=1000000)
    parser.add_argument("--max-unresolved-feedback-total", type=int, default=1000000)
    parser.add_argument("--max-p95-feedback-latency-minutes", type=float, default=1000000.0)
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
    summary = summarize_answer_risk_misband_feedback_guard(
        rows,
        unresolved_sla_minutes=max(0.0, float(args.unresolved_sla_minutes)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_event_total=max(0, int(args.min_event_total)),
        min_feedback_total=max(0, int(args.min_feedback_total)),
        min_feedback_linkage_ratio=max(0.0, float(args.min_feedback_linkage_ratio)),
        min_misband_resolution_ratio=max(0.0, float(args.min_misband_resolution_ratio)),
        max_reason_missing_total=max(0, int(args.max_reason_missing_total)),
        max_audit_context_missing_total=max(0, int(args.max_audit_context_missing_total)),
        max_unresolved_feedback_total=max(0, int(args.max_unresolved_feedback_total)),
        max_p95_feedback_latency_minutes=max(0.0, float(args.max_p95_feedback_latency_minutes)),
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
                "unresolved_sla_minutes": float(args.unresolved_sla_minutes),
                "min_window": int(args.min_window),
                "min_event_total": int(args.min_event_total),
                "min_feedback_total": int(args.min_feedback_total),
                "min_feedback_linkage_ratio": float(args.min_feedback_linkage_ratio),
                "min_misband_resolution_ratio": float(args.min_misband_resolution_ratio),
                "max_reason_missing_total": int(args.max_reason_missing_total),
                "max_audit_context_missing_total": int(args.max_audit_context_missing_total),
                "max_unresolved_feedback_total": int(args.max_unresolved_feedback_total),
                "max_p95_feedback_latency_minutes": float(args.max_p95_feedback_latency_minutes),
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
    print(f"feedback_total={_safe_int(summary.get('feedback_total'), 0)}")
    print(f"misband_total={_safe_int(summary.get('misband_total'), 0)}")
    print(f"feedback_linkage_ratio={_safe_float(summary.get('feedback_linkage_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
