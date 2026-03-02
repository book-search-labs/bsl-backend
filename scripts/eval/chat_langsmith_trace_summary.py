#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bootstrap_pythonpath() -> None:
    root = _project_root()
    query_service = root / "services" / "query-service"
    if str(query_service) not in sys.path:
        sys.path.insert(0, str(query_service))


def main() -> int:
    parser = argparse.ArgumentParser(description="Print LangSmith trace audit summary")
    parser.add_argument("--session-id", default="", help="optional session id for per-session view")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    _bootstrap_pythonpath()
    from app.core.cache import get_cache

    cache = get_cache()
    if args.session_id:
        key = f"chat:graph:langsmith-audit:{args.session_id}"
    else:
        key = "chat:graph:langsmith-audit:global"

    payload = cache.get_json(key)
    events = []
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        events = [item for item in payload.get("events", []) if isinstance(item, dict)]
    sliced = events[-max(1, args.limit) :]

    by_status: dict[str, int] = {}
    by_event: dict[str, int] = {}
    for row in sliced:
        status = str(row.get("status") or "unknown")
        event_type = str(row.get("event_type") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_event[event_type] = by_event.get(event_type, 0) + 1

    summary = {
        "key": key,
        "window_size": len(sliced),
        "by_status": by_status,
        "by_event": by_event,
        "samples": sliced[-20:],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
