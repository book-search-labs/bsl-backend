#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


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


def resolve_cycle_reports(reports_dir: Path, *, prefix: str, limit: int) -> list[Path]:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    return rows[-max(1, int(limit)) :]


def build_summary(paths: list[Path]) -> dict[str, Any]:
    total = 0
    pass_total = 0
    action_counts: dict[str, int] = {}
    failure_count = 0
    release_signatures: dict[str, int] = {}
    samples: list[dict[str, Any]] = []

    for path in paths:
        payload = load_json(path)
        total += 1
        failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
        if not failures:
            pass_total += 1
        else:
            failure_count += 1
        decision = payload.get("release_train") if isinstance(payload.get("release_train"), Mapping) else {}
        decision_row = decision.get("decision") if isinstance(decision.get("decision"), Mapping) else {}
        action = str(decision_row.get("action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
        release = payload.get("release_profile") if isinstance(payload.get("release_profile"), Mapping) else {}
        signature = str(release.get("release_signature") or "unknown")
        release_signatures[signature] = release_signatures.get(signature, 0) + 1
        samples.append(
            {
                "path": str(path),
                "generated_at": str(payload.get("generated_at") or ""),
                "action": action,
                "pass": len(failures) == 0,
                "failure_count": len(failures),
                "release_signature": signature,
            }
        )

    return {
        "window_size": total,
        "pass_total": pass_total,
        "pass_ratio": 0.0 if total == 0 else float(pass_total) / float(total),
        "failure_total": failure_count,
        "action_counts": action_counts,
        "release_signatures": release_signatures,
        "samples": samples[-20:],
    }


def evaluate_gate(summary: Mapping[str, Any], *, min_window: int, min_pass_ratio: float, deny_actions: set[str]) -> list[str]:
    failures: list[str] = []
    window_size = int(summary.get("window_size") or 0)
    pass_ratio = float(summary.get("pass_ratio") or 0.0)
    if window_size < max(0, int(min_window)):
        failures.append(f"insufficient liveops samples: window_size={window_size} < min_window={min_window}")
    if pass_ratio < max(0.0, float(min_pass_ratio)):
        failures.append(f"liveops pass ratio below threshold: {pass_ratio:.4f} < {float(min_pass_ratio):.4f}")
    action_counts = summary.get("action_counts") if isinstance(summary.get("action_counts"), Mapping) else {}
    for action in deny_actions:
        count = int(action_counts.get(action) or 0)
        if count > 0:
            failures.append(f"denied action observed: {action} count={count}")
    return failures


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize recent chat liveops cycle reports and evaluate gate.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_liveops_cycle")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-window", type=int, default=3)
    parser.add_argument("--min-pass-ratio", type=float, default=0.8)
    parser.add_argument("--deny-actions", default="rollback")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)
    paths = resolve_cycle_reports(reports_dir, prefix=str(args.prefix), limit=max(1, int(args.limit)))
    summary = build_summary(paths)
    deny_actions = {item.strip() for item in str(args.deny_actions).split(",") if item.strip()}
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_pass_ratio=max(0.0, float(args.min_pass_ratio)),
        deny_actions=deny_actions,
    )
    payload = {
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_pass_ratio": float(args.min_pass_ratio),
                "deny_actions": sorted(deny_actions),
            },
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
