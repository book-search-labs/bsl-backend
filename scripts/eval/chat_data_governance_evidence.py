#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


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


def resolve_latest_report(reports_dir: Path, *, prefix: str) -> Path | None:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    if not rows:
        return None
    return rows[-1]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def evaluate_evidence(
    *,
    retention_gate_pass: bool,
    egress_gate_pass: bool,
    retention_event_total: int,
    egress_event_total: int,
    retention_overdue_total: int,
    retention_unapproved_exception_total: int,
    egress_violation_total: int,
    egress_unmasked_sensitive_total: int,
    retention_trace_coverage_ratio: float,
    egress_trace_coverage_ratio: float,
    egress_alert_coverage_ratio: float,
    min_trace_coverage_ratio: float,
    min_lifecycle_score: float,
    require_events: bool,
    missing_reports: list[str],
    require_reports: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    if require_reports and missing_reports:
        blockers.append(f"missing required reports: {', '.join(missing_reports)}")

    if not retention_gate_pass:
        blockers.append("retention_gate_failed")
    if not egress_gate_pass:
        blockers.append("egress_gate_failed")

    if require_events:
        if retention_event_total <= 0:
            blockers.append("retention_events_missing")
        if egress_event_total <= 0:
            blockers.append("egress_events_missing")

    trace_coverage_ratio = min(
        max(0.0, retention_trace_coverage_ratio),
        max(0.0, egress_trace_coverage_ratio),
    )
    if trace_coverage_ratio < max(0.0, float(min_trace_coverage_ratio)):
        blockers.append(
            f"trace coverage below threshold: {trace_coverage_ratio:.4f} < {float(min_trace_coverage_ratio):.4f}"
        )

    lifecycle_score = 100.0
    lifecycle_score -= min(40.0, float(max(0, retention_overdue_total)) * 5.0)
    lifecycle_score -= min(25.0, float(max(0, retention_unapproved_exception_total)) * 5.0)
    lifecycle_score -= min(40.0, float(max(0, egress_violation_total)) * 8.0)
    lifecycle_score -= min(25.0, float(max(0, egress_unmasked_sensitive_total)) * 10.0)
    lifecycle_score -= max(0.0, 10.0 * (1.0 - max(0.0, egress_alert_coverage_ratio)))
    lifecycle_score = max(0.0, min(100.0, lifecycle_score))

    if lifecycle_score < max(0.0, float(min_lifecycle_score)):
        blockers.append(f"lifecycle score below threshold: {lifecycle_score:.2f} < {float(min_lifecycle_score):.2f}")

    if retention_event_total < 10:
        warnings.append("retention event volume is low")
    if egress_event_total < 10:
        warnings.append("egress event volume is low")
    if egress_alert_coverage_ratio < 1.0:
        warnings.append("egress alert coverage is below 100%")

    if blockers:
        status = "HOLD"
        action = "hold"
    elif warnings:
        status = "WATCH"
        action = "hold"
    else:
        status = "READY"
        action = "promote"

    return {
        "status": status,
        "recommended_action": action,
        "blockers": blockers,
        "warnings": warnings,
        "lifecycle_score": lifecycle_score,
        "trace_coverage_ratio": trace_coverage_ratio,
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    decision = payload.get("decision") if isinstance(payload.get("decision"), Mapping) else {}
    signals = payload.get("signals") if isinstance(payload.get("signals"), Mapping) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Data Governance Evidence")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- status: {decision.get('status')}")
    lines.append(f"- recommended_action: {decision.get('recommended_action')}")
    lines.append(f"- lifecycle_score: {_safe_float(decision.get('lifecycle_score'), 0.0):.2f}")
    lines.append(f"- trace_coverage_ratio: {_safe_float(decision.get('trace_coverage_ratio'), 0.0):.4f}")
    lines.append("")
    lines.append("## Evidence")
    lines.append("")
    lines.append(f"- retention_report: {evidence.get('retention_report')}")
    lines.append(f"- egress_report: {evidence.get('egress_report')}")
    lines.append("")
    lines.append("## Signals")
    lines.append("")
    for key in (
        "retention_event_total",
        "egress_event_total",
        "retention_overdue_total",
        "retention_unapproved_exception_total",
        "egress_violation_total",
        "egress_unmasked_sensitive_total",
        "retention_trace_coverage_ratio",
        "egress_trace_coverage_ratio",
        "egress_alert_coverage_ratio",
    ):
        lines.append(f"- {key}: {signals.get(key)}")

    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    blockers = decision.get("blockers") if isinstance(decision.get("blockers"), list) else []
    if blockers:
        for item in blockers:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    warnings = decision.get("warnings") if isinstance(decision.get("warnings"), list) else []
    if warnings:
        for item in warnings:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build combined chat data governance evidence report.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--retention-prefix", default="chat_data_retention_guard")
    parser.add_argument("--egress-prefix", default="chat_egress_guardrails_gate")
    parser.add_argument("--min-trace-coverage-ratio", type=float, default=1.0)
    parser.add_argument("--min-lifecycle-score", type=float, default=80.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_data_governance_evidence")
    parser.add_argument("--require-reports", action="store_true")
    parser.add_argument("--require-events", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)

    retention_path = resolve_latest_report(reports_dir, prefix=str(args.retention_prefix))
    egress_path = resolve_latest_report(reports_dir, prefix=str(args.egress_prefix))

    missing_reports: list[str] = []
    if retention_path is None:
        missing_reports.append("retention")
    if egress_path is None:
        missing_reports.append("egress")

    retention_payload = load_json(retention_path) if retention_path else {}
    egress_payload = load_json(egress_path) if egress_path else {}

    retention_gate = retention_payload.get("gate") if isinstance(retention_payload.get("gate"), Mapping) else {}
    egress_gate = egress_payload.get("gate") if isinstance(egress_payload.get("gate"), Mapping) else {}
    retention_summary = retention_payload.get("summary") if isinstance(retention_payload.get("summary"), Mapping) else {}
    egress_summary = egress_payload.get("summary") if isinstance(egress_payload.get("summary"), Mapping) else {}

    decision = evaluate_evidence(
        retention_gate_pass=_safe_bool(retention_gate.get("pass"), False),
        egress_gate_pass=_safe_bool(egress_gate.get("pass"), False),
        retention_event_total=_safe_int(retention_summary.get("window_size"), 0),
        egress_event_total=_safe_int(egress_summary.get("window_size"), 0),
        retention_overdue_total=_safe_int(retention_summary.get("overdue_total"), 0),
        retention_unapproved_exception_total=_safe_int(retention_summary.get("unapproved_exception_total"), 0),
        egress_violation_total=_safe_int(egress_summary.get("violation_total"), 0),
        egress_unmasked_sensitive_total=_safe_int(egress_summary.get("unmasked_sensitive_total"), 0),
        retention_trace_coverage_ratio=_safe_float(retention_summary.get("trace_coverage_ratio"), 1.0),
        egress_trace_coverage_ratio=_safe_float(egress_summary.get("trace_coverage_ratio"), 1.0),
        egress_alert_coverage_ratio=_safe_float(egress_summary.get("alert_coverage_ratio"), 1.0),
        min_trace_coverage_ratio=max(0.0, float(args.min_trace_coverage_ratio)),
        min_lifecycle_score=max(0.0, float(args.min_lifecycle_score)),
        require_events=bool(args.require_events),
        missing_reports=missing_reports,
        require_reports=bool(args.require_reports),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "signals": {
            "retention_event_total": _safe_int(retention_summary.get("window_size"), 0),
            "egress_event_total": _safe_int(egress_summary.get("window_size"), 0),
            "retention_overdue_total": _safe_int(retention_summary.get("overdue_total"), 0),
            "retention_unapproved_exception_total": _safe_int(retention_summary.get("unapproved_exception_total"), 0),
            "egress_violation_total": _safe_int(egress_summary.get("violation_total"), 0),
            "egress_unmasked_sensitive_total": _safe_int(egress_summary.get("unmasked_sensitive_total"), 0),
            "retention_trace_coverage_ratio": _safe_float(retention_summary.get("trace_coverage_ratio"), 1.0),
            "egress_trace_coverage_ratio": _safe_float(egress_summary.get("trace_coverage_ratio"), 1.0),
            "egress_alert_coverage_ratio": _safe_float(egress_summary.get("alert_coverage_ratio"), 1.0),
        },
        "evidence": {
            "retention_report": str(retention_path) if retention_path else None,
            "egress_report": str(egress_path) if egress_path else None,
        },
        "missing_reports": missing_reports,
        "inputs": {
            "reports_dir": str(reports_dir),
            "retention_prefix": str(args.retention_prefix),
            "egress_prefix": str(args.egress_prefix),
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
    print(f"status={decision.get('status')}")
    print(f"lifecycle_score={_safe_float(decision.get('lifecycle_score'), 0.0):.2f}")

    failures: list[str] = []
    blockers = decision.get("blockers") if isinstance(decision.get("blockers"), list) else []
    if blockers:
        failures.extend([f"blocker: {item}" for item in blockers])
    if args.require_ready and str(decision.get("status") or "").upper() != "READY":
        failures.append(f"require_ready enabled but status={decision.get('status')}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
