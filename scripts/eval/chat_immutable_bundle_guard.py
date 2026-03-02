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


def resolve_cycle_reports(reports_dir: Path, *, prefix: str, limit: int) -> list[Path]:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    return rows[-max(1, int(limit)) :]


def build_bundle_summary(paths: list[Path]) -> dict[str, Any]:
    unique_signatures: dict[str, int] = {}
    signature_changes: list[dict[str, Any]] = []
    missing_signature_count = 0
    cycles: list[dict[str, Any]] = []
    prev_signature = ""

    for path in paths:
        payload = load_json(path)
        release = payload.get("release_profile") if isinstance(payload.get("release_profile"), Mapping) else {}
        decision = payload.get("release_train") if isinstance(payload.get("release_train"), Mapping) else {}
        decision_row = decision.get("decision") if isinstance(decision.get("decision"), Mapping) else {}
        action = str(decision_row.get("action") or "unknown")
        signature = str(release.get("release_signature") or "").strip()
        generated_at = str(payload.get("generated_at") or "")
        if not signature:
            missing_signature_count += 1
            signature = "missing"

        unique_signatures[signature] = unique_signatures.get(signature, 0) + 1
        if prev_signature and signature != prev_signature:
            signature_changes.append(
                {
                    "from_signature": prev_signature,
                    "to_signature": signature,
                    "action": action,
                    "generated_at": generated_at,
                    "path": str(path),
                }
            )
        prev_signature = signature
        cycles.append(
            {
                "path": str(path),
                "generated_at": generated_at,
                "action": action,
                "release_signature": signature,
                "model_version": str(release.get("model_version") or ""),
                "prompt_version": str(release.get("prompt_version") or ""),
                "policy_version": str(release.get("policy_version") or ""),
            }
        )

    return {
        "window_size": len(paths),
        "missing_signature_count": missing_signature_count,
        "unique_signature_count": len(unique_signatures),
        "unique_signatures": unique_signatures,
        "signature_change_count": len(signature_changes),
        "signature_changes": signature_changes[-20:],
        "cycles": cycles[-20:],
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_unique_signatures: int,
    max_signature_changes: int,
    allowed_change_actions: set[str],
    require_signature: bool,
) -> list[str]:
    failures: list[str] = []
    window_size = int(summary.get("window_size") or 0)
    missing_signature_count = int(summary.get("missing_signature_count") or 0)
    unique_signature_count = int(summary.get("unique_signature_count") or 0)
    signature_change_count = int(summary.get("signature_change_count") or 0)

    if window_size < max(0, int(min_window)):
        failures.append(f"insufficient cycle samples: window_size={window_size} < min_window={min_window}")
    if require_signature and missing_signature_count > 0:
        failures.append(f"missing release_signature observed: count={missing_signature_count}")
    if unique_signature_count > max(0, int(max_unique_signatures)):
        failures.append(
            f"unique release signatures exceeded: {unique_signature_count} > {int(max_unique_signatures)}"
        )
    if signature_change_count > max(0, int(max_signature_changes)):
        failures.append(
            f"release signature changes exceeded: {signature_change_count} > {int(max_signature_changes)}"
        )

    changes = summary.get("signature_changes") if isinstance(summary.get("signature_changes"), list) else []
    for row in changes:
        if not isinstance(row, Mapping):
            continue
        action = str(row.get("action") or "unknown").strip().lower()
        if action not in allowed_change_actions:
            failures.append(
                "signature change detected on disallowed action: "
                f"action={action} from={row.get('from_signature')} to={row.get('to_signature')}"
            )
    return failures


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check immutable release bundle drift from chat liveops cycle reports.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_liveops_cycle")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-window", type=int, default=3)
    parser.add_argument("--max-unique-signatures", type=int, default=2)
    parser.add_argument("--max-signature-changes", type=int, default=2)
    parser.add_argument("--allowed-change-actions", default="promote,rollback")
    parser.add_argument("--require-signature", action="store_true")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)
    paths = resolve_cycle_reports(reports_dir, prefix=str(args.prefix), limit=max(1, int(args.limit)))
    summary = build_bundle_summary(paths)
    allowed_actions = {item.strip().lower() for item in str(args.allowed_change_actions).split(",") if item.strip()}
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_unique_signatures=max(0, int(args.max_unique_signatures)),
        max_signature_changes=max(0, int(args.max_signature_changes)),
        allowed_change_actions=allowed_actions,
        require_signature=bool(args.require_signature),
    )

    payload = {
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_unique_signatures": int(args.max_unique_signatures),
                "max_signature_changes": int(args.max_signature_changes),
                "allowed_change_actions": sorted(allowed_actions),
                "require_signature": bool(args.require_signature),
            },
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
