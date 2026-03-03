#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


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
    for key in ("corrected_at", "timestamp", "event_time", "created_at", "updated_at", "generated_at"):
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


def _ticket_id(row: Mapping[str, Any]) -> str:
    return str(row.get("ticket_id") or row.get("id") or row.get("case_id") or "").strip()


def _is_outcome_closed(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or row.get("final_status") or row.get("resolution") or "").strip().upper()
    if status in {"RESOLVED", "CLOSED", "DONE", "COMPLETED"}:
        return True
    return _safe_bool(row.get("resolved"), False)


def _is_corrected(row: Mapping[str, Any]) -> bool:
    if row.get("is_corrected") is not None:
        return _safe_bool(row.get("is_corrected"), False)
    predicted_category = str(row.get("predicted_category") or "").strip().upper()
    predicted_severity = str(row.get("predicted_severity") or "").strip().upper()
    final_category = str(row.get("final_category") or "").strip().upper()
    final_severity = str(row.get("final_severity") or "").strip().upper()
    if final_category and predicted_category and final_category != predicted_category:
        return True
    if final_severity and predicted_severity and final_severity != predicted_severity:
        return True
    if str(row.get("feedback_type") or "").strip().upper() in {"CORRECTION", "OVERRIDE"}:
        return True
    if str(row.get("corrected_by") or row.get("reviewer") or "").strip() and (final_category or final_severity):
        return True
    return False


