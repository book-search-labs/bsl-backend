#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
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


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_missing_signature_increase: int,
    max_unique_signature_increase: int,
    max_signature_change_increase: int,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_missing = int(base_summary.get("missing_signature_count") or 0)
    cur_missing = int(current_summary.get("missing_signature_count") or 0)
    missing_increase = max(0, cur_missing - base_missing)
    if missing_increase > max(0, int(max_missing_signature_increase)):
        failures.append(
            "missing signature regression: "
            f"baseline={base_missing}, current={cur_missing}, allowed_increase={max(0, int(max_missing_signature_increase))}"
        )

    base_unique = int(base_summary.get("unique_signature_count") or 0)
    cur_unique = int(current_summary.get("unique_signature_count") or 0)
    unique_increase = max(0, cur_unique - base_unique)
    if unique_increase > max(0, int(max_unique_signature_increase)):
        failures.append(
            "unique signature regression: "
            f"baseline={base_unique}, current={cur_unique}, allowed_increase={max(0, int(max_unique_signature_increase))}"
        )

    base_change = int(base_summary.get("signature_change_count") or 0)
    cur_change = int(current_summary.get("signature_change_count") or 0)
    change_increase = max(0, cur_change - base_change)
    if change_increase > max(0, int(max_signature_change_increase)):
        failures.append(
            "signature change regression: "
            f"baseline={base_change}, current={cur_change}, allowed_increase={max(0, int(max_signature_change_increase))}"
        )
    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    summary = derived.get("summary") if isinstance(derived.get("summary"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat Immutable Bundle Guard Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- window_size: {int(summary.get('window_size') or 0)}")
    lines.append(f"- missing_signature_count: {int(summary.get('missing_signature_count') or 0)}")
    lines.append(f"- unique_signature_count: {int(summary.get('unique_signature_count') or 0)}")
    lines.append(f"- signature_change_count: {int(summary.get('signature_change_count') or 0)}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    if failures:
        lines.append("- failures:")
        for item in failures:
            lines.append(f"  - {item}")
    if baseline_failures:
        lines.append("- baseline_failures:")
        for item in baseline_failures:
            lines.append(f"  - {item}")
    if not failures and not baseline_failures:
        lines.append("- failures: none")
    return "\n".join(lines)


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
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--report-prefix", default="chat_immutable_bundle_guard")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-missing-signature-increase", type=int, default=0)
    parser.add_argument("--max-unique-signature-increase", type=int, default=0)
    parser.add_argument("--max-signature-change-increase", type=int, default=0)
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

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            summary,
            max_missing_signature_increase=max(0, int(args.max_missing_signature_increase)),
            max_unique_signature_increase=max(0, int(args.max_unique_signature_increase)),
            max_signature_change_increase=max(0, int(args.max_signature_change_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "reports_dir": str(reports_dir),
            "prefix": str(args.prefix),
            "limit": max(1, int(args.limit)),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": summary,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_unique_signatures": int(args.max_unique_signatures),
                "max_signature_changes": int(args.max_signature_changes),
                "allowed_change_actions": sorted(allowed_actions),
                "require_signature": bool(args.require_signature),
                "max_missing_signature_increase": int(args.max_missing_signature_increase),
                "max_unique_signature_increase": int(args.max_unique_signature_increase),
                "max_signature_change_increase": int(args.max_signature_change_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.report_prefix}_{stamp}.json"
    md_path = out_dir / f"{args.report_prefix}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if args.gate and not payload["gate"]["pass"]:
        for item in failures:
            print(f"[gate-failure] {item}")
        for item in baseline_failures:
            print(f"[baseline-failure] {item}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
