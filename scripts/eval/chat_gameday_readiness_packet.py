#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
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


def evaluate_packet(
    *,
    readiness_score: float,
    readiness_gate_pass: bool,
    readiness_tier: str,
    trend_week_avg: float,
    trend_gate_pass: bool,
    dr_open_total: int,
    min_readiness_score: float,
    min_week_avg: float,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    if readiness_score < min_readiness_score:
        blockers.append(f"readiness_score_below_threshold({readiness_score:.2f} < {min_readiness_score:.2f})")
    if not readiness_gate_pass:
        blockers.append("readiness_gate_failed")
    if trend_week_avg < min_week_avg:
        warnings.append(f"readiness_trend_weekly_low({trend_week_avg:.2f} < {min_week_avg:.2f})")
    if not trend_gate_pass:
        warnings.append("readiness_trend_gate_failed")
    if int(dr_open_total) > 0:
        blockers.append(f"open_drill_exists({int(dr_open_total)})")
    if str(readiness_tier).upper() == "WATCH":
        warnings.append("readiness_tier_watch")

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
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    decision = payload.get("decision") if isinstance(payload.get("decision"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Gameday Readiness Packet")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- status: {decision.get('status')}")
    lines.append(f"- recommended_action: {decision.get('recommended_action')}")
    lines.append("")
    lines.append("## Evidence")
    lines.append("")
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), Mapping) else {}
    for key in ("readiness_report", "trend_report", "dr_report", "drillpack_report", "feedback_report"):
        lines.append(f"- {key}: {evidence.get(key)}")
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
    parser = argparse.ArgumentParser(description="Build combined gameday readiness packet from latest chat liveops reports.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--readiness-prefix", default="chat_readiness_score")
    parser.add_argument("--trend-prefix", default="chat_readiness_trend")
    parser.add_argument("--dr-prefix", default="chat_dr_drill_report")
    parser.add_argument("--drillpack-prefix", default="chat_gameday_drillpack")
    parser.add_argument("--feedback-prefix", default="chat_incident_feedback_binding")
    parser.add_argument("--min-readiness-score", type=float, default=80.0)
    parser.add_argument("--min-week-avg", type=float, default=80.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_gameday_readiness_packet")
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)

    readiness_path = resolve_latest_report(reports_dir, prefix=str(args.readiness_prefix))
    trend_path = resolve_latest_report(reports_dir, prefix=str(args.trend_prefix))
    dr_path = resolve_latest_report(reports_dir, prefix=str(args.dr_prefix))
    drillpack_path = resolve_latest_report(reports_dir, prefix=str(args.drillpack_prefix))
    feedback_path = resolve_latest_report(reports_dir, prefix=str(args.feedback_prefix))

    missing: list[str] = []
    if readiness_path is None:
        missing.append("readiness")
    if trend_path is None:
        missing.append("trend")
    if dr_path is None:
        missing.append("dr")
    if drillpack_path is None:
        missing.append("drillpack")
    if feedback_path is None:
        missing.append("feedback")

    readiness_payload = load_json(readiness_path) if readiness_path else {}
    trend_payload = load_json(trend_path) if trend_path else {}
    dr_payload = load_json(dr_path) if dr_path else {}
    drillpack_payload = load_json(drillpack_path) if drillpack_path else {}
    feedback_payload = load_json(feedback_path) if feedback_path else {}

    readiness = readiness_payload.get("readiness") if isinstance(readiness_payload.get("readiness"), Mapping) else {}
    readiness_gate = readiness_payload.get("gate") if isinstance(readiness_payload.get("gate"), Mapping) else {}
    trend_summary = trend_payload.get("summary") if isinstance(trend_payload.get("summary"), Mapping) else {}
    trend_gate = trend_payload.get("gate") if isinstance(trend_payload.get("gate"), Mapping) else {}
    dr_summary = dr_payload.get("summary") if isinstance(dr_payload.get("summary"), Mapping) else {}
    feedback_summary = feedback_payload.get("summary") if isinstance(feedback_payload.get("summary"), Mapping) else {}

    decision = evaluate_packet(
        readiness_score=_safe_float(readiness.get("total_score"), 0.0),
        readiness_gate_pass=_safe_bool(readiness_gate.get("pass"), False),
        readiness_tier=str(readiness.get("tier") or ""),
        trend_week_avg=_safe_float(trend_summary.get("current_week_avg"), 0.0),
        trend_gate_pass=_safe_bool(trend_gate.get("pass"), False),
        dr_open_total=int(dr_summary.get("open_drill_total") or 0),
        min_readiness_score=max(0.0, float(args.min_readiness_score)),
        min_week_avg=max(0.0, float(args.min_week_avg)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "evidence": {
            "readiness_report": str(readiness_path) if readiness_path else None,
            "trend_report": str(trend_path) if trend_path else None,
            "dr_report": str(dr_path) if dr_path else None,
            "drillpack_report": str(drillpack_path) if drillpack_path else None,
            "feedback_report": str(feedback_path) if feedback_path else None,
        },
        "signals": {
            "readiness_score": _safe_float(readiness.get("total_score"), 0.0),
            "readiness_tier": str(readiness.get("tier") or ""),
            "trend_week_avg": _safe_float(trend_summary.get("current_week_avg"), 0.0),
            "dr_open_total": int(dr_summary.get("open_drill_total") or 0),
            "drillpack_scenario_total": len(drillpack_payload.get("scenarios") or [])
            if isinstance(drillpack_payload.get("scenarios"), list)
            else 0,
            "feedback_bound_category_total": int(feedback_summary.get("bound_category_total") or 0),
        },
        "missing_reports": missing,
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
    print(f"recommended_action={decision.get('recommended_action')}")

    failures: list[str] = []
    if args.require_all and missing:
        failures.append(f"missing required reports: {', '.join(missing)}")
    blockers = decision.get("blockers") if isinstance(decision.get("blockers"), list) else []
    if blockers:
        failures.extend([f"blocker: {item}" for item in blockers])
    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