def summarize_feedback_loop(
    feedback_rows: list[Mapping[str, Any]],
    outcome_rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    outcomes_by_ticket: dict[str, dict[str, Any]] = {}
    outcome_total = 0
    closed_outcome_total = 0
    for row in outcome_rows:
        ticket_id = _ticket_id(row)
        if not ticket_id:
            continue
        outcome_total += 1
        outcomes_by_ticket[ticket_id] = {str(k): v for k, v in row.items()}
        if _is_outcome_closed(row):
            closed_outcome_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    feedback_total = 0
    corrected_total = 0
    feedback_linked_total = 0
    missing_actor_total = 0
    missing_corrected_time_total = 0
    missing_model_version_total = 0
    monthly_samples: dict[str, int] = {}

    for row in feedback_rows:
        ticket_id = _ticket_id(row)
        if not ticket_id:
            continue
        feedback_total += 1

        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        model_version = str(
            row.get("model_version") or row.get("classifier_model_version") or row.get("estimator_version") or ""
        ).strip()
        if not model_version:
            missing_model_version_total += 1

        if not _is_corrected(row):
            continue
        corrected_total += 1

        if ticket_id in outcomes_by_ticket:
            feedback_linked_total += 1

        actor = str(row.get("corrected_by") or row.get("reviewer") or row.get("updated_by") or "").strip()
        if not actor:
            missing_actor_total += 1

        corrected_at = _parse_ts(row.get("corrected_at")) or _event_ts(row)
        if corrected_at is None:
            missing_corrected_time_total += 1
        else:
            month_key = corrected_at.strftime("%Y-%m")
            monthly_samples[month_key] = monthly_samples.get(month_key, 0) + 1

    correction_rate = 0.0 if feedback_total == 0 else float(corrected_total) / float(feedback_total)
    feedback_linkage_ratio = 1.0 if corrected_total == 0 else float(feedback_linked_total) / float(corrected_total)
    monthly_bucket_total = len(monthly_samples)
    monthly_min_samples = min(monthly_samples.values()) if monthly_samples else 0
    monthly_max_samples = max(monthly_samples.values()) if monthly_samples else 0
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(feedback_rows),
        "feedback_total": feedback_total,
        "corrected_total": corrected_total,
        "correction_rate": correction_rate,
        "feedback_linked_total": feedback_linked_total,
        "feedback_linkage_ratio": feedback_linkage_ratio,
        "missing_actor_total": missing_actor_total,
        "missing_corrected_time_total": missing_corrected_time_total,
        "missing_model_version_total": missing_model_version_total,
        "outcome_total": outcome_total,
        "closed_outcome_total": closed_outcome_total,
        "monthly_bucket_total": monthly_bucket_total,
        "monthly_min_samples": monthly_min_samples,
        "monthly_max_samples": monthly_max_samples,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_feedback_total: int,
    max_missing_actor_total: int,
    max_missing_corrected_time_total: int,
    max_missing_model_version_total: int,
    min_feedback_linkage_ratio: float,
    min_monthly_bucket_total: int,
    min_monthly_samples_per_bucket: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    feedback_total = _safe_int(summary.get("feedback_total"), 0)
    missing_actor_total = _safe_int(summary.get("missing_actor_total"), 0)
    missing_corrected_time_total = _safe_int(summary.get("missing_corrected_time_total"), 0)
    missing_model_version_total = _safe_int(summary.get("missing_model_version_total"), 0)
    feedback_linkage_ratio = _safe_float(summary.get("feedback_linkage_ratio"), 1.0)
    monthly_bucket_total = _safe_int(summary.get("monthly_bucket_total"), 0)
    monthly_min_samples = _safe_int(summary.get("monthly_min_samples"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket feedback loop window too small: {window_size} < {int(min_window)}")
    if feedback_total < max(0, int(min_feedback_total)):
        failures.append(f"ticket feedback total too small: {feedback_total} < {int(min_feedback_total)}")
    if window_size == 0:
        return failures

    if missing_actor_total > max(0, int(max_missing_actor_total)):
        failures.append(f"ticket feedback missing actor total exceeded: {missing_actor_total} > {int(max_missing_actor_total)}")
    if missing_corrected_time_total > max(0, int(max_missing_corrected_time_total)):
        failures.append(
            "ticket feedback missing corrected timestamp total exceeded: "
            f"{missing_corrected_time_total} > {int(max_missing_corrected_time_total)}"
        )
    if missing_model_version_total > max(0, int(max_missing_model_version_total)):
        failures.append(
            f"ticket feedback missing model version total exceeded: {missing_model_version_total} > {int(max_missing_model_version_total)}"
        )
    if feedback_linkage_ratio < max(0.0, float(min_feedback_linkage_ratio)):
        failures.append(
            f"ticket feedback linkage ratio below threshold: {feedback_linkage_ratio:.4f} < {float(min_feedback_linkage_ratio):.4f}"
        )
    if monthly_bucket_total < max(0, int(min_monthly_bucket_total)):
        failures.append(
            f"ticket feedback monthly bucket total too small: {monthly_bucket_total} < {int(min_monthly_bucket_total)}"
        )
    if monthly_bucket_total > 0 and monthly_min_samples < max(0, int(min_monthly_samples_per_bucket)):
        failures.append(
            "ticket feedback monthly minimum samples below threshold: "
            f"{monthly_min_samples} < {int(min_monthly_samples_per_bucket)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket feedback evidence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Ticket Feedback Loop")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- feedback_jsonl: {payload.get('feedback_jsonl')}")
    lines.append(f"- outcomes_jsonl: {payload.get('outcomes_jsonl')}")
    lines.append(f"- feedback_total: {_safe_int(summary.get('feedback_total'), 0)}")
    lines.append(f"- corrected_total: {_safe_int(summary.get('corrected_total'), 0)}")
    lines.append(f"- feedback_linkage_ratio: {_safe_float(summary.get('feedback_linkage_ratio'), 1.0):.4f}")
    lines.append(f"- monthly_bucket_total: {_safe_int(summary.get('monthly_bucket_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat ticket feedback loop quality.")
    parser.add_argument("--feedback-jsonl", default="var/chat_ticket/triage_feedback.jsonl")
    parser.add_argument("--outcomes-jsonl", default="var/chat_ticket/sla_outcomes.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_feedback_loop")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-feedback-total", type=int, default=0)
    parser.add_argument("--max-missing-actor-total", type=int, default=0)
    parser.add_argument("--max-missing-corrected-time-total", type=int, default=0)
    parser.add_argument("--max-missing-model-version-total", type=int, default=0)
    parser.add_argument("--min-feedback-linkage-ratio", type=float, default=0.8)
    parser.add_argument("--min-monthly-bucket-total", type=int, default=1)
    parser.add_argument("--min-monthly-samples-per-bucket", type=int, default=10)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    feedback_rows = _read_jsonl(
        Path(args.feedback_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    outcome_rows = _read_jsonl(
        Path(args.outcomes_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_feedback_loop(feedback_rows, outcome_rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_feedback_total=max(0, int(args.min_feedback_total)),
        max_missing_actor_total=max(0, int(args.max_missing_actor_total)),
        max_missing_corrected_time_total=max(0, int(args.max_missing_corrected_time_total)),
        max_missing_model_version_total=max(0, int(args.max_missing_model_version_total)),
        min_feedback_linkage_ratio=max(0.0, float(args.min_feedback_linkage_ratio)),
        min_monthly_bucket_total=max(0, int(args.min_monthly_bucket_total)),
        min_monthly_samples_per_bucket=max(0, int(args.min_monthly_samples_per_bucket)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feedback_jsonl": str(args.feedback_jsonl),
        "outcomes_jsonl": str(args.outcomes_jsonl),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_feedback_total": int(args.min_feedback_total),
                "max_missing_actor_total": int(args.max_missing_actor_total),
                "max_missing_corrected_time_total": int(args.max_missing_corrected_time_total),
                "max_missing_model_version_total": int(args.max_missing_model_version_total),
                "min_feedback_linkage_ratio": float(args.min_feedback_linkage_ratio),
                "min_monthly_bucket_total": int(args.min_monthly_bucket_total),
                "min_monthly_samples_per_bucket": int(args.min_monthly_samples_per_bucket),
                "max_stale_minutes": float(args.max_stale_minutes),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"feedback_total={_safe_int(summary.get('feedback_total'), 0)}")
    print(f"corrected_total={_safe_int(summary.get('corrected_total'), 0)}")
    print(f"feedback_linkage_ratio={_safe_float(summary.get('feedback_linkage_ratio'), 1.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
