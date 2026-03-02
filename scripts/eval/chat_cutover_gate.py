#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


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
    parser.add_argument("--trace-id", default=f"cutover_trace_{int(time.time())}")
    parser.add_argument("--request-id", default=f"cutover_req_{int(time.time())}")
    parser.add_argument("--source", default="chat_cutover_gate_script")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _bootstrap_pythonpath()
    from app.core.chat_graph.canary_controller import apply_auto_rollback, evaluate_canary_gate
    from app.core.chat_graph.perf_budget import build_perf_summary, evaluate_budget_gate, evaluate_cutover_decision
    from app.core.chat_graph.shadow_comparator import build_gate_payload

    parity_payload = build_gate_payload(limit=max(1, int(args.shadow_limit)))
    canary_decision = evaluate_canary_gate(parity_payload)
    perf_summary = build_perf_summary(limit=max(1, int(args.perf_limit)))
    budget_gate = evaluate_budget_gate(perf_summary)
    cutover = evaluate_cutover_decision(
        perf_summary,
        current_stage=int(args.current_stage),
        dwell_minutes=max(0, int(args.dwell_minutes)),
    )

    final_action = cutover.action
    final_reason = cutover.reason
    if not canary_decision.passed:
        final_action = "rollback"
        final_reason = f"canary_{canary_decision.reason}"

    rollback_result = None
    if args.apply_rollback and final_action == "rollback":
        rollback = apply_auto_rollback(
            canary_decision,
            trace_id=args.trace_id,
            request_id=args.request_id,
            source=args.source,
        )
        rollback_result = {
            "applied": rollback.applied,
            "mode": rollback.mode,
            "reason": rollback.reason,
            "cooldown_until": rollback.cooldown_until,
        }

    payload = {
        "stage": int(args.current_stage),
        "dwell_minutes": max(0, int(args.dwell_minutes)),
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
            "next_stage": cutover.next_stage if final_action != "rollback" else max(10, int(args.current_stage) // 2),
            "reason": final_reason,
        },
        "rollback": rollback_result,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
