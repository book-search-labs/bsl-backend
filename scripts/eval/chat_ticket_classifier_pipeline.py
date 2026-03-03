#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_CATEGORIES = {"ORDER", "PAYMENT", "SHIPPING", "REFUND", "ACCOUNT", "OTHER"}
VALID_SEVERITIES = {"S1", "S2", "S3", "S4"}


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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _read_rows(path: Path, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
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


def _is_prediction_row(row: Mapping[str, Any]) -> bool:
    event = str(row.get("event_type") or row.get("event") or row.get("status") or "").strip().upper()
    if event in {"TRIAGE_PREDICT", "TRIAGE_RESULT", "PREDICTION"}:
        return True
    return any(
        row.get(key) is not None
        for key in ("predicted_category", "predicted_severity", "confidence", "ticket_id")
    )


def _is_manual_review(row: Mapping[str, Any]) -> bool:
    queue = str(row.get("queue") or row.get("route") or row.get("next_action") or "").strip().upper()
    if queue in {"MANUAL_REVIEW", "HUMAN_REVIEW", "REVIEW_QUEUE"}:
        return True
    return _safe_bool(row.get("manual_review"), False)


def summarize_classifier_pipeline(
    rows: list[Mapping[str, Any]],
    *,
    low_confidence_threshold: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    prediction_total = 0
    low_confidence_total = 0
    low_confidence_manual_review_total = 0
    unknown_category_total = 0
    unknown_severity_total = 0
    missing_model_version_total = 0
    missing_signal_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _is_prediction_row(row):
            continue
        prediction_total += 1
        confidence = _safe_float(row.get("confidence"), 0.0)
        if confidence < float(low_confidence_threshold):
            low_confidence_total += 1
            if _is_manual_review(row):
                low_confidence_manual_review_total += 1

        category = str(row.get("predicted_category") or row.get("category") or "").strip().upper()
        severity = str(row.get("predicted_severity") or row.get("severity") or "").strip().upper()
        if category and category not in VALID_CATEGORIES:
            unknown_category_total += 1
        if severity and severity not in VALID_SEVERITIES:
            unknown_severity_total += 1

        if not str(row.get("model_version") or row.get("classifier_version") or "").strip():
            missing_model_version_total += 1

        has_signal = bool(
            str(row.get("conversation_summary") or row.get("summary") or "").strip()
            or str(row.get("reason_code") or "").strip()
            or bool(row.get("tool_failures"))
            or bool(row.get("tool_failure_total"))
        )
        if not has_signal:
            missing_signal_total += 1

    low_confidence_unrouted_total = max(0, low_confidence_total - low_confidence_manual_review_total)
    manual_review_coverage_ratio = (
        1.0 if low_confidence_total == 0 else float(low_confidence_manual_review_total) / float(low_confidence_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "prediction_total": prediction_total,
        "low_confidence_threshold": float(low_confidence_threshold),
        "low_confidence_total": low_confidence_total,
        "low_confidence_manual_review_total": low_confidence_manual_review_total,
        "low_confidence_unrouted_total": low_confidence_unrouted_total,
        "manual_review_coverage_ratio": manual_review_coverage_ratio,
        "unknown_category_total": unknown_category_total,
        "unknown_severity_total": unknown_severity_total,
        "missing_model_version_total": missing_model_version_total,
        "missing_signal_total": missing_signal_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_low_confidence_unrouted_total: int,
    min_manual_review_coverage_ratio: float,
    max_unknown_category_total: int,
    max_unknown_severity_total: int,
    max_missing_model_version_total: int,
    max_missing_signal_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    low_confidence_unrouted_total = _safe_int(summary.get("low_confidence_unrouted_total"), 0)
    manual_review_coverage_ratio = _safe_float(summary.get("manual_review_coverage_ratio"), 1.0)
    unknown_category_total = _safe_int(summary.get("unknown_category_total"), 0)
    unknown_severity_total = _safe_int(summary.get("unknown_severity_total"), 0)
    missing_model_version_total = _safe_int(summary.get("missing_model_version_total"), 0)
    missing_signal_total = _safe_int(summary.get("missing_signal_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket classifier window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if low_confidence_unrouted_total > max(0, int(max_low_confidence_unrouted_total)):
        failures.append(
            "ticket classifier low-confidence unrouted total exceeded: "
            f"{low_confidence_unrouted_total} > {int(max_low_confidence_unrouted_total)}"
        )
    if manual_review_coverage_ratio < max(0.0, float(min_manual_review_coverage_ratio)):
        failures.append(
            "ticket classifier manual-review coverage ratio below threshold: "
            f"{manual_review_coverage_ratio:.4f} < {float(min_manual_review_coverage_ratio):.4f}"
        )
    if unknown_category_total > max(0, int(max_unknown_category_total)):
        failures.append(
            f"ticket classifier unknown category total exceeded: {unknown_category_total} > {int(max_unknown_category_total)}"
        )
    if unknown_severity_total > max(0, int(max_unknown_severity_total)):
        failures.append(
            f"ticket classifier unknown severity total exceeded: {unknown_severity_total} > {int(max_unknown_severity_total)}"
        )
    if missing_model_version_total > max(0, int(max_missing_model_version_total)):
        failures.append(
            "ticket classifier missing model version total exceeded: "
            f"{missing_model_version_total} > {int(max_missing_model_version_total)}"
        )
    if missing_signal_total > max(0, int(max_missing_signal_total)):
        failures.append(
            f"ticket classifier missing input signal total exceeded: {missing_signal_total} > {int(max_missing_signal_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket classifier evidence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Ticket Classifier Pipeline")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- prediction_total: {_safe_int(summary.get('prediction_total'), 0)}")
    lines.append(f"- low_confidence_total: {_safe_int(summary.get('low_confidence_total'), 0)}")
    lines.append(f"- low_confidence_unrouted_total: {_safe_int(summary.get('low_confidence_unrouted_total'), 0)}")
    lines.append(f"- manual_review_coverage_ratio: {_safe_float(summary.get('manual_review_coverage_ratio'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat ticket classifier pipeline quality.")
    parser.add_argument("--events-jsonl", default="var/chat_ticket/triage_predictions.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--low-confidence-threshold", type=float, default=0.7)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_classifier_pipeline")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-low-confidence-unrouted-total", type=int, default=0)
    parser.add_argument("--min-manual-review-coverage-ratio", type=float, default=0.8)
    parser.add_argument("--max-unknown-category-total", type=int, default=0)
    parser.add_argument("--max-unknown-severity-total", type=int, default=0)
    parser.add_argument("--max-missing-model-version-total", type=int, default=0)
    parser.add_argument("--max-missing-signal-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    events_path = Path(args.events_jsonl)
    rows = _read_rows(
        events_path,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_classifier_pipeline(
        rows,
        low_confidence_threshold=max(0.0, float(args.low_confidence_threshold)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_low_confidence_unrouted_total=max(0, int(args.max_low_confidence_unrouted_total)),
        min_manual_review_coverage_ratio=max(0.0, float(args.min_manual_review_coverage_ratio)),
        max_unknown_category_total=max(0, int(args.max_unknown_category_total)),
        max_unknown_severity_total=max(0, int(args.max_unknown_severity_total)),
        max_missing_model_version_total=max(0, int(args.max_missing_model_version_total)),
        max_missing_signal_total=max(0, int(args.max_missing_signal_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(events_path),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "low_confidence_threshold": float(args.low_confidence_threshold),
                "max_low_confidence_unrouted_total": int(args.max_low_confidence_unrouted_total),
                "min_manual_review_coverage_ratio": float(args.min_manual_review_coverage_ratio),
                "max_unknown_category_total": int(args.max_unknown_category_total),
                "max_unknown_severity_total": int(args.max_unknown_severity_total),
                "max_missing_model_version_total": int(args.max_missing_model_version_total),
                "max_missing_signal_total": int(args.max_missing_signal_total),
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
    print(f"prediction_total={_safe_int(summary.get('prediction_total'), 0)}")
    print(f"low_confidence_total={_safe_int(summary.get('low_confidence_total'), 0)}")
    print(f"low_confidence_unrouted_total={_safe_int(summary.get('low_confidence_unrouted_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
