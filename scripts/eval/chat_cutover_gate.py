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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat cutover promotion gate using parity + perf budgets.")
    parser.add_argument("--current-stage", type=int, default=10)
    parser.add_argument("--dwell-minutes", type=int, default=0)
    parser.add_argument("--shadow-limit", type=int, default=200)
    parser.add_argument("--perf-limit", type=int, default=500)
    parser.add_argument("--apply-rollback", action="store_true")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--require-promote", action="store_true")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_cutover_gate")
    parser.add_argument("--trace-id", default=f"cutover_trace_{int(time.time())}")
    parser.add_argument("--request-id", default=f"cutover_req_{int(time.time())}")
    parser.add_argument("--source", default="chat_cutover_gate_script")
    return parser.parse_args()


def evaluate_cutover(
    *,
    current_stage: int,
    dwell_minutes: int,
    shadow_limit: int,
    perf_limit: int,
    apply_rollback: bool,
    trace_id: str,
    request_id: str,
    source: str,
) -> dict[str, Any]:
    _bootstrap_pythonpath()
    from app.core.chat_graph.canary_controller import apply_auto_rollback, evaluate_canary_gate
    from app.core.chat_graph.perf_budget import build_perf_summary, evaluate_budget_gate, evaluate_cutover_decision
    from app.core.chat_graph.shadow_comparator import build_gate_payload

    parity_payload = build_gate_payload(limit=max(1, int(shadow_limit)))
    canary_decision = evaluate_canary_gate(parity_payload)
    perf_summary = build_perf_summary(limit=max(1, int(perf_limit)))
    budget_gate = evaluate_budget_gate(perf_summary)
    cutover = evaluate_cutover_decision(
        perf_summary,
        current_stage=int(current_stage),
        dwell_minutes=max(0, int(dwell_minutes)),
    )

    final_action = cutover.action
    final_reason = cutover.reason
    if not canary_decision.passed:
        final_action = "rollback"
        final_reason = f"canary_{canary_decision.reason}"

    rollback_result = None
    if apply_rollback and final_action == "rollback":
        rollback = apply_auto_rollback(
            canary_decision,
            trace_id=trace_id,
            request_id=request_id,
            source=source,
        )
        rollback_result = {
            "applied": rollback.applied,
            "mode": rollback.mode,
            "reason": rollback.reason,
            "cooldown_until": rollback.cooldown_until,
        }

    payload = {
        "stage": int(current_stage),
        "dwell_minutes": max(0, int(dwell_minutes)),
        "parity_gate": {
            "passed": canary_decision.passed,
            "gate_status": canary_decision.gate_status,
            "reason": canary_decision.reason,
            "blocker_ratio": canary_decision.blocker_ratio,
            "mismatch_ratio": canary_decision.mismatch_ratio,
        },
        "perf_gate": {
            "passed": budget_gate.passed,
            "failures": budget_gate.failures,
            "summary": perf_summary,
        },
        "cutover": {
            "action": final_action,
            "next_stage": cutover.next_stage if final_action != "rollback" else max(10, int(current_stage) // 2),
            "reason": final_reason,
        },
        "rollback": rollback_result,
    }
    return payload


def evaluate_gate(derived: Mapping[str, Any], *, require_promote: bool) -> list[str]:
    failures: list[str] = []
    parity_gate = derived.get("parity_gate") if isinstance(derived.get("parity_gate"), Mapping) else {}
    perf_gate = derived.get("perf_gate") if isinstance(derived.get("perf_gate"), Mapping) else {}
    cutover = derived.get("cutover") if isinstance(derived.get("cutover"), Mapping) else {}

    if not bool(parity_gate.get("passed")):
        failures.append(f"parity gate failed: reason={str(parity_gate.get('reason') or 'unknown')}")
    if not bool(perf_gate.get("passed")):
        perf_failures = perf_gate.get("failures") if isinstance(perf_gate.get("failures"), list) else []
        if perf_failures:
            failures.append(f"perf gate failed: {str(perf_failures[0])}")
        else:
            failures.append("perf gate failed")

    action = str(cutover.get("action") or "")
    if action == "rollback":
        failures.append(f"cutover action=rollback: reason={str(cutover.get('reason') or 'unknown')}")
    if require_promote and action != "promote":
        failures.append(f"cutover promote required but action={action or 'unknown'}")
    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    parity_gate = derived.get("parity_gate") if isinstance(derived.get("parity_gate"), Mapping) else {}
    perf_gate = derived.get("perf_gate") if isinstance(derived.get("perf_gate"), Mapping) else {}
    cutover = derived.get("cutover") if isinstance(derived.get("cutover"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Cutover Gate Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- stage: {derived.get('stage')}")
    lines.append(f"- dwell_minutes: {derived.get('dwell_minutes')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- parity_passed: {str(bool(parity_gate.get('passed'))).lower()}")
    lines.append(f"- perf_passed: {str(bool(perf_gate.get('passed'))).lower()}")
    lines.append(
        f"- cutover_action: {cutover.get('action')} (next_stage={int(cutover.get('next_stage') or 0)}, reason={cutover.get('reason')})"
    )
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


def main() -> int:
    args = _parse_args()
    derived = evaluate_cutover(
        current_stage=int(args.current_stage),
        dwell_minutes=max(0, int(args.dwell_minutes)),
        shadow_limit=max(1, int(args.shadow_limit)),
        perf_limit=max(1, int(args.perf_limit)),
        apply_rollback=bool(args.apply_rollback),
        trace_id=str(args.trace_id),
        request_id=str(args.request_id),
        source=str(args.source),
    )
    failures = evaluate_gate(derived, require_promote=bool(args.require_promote))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "current_stage": int(args.current_stage),
            "dwell_minutes": max(0, int(args.dwell_minutes)),
            "shadow_limit": max(1, int(args.shadow_limit)),
            "perf_limit": max(1, int(args.perf_limit)),
            "apply_rollback": bool(args.apply_rollback),
        },
        "derived": derived,
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
