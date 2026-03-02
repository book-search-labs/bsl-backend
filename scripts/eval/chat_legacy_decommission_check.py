#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bootstrap_pythonpath() -> None:
    root = _project_root()
    query_service = root / "services" / "query-service"
    if str(query_service) not in sys.path:
        sys.path.insert(0, str(query_service))


def _parse_allow_reasons(raw: str) -> set[str]:
    return {item.strip() for item in str(raw).split(",") if item.strip()}


def _int_value(payload: Mapping[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(payload.get(key, default) or default)
    except Exception:
        return default


def _float_value(payload: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(payload.get(key, default) or default)
    except Exception:
        return default


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_legacy_count: int,
    max_legacy_ratio: float,
    allow_legacy_reasons: set[str],
) -> list[str]:
    failures: list[str] = []
    window_size = _int_value(summary, "window_size", 0)
    legacy_count = _int_value(summary, "legacy_count", 0)
    legacy_ratio = _float_value(summary, "legacy_ratio", 0.0)
    reason_counts_raw = summary.get("legacy_reason_counts")
    reason_counts: dict[str, int] = {}
    if isinstance(reason_counts_raw, Mapping):
        for key, value in reason_counts_raw.items():
            reason_counts[str(key)] = int(value or 0)

    if window_size < max(0, int(min_window)):
        failures.append(f"insufficient routing samples: window_size={window_size} < min_window={min_window}")
    if legacy_count > max(0, int(max_legacy_count)):
        failures.append(f"legacy count exceeded: {legacy_count} > {max_legacy_count}")
    if legacy_ratio > max(0.0, float(max_legacy_ratio)):
        failures.append(f"legacy ratio exceeded: {legacy_ratio:.4f} > {max_legacy_ratio:.4f}")

    if allow_legacy_reasons:
        disallowed = {
            reason: count for reason, count in reason_counts.items() if int(count) > 0 and reason not in allow_legacy_reasons
        }
        if disallowed:
            failures.append(f"disallowed legacy reasons detected: {json.dumps(disallowed, ensure_ascii=False)}")

    return failures


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check chat routing audit window for legacy decommission compliance.")
    parser.add_argument("--limit", type=int, default=500, help="Recent routing audit rows to inspect")
    parser.add_argument("--min-window", type=int, default=20, help="Minimum routing samples required")
    parser.add_argument("--max-legacy-count", type=int, default=0, help="Maximum allowed legacy route count in window")
    parser.add_argument("--max-legacy-ratio", type=float, default=0.0, help="Maximum allowed legacy route ratio in window")
    parser.add_argument(
        "--allow-legacy-reasons",
        default="",
        help="Comma-separated allowlist for legacy reasons (optional)",
    )
    parser.add_argument("--gate", action="store_true", help="Exit non-zero when gate fails")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _bootstrap_pythonpath()
    from app.core.chat_graph.feature_router import build_legacy_mode_summary

    summary = build_legacy_mode_summary(limit=max(1, int(args.limit)))
    allow_legacy_reasons = _parse_allow_reasons(args.allow_legacy_reasons)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_legacy_count=max(0, int(args.max_legacy_count)),
        max_legacy_ratio=max(0.0, float(args.max_legacy_ratio)),
        allow_legacy_reasons=allow_legacy_reasons,
    )
    payload = {
        "thresholds": {
            "min_window": max(0, int(args.min_window)),
            "max_legacy_count": max(0, int(args.max_legacy_count)),
            "max_legacy_ratio": max(0.0, float(args.max_legacy_ratio)),
            "allow_legacy_reasons": sorted(allow_legacy_reasons),
        },
        "summary": summary,
        "gate": {
            "passed": len(failures) == 0,
            "failures": failures,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.gate and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
