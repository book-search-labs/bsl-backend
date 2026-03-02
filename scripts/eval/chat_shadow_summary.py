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
    parser = argparse.ArgumentParser(description="Print shadow comparator summary")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    _bootstrap_pythonpath()
    from app.core.chat_graph.shadow_comparator import build_gate_payload

    payload = build_gate_payload(limit=max(1, args.limit))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
