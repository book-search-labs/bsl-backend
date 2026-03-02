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


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate canary gate and optionally apply auto rollback")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--apply", action="store_true", help="Apply force-legacy override on gate failure")
    parser.add_argument("--trace-id", default=f"canary_trace_{int(time.time())}")
    parser.add_argument("--request-id", default=f"canary_req_{int(time.time())}")
    parser.add_argument("--source", default="chat_canary_gate_script")
    args = parser.parse_args()

    _bootstrap_pythonpath()

    from app.core.chat_graph.shadow_comparator import build_gate_payload
    from app.core.chat_graph.canary_controller import apply_auto_rollback, evaluate_canary_gate

    gate_payload = build_gate_payload(limit=max(1, args.limit))
    decision = evaluate_canary_gate(gate_payload)

    response = {
        "gate_payload": gate_payload,
        "decision": {
            "passed": decision.passed,
            "gate_status": decision.gate_status,
            "reason": decision.reason,
            "blocker_ratio": decision.blocker_ratio,
            "mismatch_ratio": decision.mismatch_ratio,
        },
        "rollback": None,
    }

    if args.apply:
        rollback = apply_auto_rollback(
            decision,
            trace_id=args.trace_id,
            request_id=args.request_id,
            source=args.source,
        )
        response["rollback"] = {
            "applied": rollback.applied,
            "mode": rollback.mode,
            "reason": rollback.reason,
            "cooldown_until": rollback.cooldown_until,
        }

    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
