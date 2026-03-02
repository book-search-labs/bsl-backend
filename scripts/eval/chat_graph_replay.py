#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
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


def _build_replay_id(run_id: str) -> str:
    seed = f"{run_id}:{int(time.time() * 1000)}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"replay_{digest}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic replay runner for chat graph runs")
    parser.add_argument("--run-id", help="Recorded graph run id")
    parser.add_argument("--request-id", help="Resolve run id from original request id")
    parser.add_argument("--trace-id", default=f"replay_trace_{int(time.time())}")
    parser.add_argument("--new-request-id", default=f"replay_req_{int(time.time())}")
    parser.add_argument("--replay-id", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    if not args.run_id and not args.request_id:
        parser.error("Either --run-id or --request-id is required")

    _bootstrap_pythonpath()

    from app.core.chat_graph.replay_store import (
        load_run,
        load_replay,
        resolve_run_id,
        response_diff,
        save_replay,
    )
    from app.core.chat_graph.runtime import run_chat_graph

    run_id = args.run_id or resolve_run_id(str(args.request_id))
    if not run_id:
        print(json.dumps({"status": "not_found", "reason": "RUN_NOT_FOUND"}, ensure_ascii=False))
        return 2

    run = load_run(run_id)
    if not isinstance(run, dict):
        print(json.dumps({"status": "not_found", "reason": "RUN_RECORD_MISSING", "run_id": run_id}, ensure_ascii=False))
        return 2

    request_payload = run.get("request_payload") if isinstance(run.get("request_payload"), dict) else None
    original_response = run.get("response") if isinstance(run.get("response"), dict) else None
    stub_response = run.get("stub_response") if isinstance(run.get("stub_response"), dict) else original_response

    if not isinstance(request_payload, dict):
        print(json.dumps({"status": "error", "reason": "INVALID_REQUEST_PAYLOAD", "run_id": run_id}, ensure_ascii=False))
        return 1
    if not isinstance(original_response, dict):
        print(json.dumps({"status": "error", "reason": "INVALID_ORIGINAL_RESPONSE", "run_id": run_id}, ensure_ascii=False))
        return 1
    if not isinstance(stub_response, dict):
        print(json.dumps({"status": "error", "reason": "INVALID_STUB_RESPONSE", "run_id": run_id}, ensure_ascii=False))
        return 1

    async def _stub_executor(_request, _trace_id, _request_id):
        return stub_response

    replay_result = asyncio.run(
        run_chat_graph(
            request_payload,
            args.trace_id,
            args.new_request_id,
            legacy_executor=_stub_executor,
            run_id=f"{run_id}:replay",
            record_run=False,
        )
    )

    diff = response_diff(original_response, replay_result.response)
    replay_id = args.replay_id.strip() or _build_replay_id(run_id)
    save_replay(
        replay_id,
        run_id=run_id,
        request_payload=request_payload,
        replay_response=replay_result.response,
        original_response=original_response,
        diff=diff,
        success=bool(diff.get("matched")),
    )

    replay_record = load_replay(replay_id) or {
        "replay_id": replay_id,
        "run_id": run_id,
        "status": "ok" if diff.get("matched") else "mismatch",
        "diff": diff,
    }

    if args.output_json.strip():
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(replay_record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(replay_record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
