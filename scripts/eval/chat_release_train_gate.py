#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bootstrap_pythonpath() -> None:
    root = _project_root()
    query_service = root / "services" / "query-service"
    if str(query_service) not in sys.path:
        sys.path.insert(0, str(query_service))


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def resolve_launch_gate_report(path: str, *, reports_dir: str, prefix: str) -> Path:
    if str(path).strip():
        resolved = Path(path)
        if not resolved.exists():
            raise RuntimeError(f"launch gate report not found: {resolved}")
        return resolved

    base = Path(reports_dir)
    if not base.exists():
        raise RuntimeError(f"reports dir not found: {base}")
    candidates = sorted(base.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    if not candidates:
        raise RuntimeError(f"no launch gate report found in {base} with prefix={prefix}")
    return candidates[-1]


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


def decide_release_train(
    report: Mapping[str, Any],
    *,
    current_stage: int,
    dwell_minutes: int,
) -> dict[str, Any]:
    _bootstrap_pythonpath()
    from app.core.chat_graph.perf_budget import evaluate_cutover_decision

    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    canary = derived.get("canary") if isinstance(derived.get("canary"), Mapping) else {}
    perf = derived.get("perf") if isinstance(derived.get("perf"), Mapping) else {}

    launch_pass = _safe_bool(gate.get("pass"), False)
    canary_pass = _safe_bool(canary.get("passed"), False)
    cutover = evaluate_cutover_decision(
        perf,
        current_stage=int(current_stage),
        dwell_minutes=max(0, int(dwell_minutes)),
    )

    action = cutover.action
    reason = cutover.reason
    next_stage = int(cutover.next_stage)

    if not launch_pass:
        action = "rollback"
        reason = "launch_gate_failed"
        next_stage = max(10, int(current_stage) // 2)
    elif not canary_pass:
        action = "rollback"
        reason = f"canary_{str(canary.get('reason') or 'failed')}"
        next_stage = max(10, int(current_stage) // 2)

    return {
        "action": action,
        "reason": reason,
        "next_stage": next_stage,
        "cutover": {
            "action": cutover.action,
            "reason": cutover.reason,
            "next_stage": int(cutover.next_stage),
        },
        "launch_gate_passed": launch_pass,
        "canary_passed": canary_pass,
        "canary_reason": str(canary.get("reason") or ""),
        "canary_gate_status": str(canary.get("gate_status") or ""),
    }


def evaluate_gate(decision: Mapping[str, Any], *, require_promote: bool) -> list[str]:
    failures: list[str] = []
    action = str(decision.get("action") or "")
    reason = str(decision.get("reason") or "")
    if action == "rollback":
        failures.append(f"release action=rollback: reason={reason or 'unknown'}")
    if require_promote and action != "promote":
        failures.append(f"release promote required but action={action or 'unknown'}")
    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    decision = report.get("decision") if isinstance(report.get("decision"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Release Train Gate Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- report_path: {report.get('report_path')}")
    lines.append(f"- stage: {report.get('stage')}")
    lines.append(f"- dwell_minutes: {report.get('dwell_minutes')}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- action: {decision.get('action')}")
    lines.append(f"- reason: {decision.get('reason')}")
    lines.append(f"- next_stage: {decision.get('next_stage')}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    if failures:
        lines.append("- failures:")
        for item in failures:
            lines.append(f"  - {item}")
    else:
        lines.append("- failures: none")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decide chat release-train promotion using launch gate report + cutover policy.")
    parser.add_argument("--launch-gate-report", default="")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--report-prefix", default="chat_production_launch_gate")
    parser.add_argument("--current-stage", type=int, default=10)
    parser.add_argument("--dwell-minutes", type=int, default=0)
    parser.add_argument("--apply-rollback", action="store_true")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--require-promote", action="store_true")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_release_train_gate")
    parser.add_argument("--trace-id", default=f"release_train_trace_{int(time.time())}")
    parser.add_argument("--request-id", default=f"release_train_req_{int(time.time())}")
    parser.add_argument("--source", default="chat_release_train_gate_script")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _bootstrap_pythonpath()

    from app.core.chat_graph.canary_controller import CanaryGateDecision, apply_auto_rollback

    report_path = resolve_launch_gate_report(
        args.launch_gate_report,
        reports_dir=args.reports_dir,
        prefix=args.report_prefix,
    )
    report = load_json(report_path)
    decision = decide_release_train(
        report,
        current_stage=int(args.current_stage),
        dwell_minutes=max(0, int(args.dwell_minutes)),
    )

    rollback = None
    if args.apply_rollback and str(decision.get("action")) == "rollback":
        derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
        canary = derived.get("canary") if isinstance(derived.get("canary"), Mapping) else {}
        rollback_input = CanaryGateDecision(
            passed=False,
            gate_status=str(canary.get("gate_status") or "BLOCK"),
            reason=str(decision.get("reason") or "launch_gate_failed"),
            blocker_ratio=_safe_float(canary.get("blocker_ratio"), 0.0),
            mismatch_ratio=_safe_float(canary.get("mismatch_ratio"), 0.0),
        )
        result = apply_auto_rollback(
            rollback_input,
            trace_id=str(args.trace_id),
            request_id=str(args.request_id),
            source=str(args.source),
        )
        rollback = {
            "applied": result.applied,
            "mode": result.mode,
            "reason": result.reason,
            "cooldown_until": result.cooldown_until,
        }

    failures = evaluate_gate(decision, require_promote=bool(args.require_promote))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "reports_dir": str(args.reports_dir),
            "report_prefix": str(args.report_prefix),
            "launch_gate_report": str(args.launch_gate_report) if args.launch_gate_report else None,
        },
        "report_path": str(report_path),
        "report_generated_at": str(report.get("generated_at") or ""),
        "release_profile": report.get("release_profile"),
        "stage": int(args.current_stage),
        "dwell_minutes": max(0, int(args.dwell_minutes)),
        "decision": decision,
        "rollback": rollback,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {"require_promote": bool(args.require_promote)},
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")
    if args.gate and not report["gate"]["pass"]:
        for item in failures:
            print(f"[gate-failure] {item}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
