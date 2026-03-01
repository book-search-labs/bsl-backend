#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap_query_service_path() -> None:
    root = Path(__file__).resolve().parents[2]
    query_service_root = root / "services" / "query-service"
    path_value = str(query_service_root)
    if path_value not in sys.path:
        sys.path.insert(0, path_value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge chat retention tables with configured TTL policy.")
    parser.add_argument("--dry-run", action="store_true", help="Only count expired rows; do not delete.")
    parser.add_argument("--trace-id", default=None)
    parser.add_argument("--request-id", default=None)
    args = parser.parse_args()

    _bootstrap_query_service_path()
    from app.core.chat_state_store import run_retention_cleanup

    result = run_retention_cleanup(
        dry_run=bool(args.dry_run),
        trace_id=args.trace_id,
        request_id=args.request_id,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))

    if not bool(result.get("enabled")):
        return 2
    if str(result.get("status") or "ok").lower() != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
