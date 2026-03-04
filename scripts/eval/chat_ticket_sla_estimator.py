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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def _ticket_id(row: Mapping[str, Any]) -> str:
    return str(row.get("ticket_id") or row.get("id") or row.get("case_id") or "").strip()


def _is_alerted(row: Mapping[str, Any]) -> bool:
    route = str(row.get("alert_route") or row.get("route") or row.get("next_action") or "").strip().upper()
    if route in {"PRIORITY_ALERT", "SLA_ALERT", "ESCALATE", "PAGER"}:
        return True
    return _safe_bool(row.get("alert_sent"), False)


def _is_actual_breach(estimate: Mapping[str, Any], outcome: Mapping[str, Any] | None) -> bool | None:
    if outcome is not None:
        if outcome.get("sla_breached") is not None:
            return _safe_bool(outcome.get("sla_breached"), False)
        actual = _safe_float(outcome.get("actual_response_minutes"), -1.0)
        target = _safe_float(outcome.get("sla_target_minutes"), -1.0)
        if actual >= 0.0 and target > 0.0:
            return actual > target
    if estimate.get("sla_breached") is not None:
        return _safe_bool(estimate.get("sla_breached"), False)
    actual = _safe_float(estimate.get("actual_response_minutes"), -1.0)
    target = _safe_float(estimate.get("sla_target_minutes"), -1.0)
    if actual >= 0.0 and target > 0.0:
        return actual > target
    return None


