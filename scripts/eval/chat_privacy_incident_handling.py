#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SEVERITY_WEIGHT = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
HIGH_SEVERITIES = {"HIGH", "CRITICAL"}
RESOLVED_STATUSES = {"RESOLVED", "CLOSED", "DONE"}


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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "detected_at", "generated_at"):
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


def _severity(row: Mapping[str, Any]) -> str:
    text = str(row.get("severity") or row.get("incident_severity") or "MEDIUM").strip().upper()
    aliases = {"P1": "CRITICAL", "P2": "HIGH", "P3": "MEDIUM", "P4": "LOW"}
    return aliases.get(text, text or "MEDIUM")


def _is_alert_sent(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("alert_sent"), False):
        return True
    status = str(row.get("alert_status") or "").strip().upper()
    return status in {"SENT", "DELIVERED", "ACKED"}


def _is_queued(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("operator_queued"), False):
        return True
    queue_id = str(row.get("queue_id") or row.get("operator_ticket_id") or "").strip()
    return bool(queue_id)


def _is_resolved(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("resolved"), False):
        return True
    status = str(row.get("status") or row.get("incident_status") or "").strip().upper()
    return status in RESOLVED_STATUSES


def _ack_latency_minutes(row: Mapping[str, Any]) -> float | None:
    explicit_seconds = row.get("ack_latency_seconds")
    if explicit_seconds is not None:
        return _safe_float(explicit_seconds, 0.0) / 60.0
    explicit_minutes = row.get("ack_latency_minutes")
    if explicit_minutes is not None:
        return _safe_float(explicit_minutes, 0.0)
    detected_at = _parse_ts(row.get("detected_at") or row.get("created_at"))
    acked_at = _parse_ts(row.get("acked_at") or row.get("first_ack_at"))
    if detected_at is None or acked_at is None:
        return None
    return max(0.0, (acked_at - detected_at).total_seconds() / 60.0)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_incident_handling(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    incident_total = 0
    high_severity_total = 0
    alert_sent_total = 0
    alert_miss_total = 0
    queued_total = 0
    high_unqueued_total = 0
    acked_total = 0
    resolved_total = 0
    missing_runbook_link_total = 0
    severity_distribution: dict[str, int] = {}
    ack_latency_samples: list[float] = []

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        incident_total += 1
        severity = _severity(row)
        severity_distribution[severity] = severity_distribution.get(severity, 0) + 1

        is_high = severity in HIGH_SEVERITIES
        if is_high:
            high_severity_total += 1

        alert_sent = _is_alert_sent(row)
        if alert_sent:
            alert_sent_total += 1
        if is_high and not alert_sent:
            alert_miss_total += 1

        queued = _is_queued(row)
        if queued:
            queued_total += 1
        if is_high and not queued:
            high_unqueued_total += 1

        latency = _ack_latency_minutes(row)
        if latency is not None:
            acked_total += 1
            ack_latency_samples.append(latency)

        if _is_resolved(row):
            resolved_total += 1

        runbook_link = str(row.get("runbook_link") or row.get("playbook_link") or "").strip()
        if not runbook_link:
            missing_runbook_link_total += 1

    high_queue_coverage_ratio = 1.0 if high_severity_total == 0 else float(high_severity_total - high_unqueued_total) / float(high_severity_total)
    resolved_ratio = 1.0 if incident_total == 0 else float(resolved_total) / float(incident_total)
    p95_ack_latency_minutes = _p95(ack_latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "incident_total": incident_total,
        "high_severity_total": high_severity_total,
        "alert_sent_total": alert_sent_total,
        "alert_miss_total": alert_miss_total,
        "queued_total": queued_total,
        "high_unqueued_total": high_unqueued_total,
        "high_queue_coverage_ratio": high_queue_coverage_ratio,
        "acked_total": acked_total,
        "p95_ack_latency_minutes": p95_ack_latency_minutes,
        "resolved_total": resolved_total,
        "resolved_ratio": resolved_ratio,
        "missing_runbook_link_total": missing_runbook_link_total,
        "severity_distribution": [
            {"severity": key, "count": value} for key, value in sorted(severity_distribution.items(), key=lambda x: x[0])
        ],
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_incident_total: int,
    min_high_queue_coverage_ratio: float,
    min_resolved_ratio: float,
    max_alert_miss_total: int,
    max_high_unqueued_total: int,
    max_p95_ack_latency_minutes: float,
    max_missing_runbook_link_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    incident_total = _safe_int(summary.get("incident_total"), 0)
    high_queue_coverage_ratio = _safe_float(summary.get("high_queue_coverage_ratio"), 0.0)
    resolved_ratio = _safe_float(summary.get("resolved_ratio"), 0.0)
    alert_miss_total = _safe_int(summary.get("alert_miss_total"), 0)
    high_unqueued_total = _safe_int(summary.get("high_unqueued_total"), 0)
    p95_ack_latency_minutes = _safe_float(summary.get("p95_ack_latency_minutes"), 0.0)
    missing_runbook_link_total = _safe_int(summary.get("missing_runbook_link_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat privacy incident window too small: {window_size} < {int(min_window)}")
    if incident_total < max(0, int(min_incident_total)):
        failures.append(f"chat privacy incident total too small: {incident_total} < {int(min_incident_total)}")
    if window_size == 0:
        return failures

    if high_queue_coverage_ratio < max(0.0, float(min_high_queue_coverage_ratio)):
        failures.append(
            "chat privacy incident high queue coverage ratio below minimum: "
            f"{high_queue_coverage_ratio:.4f} < {float(min_high_queue_coverage_ratio):.4f}"
        )
    if resolved_ratio < max(0.0, float(min_resolved_ratio)):
        failures.append(f"chat privacy incident resolved ratio below minimum: {resolved_ratio:.4f} < {float(min_resolved_ratio):.4f}")
    if alert_miss_total > max(0, int(max_alert_miss_total)):
        failures.append(f"chat privacy incident alert miss total exceeded: {alert_miss_total} > {int(max_alert_miss_total)}")
    if high_unqueued_total > max(0, int(max_high_unqueued_total)):
        failures.append(f"chat privacy incident high unqueued total exceeded: {high_unqueued_total} > {int(max_high_unqueued_total)}")
    if p95_ack_latency_minutes > max(0.0, float(max_p95_ack_latency_minutes)):
        failures.append(
            "chat privacy incident p95 ack latency exceeded: "
            f"{p95_ack_latency_minutes:.2f}m > {float(max_p95_ack_latency_minutes):.2f}m"
        )
    if missing_runbook_link_total > max(0, int(max_missing_runbook_link_total)):
        failures.append(
            "chat privacy incident missing runbook link total exceeded: "
            f"{missing_runbook_link_total} > {int(max_missing_runbook_link_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat privacy incident stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_incident_total_drop: int,
    max_high_severity_total_drop: int,
    max_alert_sent_total_drop: int,
    max_resolved_total_drop: int,
    max_alert_miss_total_increase: int,
    max_high_unqueued_total_increase: int,
    max_missing_runbook_link_total_increase: int,
    max_high_queue_coverage_ratio_drop: float,
    max_resolved_ratio_drop: float,
    max_p95_ack_latency_minutes_increase: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("incident_total", max_incident_total_drop),
        ("high_severity_total", max_high_severity_total_drop),
        ("alert_sent_total", max_alert_sent_total_drop),
        ("resolved_total", max_resolved_total_drop),
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
        ("alert_miss_total", max_alert_miss_total_increase),
        ("high_unqueued_total", max_high_unqueued_total_increase),
        ("missing_runbook_link_total", max_missing_runbook_link_total_increase),
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

    base_high_queue_coverage_ratio = _safe_float(base_summary.get("high_queue_coverage_ratio"), 1.0)
    cur_high_queue_coverage_ratio = _safe_float(current_summary.get("high_queue_coverage_ratio"), 1.0)
    high_queue_coverage_ratio_drop = max(0.0, base_high_queue_coverage_ratio - cur_high_queue_coverage_ratio)
    if high_queue_coverage_ratio_drop > max(0.0, float(max_high_queue_coverage_ratio_drop)):
        failures.append(
            "high_queue_coverage_ratio regression: "
            f"baseline={base_high_queue_coverage_ratio:.6f}, current={cur_high_queue_coverage_ratio:.6f}, "
            f"allowed_drop={float(max_high_queue_coverage_ratio_drop):.6f}"
        )

    base_resolved_ratio = _safe_float(base_summary.get("resolved_ratio"), 1.0)
    cur_resolved_ratio = _safe_float(current_summary.get("resolved_ratio"), 1.0)
    resolved_ratio_drop = max(0.0, base_resolved_ratio - cur_resolved_ratio)
    if resolved_ratio_drop > max(0.0, float(max_resolved_ratio_drop)):
        failures.append(
            "resolved_ratio regression: "
            f"baseline={base_resolved_ratio:.6f}, current={cur_resolved_ratio:.6f}, "
            f"allowed_drop={float(max_resolved_ratio_drop):.6f}"
        )

    base_p95_ack_latency_minutes = _safe_float(base_summary.get("p95_ack_latency_minutes"), 0.0)
    cur_p95_ack_latency_minutes = _safe_float(current_summary.get("p95_ack_latency_minutes"), 0.0)
    p95_ack_latency_minutes_increase = max(0.0, cur_p95_ack_latency_minutes - base_p95_ack_latency_minutes)
    if p95_ack_latency_minutes_increase > max(0.0, float(max_p95_ack_latency_minutes_increase)):
        failures.append(
            "p95_ack_latency_minutes regression: "
            f"baseline={base_p95_ack_latency_minutes:.6f}, current={cur_p95_ack_latency_minutes:.6f}, "
            f"allowed_increase={float(max_p95_ack_latency_minutes_increase):.6f}"
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
    lines.append("# Chat Privacy Incident Handling")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- incident_total: {_safe_int(summary.get('incident_total'), 0)}")
    lines.append(f"- high_severity_total: {_safe_int(summary.get('high_severity_total'), 0)}")
    lines.append(f"- alert_miss_total: {_safe_int(summary.get('alert_miss_total'), 0)}")
    lines.append(f"- high_unqueued_total: {_safe_int(summary.get('high_unqueued_total'), 0)}")
    lines.append(f"- p95_ack_latency_minutes: {_safe_float(summary.get('p95_ack_latency_minutes'), 0.0):.2f}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat privacy incident handling and operator response loop.")
    parser.add_argument("--events-jsonl", default="var/chat_privacy/privacy_incidents.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_privacy_incident_handling")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-incident-total", type=int, default=0)
    parser.add_argument("--min-high-queue-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-resolved-ratio", type=float, default=0.0)
    parser.add_argument("--max-alert-miss-total", type=int, default=0)
    parser.add_argument("--max-high-unqueued-total", type=int, default=0)
    parser.add_argument("--max-p95-ack-latency-minutes", type=float, default=0.0)
    parser.add_argument("--max-missing-runbook-link-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-incident-total-drop", type=int, default=10)
    parser.add_argument("--max-high-severity-total-drop", type=int, default=5)
    parser.add_argument("--max-alert-sent-total-drop", type=int, default=10)
    parser.add_argument("--max-resolved-total-drop", type=int, default=10)
    parser.add_argument("--max-alert-miss-total-increase", type=int, default=0)
    parser.add_argument("--max-high-unqueued-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-runbook-link-total-increase", type=int, default=0)
    parser.add_argument("--max-high-queue-coverage-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-resolved-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-p95-ack-latency-minutes-increase", type=float, default=30.0)
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
    summary = summarize_incident_handling(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_incident_total=max(0, int(args.min_incident_total)),
        min_high_queue_coverage_ratio=max(0.0, float(args.min_high_queue_coverage_ratio)),
        min_resolved_ratio=max(0.0, float(args.min_resolved_ratio)),
        max_alert_miss_total=max(0, int(args.max_alert_miss_total)),
        max_high_unqueued_total=max(0, int(args.max_high_unqueued_total)),
        max_p95_ack_latency_minutes=max(0.0, float(args.max_p95_ack_latency_minutes)),
        max_missing_runbook_link_total=max(0, int(args.max_missing_runbook_link_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_incident_total_drop=max(0, int(args.max_incident_total_drop)),
            max_high_severity_total_drop=max(0, int(args.max_high_severity_total_drop)),
            max_alert_sent_total_drop=max(0, int(args.max_alert_sent_total_drop)),
            max_resolved_total_drop=max(0, int(args.max_resolved_total_drop)),
            max_alert_miss_total_increase=max(0, int(args.max_alert_miss_total_increase)),
            max_high_unqueued_total_increase=max(0, int(args.max_high_unqueued_total_increase)),
            max_missing_runbook_link_total_increase=max(0, int(args.max_missing_runbook_link_total_increase)),
            max_high_queue_coverage_ratio_drop=max(0.0, float(args.max_high_queue_coverage_ratio_drop)),
            max_resolved_ratio_drop=max(0.0, float(args.max_resolved_ratio_drop)),
            max_p95_ack_latency_minutes_increase=max(0.0, float(args.max_p95_ack_latency_minutes_increase)),
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
                "min_incident_total": int(args.min_incident_total),
                "min_high_queue_coverage_ratio": float(args.min_high_queue_coverage_ratio),
                "min_resolved_ratio": float(args.min_resolved_ratio),
                "max_alert_miss_total": int(args.max_alert_miss_total),
                "max_high_unqueued_total": int(args.max_high_unqueued_total),
                "max_p95_ack_latency_minutes": float(args.max_p95_ack_latency_minutes),
                "max_missing_runbook_link_total": int(args.max_missing_runbook_link_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_incident_total_drop": int(args.max_incident_total_drop),
                "max_high_severity_total_drop": int(args.max_high_severity_total_drop),
                "max_alert_sent_total_drop": int(args.max_alert_sent_total_drop),
                "max_resolved_total_drop": int(args.max_resolved_total_drop),
                "max_alert_miss_total_increase": int(args.max_alert_miss_total_increase),
                "max_high_unqueued_total_increase": int(args.max_high_unqueued_total_increase),
                "max_missing_runbook_link_total_increase": int(args.max_missing_runbook_link_total_increase),
                "max_high_queue_coverage_ratio_drop": float(args.max_high_queue_coverage_ratio_drop),
                "max_resolved_ratio_drop": float(args.max_resolved_ratio_drop),
                "max_p95_ack_latency_minutes_increase": float(args.max_p95_ack_latency_minutes_increase),
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
    print(f"incident_total={_safe_int(summary.get('incident_total'), 0)}")
    print(f"alert_miss_total={_safe_int(summary.get('alert_miss_total'), 0)}")
    print(f"high_unqueued_total={_safe_int(summary.get('high_unqueued_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