def summarize_sla_estimator(
    estimate_rows: list[Mapping[str, Any]],
    outcome_rows: list[Mapping[str, Any]],
    *,
    breach_risk_threshold: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None
    outcomes_by_ticket: dict[str, dict[str, Any]] = {}
    for row in outcome_rows:
        ticket_id = _ticket_id(row)
        if ticket_id:
            outcomes_by_ticket[ticket_id] = {str(k): v for k, v in row.items()}

    estimate_total = 0
    high_risk_total = 0
    high_risk_alerted_total = 0
    missing_features_snapshot_total = 0
    missing_model_version_total = 0
    predicted_minutes_invalid_total = 0

    actual_linked_total = 0
    error_total = 0.0
    actual_breach_total = 0
    detected_breach_total = 0

    for row in estimate_rows:
        ticket_id = _ticket_id(row)
        if not ticket_id:
            continue
        estimate_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        predicted_minutes = _safe_float(row.get("predicted_response_minutes"), -1.0)
        risk_score = _safe_float(row.get("breach_risk_score"), 0.0)
        if predicted_minutes <= 0.0:
            predicted_minutes_invalid_total += 1

        if risk_score >= float(breach_risk_threshold):
            high_risk_total += 1
            if _is_alerted(row):
                high_risk_alerted_total += 1

        if not row.get("features_snapshot"):
            missing_features_snapshot_total += 1
        if not str(row.get("model_version") or row.get("estimator_version") or "").strip():
            missing_model_version_total += 1

        outcome = outcomes_by_ticket.get(ticket_id)
        actual_minutes = _safe_float(
            (outcome or {}).get("actual_response_minutes") if outcome is not None else row.get("actual_response_minutes"),
            -1.0,
        )
        if predicted_minutes > 0.0 and actual_minutes >= 0.0:
            actual_linked_total += 1
            error_total += abs(actual_minutes - predicted_minutes)

        actual_breach = _is_actual_breach(row, outcome)
        if actual_breach is True:
            actual_breach_total += 1
            if risk_score >= float(breach_risk_threshold):
                detected_breach_total += 1

    high_risk_unalerted_total = max(0, high_risk_total - high_risk_alerted_total)
    mae_minutes = 0.0 if actual_linked_total == 0 else float(error_total) / float(actual_linked_total)
    breach_recall = 1.0 if actual_breach_total == 0 else float(detected_breach_total) / float(actual_breach_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(estimate_rows),
        "estimate_total": estimate_total,
        "high_risk_total": high_risk_total,
        "high_risk_alerted_total": high_risk_alerted_total,
        "high_risk_unalerted_total": high_risk_unalerted_total,
        "missing_features_snapshot_total": missing_features_snapshot_total,
        "missing_model_version_total": missing_model_version_total,
        "predicted_minutes_invalid_total": predicted_minutes_invalid_total,
        "actual_linked_total": actual_linked_total,
        "mae_minutes": mae_minutes,
        "actual_breach_total": actual_breach_total,
        "detected_breach_total": detected_breach_total,
        "breach_recall": breach_recall,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_high_risk_unalerted_total: int,
    max_missing_features_snapshot_total: int,
    max_missing_model_version_total: int,
    max_predicted_minutes_invalid_total: int,
    max_mae_minutes: float,
    min_breach_recall: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    high_risk_unalerted_total = _safe_int(summary.get("high_risk_unalerted_total"), 0)
    missing_features_snapshot_total = _safe_int(summary.get("missing_features_snapshot_total"), 0)
    missing_model_version_total = _safe_int(summary.get("missing_model_version_total"), 0)
    predicted_minutes_invalid_total = _safe_int(summary.get("predicted_minutes_invalid_total"), 0)
    mae_minutes = _safe_float(summary.get("mae_minutes"), 0.0)
    breach_recall = _safe_float(summary.get("breach_recall"), 1.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket sla estimator window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if high_risk_unalerted_total > max(0, int(max_high_risk_unalerted_total)):
        failures.append(
            f"ticket sla high-risk unalerted total exceeded: {high_risk_unalerted_total} > {int(max_high_risk_unalerted_total)}"
        )
    if missing_features_snapshot_total > max(0, int(max_missing_features_snapshot_total)):
        failures.append(
            "ticket sla missing feature snapshot total exceeded: "
            f"{missing_features_snapshot_total} > {int(max_missing_features_snapshot_total)}"
        )
    if missing_model_version_total > max(0, int(max_missing_model_version_total)):
        failures.append(
            f"ticket sla missing model version total exceeded: {missing_model_version_total} > {int(max_missing_model_version_total)}"
        )
    if predicted_minutes_invalid_total > max(0, int(max_predicted_minutes_invalid_total)):
        failures.append(
            "ticket sla invalid predicted response minutes total exceeded: "
            f"{predicted_minutes_invalid_total} > {int(max_predicted_minutes_invalid_total)}"
        )
    if mae_minutes > max(0.0, float(max_mae_minutes)):
        failures.append(f"ticket sla MAE exceeded: {mae_minutes:.2f} > {float(max_mae_minutes):.2f}")
    if breach_recall < max(0.0, float(min_breach_recall)):
        failures.append(f"ticket sla breach recall below threshold: {breach_recall:.4f} < {float(min_breach_recall):.4f}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket sla evidence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_estimate_total_drop: int,
    max_high_risk_unalerted_total_increase: int,
    max_missing_features_snapshot_total_increase: int,
    max_missing_model_version_total_increase: int,
    max_predicted_minutes_invalid_total_increase: int,
    max_mae_minutes_increase: float,
    max_breach_recall_drop: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_estimate_total = _safe_int(base_summary.get("estimate_total"), 0)
    cur_estimate_total = _safe_int(current_summary.get("estimate_total"), 0)
    estimate_total_drop = max(0, base_estimate_total - cur_estimate_total)
    if estimate_total_drop > max(0, int(max_estimate_total_drop)):
        failures.append(
            "estimate_total regression: "
            f"baseline={base_estimate_total}, current={cur_estimate_total}, "
            f"allowed_drop={max(0, int(max_estimate_total_drop))}"
        )

    baseline_increase_pairs = [
        ("high_risk_unalerted_total", max_high_risk_unalerted_total_increase),
        ("missing_features_snapshot_total", max_missing_features_snapshot_total_increase),
        ("missing_model_version_total", max_missing_model_version_total_increase),
        ("predicted_minutes_invalid_total", max_predicted_minutes_invalid_total_increase),
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

    base_mae_minutes = _safe_float(base_summary.get("mae_minutes"), 0.0)
    cur_mae_minutes = _safe_float(current_summary.get("mae_minutes"), 0.0)
    mae_minutes_increase = max(0.0, cur_mae_minutes - base_mae_minutes)
    if mae_minutes_increase > max(0.0, float(max_mae_minutes_increase)):
        failures.append(
            "mae_minutes regression: "
            f"baseline={base_mae_minutes:.6f}, current={cur_mae_minutes:.6f}, "
            f"allowed_increase={float(max_mae_minutes_increase):.6f}"
        )

    base_breach_recall = _safe_float(base_summary.get("breach_recall"), 0.0)
    cur_breach_recall = _safe_float(current_summary.get("breach_recall"), 0.0)
    breach_recall_drop = max(0.0, base_breach_recall - cur_breach_recall)
    if breach_recall_drop > max(0.0, float(max_breach_recall_drop)):
        failures.append(
            "breach_recall regression: "
            f"baseline={base_breach_recall:.6f}, current={cur_breach_recall:.6f}, "
            f"allowed_drop={float(max_breach_recall_drop):.6f}"
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
    lines.append("# Chat Ticket SLA Estimator")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- estimates_jsonl: {payload.get('estimates_jsonl')}")
    lines.append(f"- outcomes_jsonl: {payload.get('outcomes_jsonl')}")
    lines.append(f"- estimate_total: {_safe_int(summary.get('estimate_total'), 0)}")
    lines.append(f"- high_risk_unalerted_total: {_safe_int(summary.get('high_risk_unalerted_total'), 0)}")
    lines.append(f"- mae_minutes: {_safe_float(summary.get('mae_minutes'), 0.0):.2f}")
    lines.append(f"- breach_recall: {_safe_float(summary.get('breach_recall'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat ticket SLA estimator quality.")
    parser.add_argument("--estimates-jsonl", default="var/chat_ticket/sla_estimates.jsonl")
    parser.add_argument("--outcomes-jsonl", default="var/chat_ticket/sla_outcomes.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--breach-risk-threshold", type=float, default=0.7)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_sla_estimator")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-high-risk-unalerted-total", type=int, default=0)
    parser.add_argument("--max-missing-features-snapshot-total", type=int, default=0)
    parser.add_argument("--max-missing-model-version-total", type=int, default=0)
    parser.add_argument("--max-predicted-minutes-invalid-total", type=int, default=0)
    parser.add_argument("--max-mae-minutes", type=float, default=60.0)
    parser.add_argument("--min-breach-recall", type=float, default=0.6)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-estimate-total-drop", type=int, default=10)
    parser.add_argument("--max-high-risk-unalerted-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-features-snapshot-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-model-version-total-increase", type=int, default=0)
    parser.add_argument("--max-predicted-minutes-invalid-total-increase", type=int, default=0)
    parser.add_argument("--max-mae-minutes-increase", type=float, default=10.0)
    parser.add_argument("--max-breach-recall-drop", type=float, default=0.05)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    estimate_rows = _read_jsonl(
        Path(args.estimates_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    outcome_rows = _read_jsonl(
        Path(args.outcomes_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_sla_estimator(
        estimate_rows,
        outcome_rows,
        breach_risk_threshold=max(0.0, float(args.breach_risk_threshold)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_high_risk_unalerted_total=max(0, int(args.max_high_risk_unalerted_total)),
        max_missing_features_snapshot_total=max(0, int(args.max_missing_features_snapshot_total)),
        max_missing_model_version_total=max(0, int(args.max_missing_model_version_total)),
        max_predicted_minutes_invalid_total=max(0, int(args.max_predicted_minutes_invalid_total)),
        max_mae_minutes=max(0.0, float(args.max_mae_minutes)),
        min_breach_recall=max(0.0, float(args.min_breach_recall)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_estimate_total_drop=max(0, int(args.max_estimate_total_drop)),
            max_high_risk_unalerted_total_increase=max(0, int(args.max_high_risk_unalerted_total_increase)),
            max_missing_features_snapshot_total_increase=max(
                0, int(args.max_missing_features_snapshot_total_increase)
            ),
            max_missing_model_version_total_increase=max(0, int(args.max_missing_model_version_total_increase)),
            max_predicted_minutes_invalid_total_increase=max(
                0, int(args.max_predicted_minutes_invalid_total_increase)
            ),
            max_mae_minutes_increase=max(0.0, float(args.max_mae_minutes_increase)),
            max_breach_recall_drop=max(0.0, float(args.max_breach_recall_drop)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "estimates_jsonl": str(args.estimates_jsonl),
        "outcomes_jsonl": str(args.outcomes_jsonl),
        "source": {
            "estimates_jsonl": str(args.estimates_jsonl),
            "outcomes_jsonl": str(args.outcomes_jsonl),
            "window_hours": int(args.window_hours),
            "limit": int(args.limit),
            "breach_risk_threshold": float(args.breach_risk_threshold),
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
                "breach_risk_threshold": float(args.breach_risk_threshold),
                "max_high_risk_unalerted_total": int(args.max_high_risk_unalerted_total),
                "max_missing_features_snapshot_total": int(args.max_missing_features_snapshot_total),
                "max_missing_model_version_total": int(args.max_missing_model_version_total),
                "max_predicted_minutes_invalid_total": int(args.max_predicted_minutes_invalid_total),
                "max_mae_minutes": float(args.max_mae_minutes),
                "min_breach_recall": float(args.min_breach_recall),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_estimate_total_drop": int(args.max_estimate_total_drop),
                "max_high_risk_unalerted_total_increase": int(args.max_high_risk_unalerted_total_increase),
                "max_missing_features_snapshot_total_increase": int(
                    args.max_missing_features_snapshot_total_increase
                ),
                "max_missing_model_version_total_increase": int(args.max_missing_model_version_total_increase),
                "max_predicted_minutes_invalid_total_increase": int(
                    args.max_predicted_minutes_invalid_total_increase
                ),
                "max_mae_minutes_increase": float(args.max_mae_minutes_increase),
                "max_breach_recall_drop": float(args.max_breach_recall_drop),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
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
    print(f"estimate_total={_safe_int(summary.get('estimate_total'), 0)}")
    print(f"high_risk_unalerted_total={_safe_int(summary.get('high_risk_unalerted_total'), 0)}")
    print(f"mae_minutes={_safe_float(summary.get('mae_minutes'), 0.0):.2f}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
