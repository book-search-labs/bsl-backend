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


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_pass_ratio_drop: float,
    max_failure_total_increase: int,
    max_rollback_count_increase: int,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_pass_ratio = float(base_summary.get("pass_ratio") or 0.0)
    cur_pass_ratio = float(current_summary.get("pass_ratio") or 0.0)
    pass_ratio_drop = max(0.0, base_pass_ratio - cur_pass_ratio)
    if pass_ratio_drop > max(0.0, float(max_pass_ratio_drop)):
        failures.append(
            "pass ratio regression: "
            f"baseline={base_pass_ratio:.6f}, current={cur_pass_ratio:.6f}, allowed_drop={float(max_pass_ratio_drop):.6f}"
        )

    base_failure_total = int(base_summary.get("failure_total") or 0)
    cur_failure_total = int(current_summary.get("failure_total") or 0)
    failure_total_increase = max(0, cur_failure_total - base_failure_total)
    if failure_total_increase > max(0, int(max_failure_total_increase)):
        failures.append(
            "failure_total regression: "
            f"baseline={base_failure_total}, current={cur_failure_total}, allowed_increase={max(0, int(max_failure_total_increase))}"
        )

    base_actions = base_summary.get("action_counts") if isinstance(base_summary.get("action_counts"), Mapping) else {}
    cur_actions = current_summary.get("action_counts") if isinstance(current_summary.get("action_counts"), Mapping) else {}
    base_rollback = int(base_actions.get("rollback") or 0)
    cur_rollback = int(cur_actions.get("rollback") or 0)
    rollback_increase = max(0, cur_rollback - base_rollback)
    if rollback_increase > max(0, int(max_rollback_count_increase)):
        failures.append(
            "rollback action regression: "
            f"baseline={base_rollback}, current={cur_rollback}, allowed_increase={max(0, int(max_rollback_count_increase))}"
        )
    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    summary = derived.get("summary") if isinstance(derived.get("summary"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat LiveOps Summary Gate Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- window_size: {int(summary.get('window_size') or 0)}")
    lines.append(f"- pass_total: {int(summary.get('pass_total') or 0)}")
    lines.append(f"- pass_ratio: {float(summary.get('pass_ratio') or 0.0):.6f}")
    lines.append(f"- failure_total: {int(summary.get('failure_total') or 0)}")
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
    parser = argparse.ArgumentParser(description="Summarize recent chat liveops cycle reports and evaluate gate.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_liveops_cycle")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-window", type=int, default=3)
    parser.add_argument("--min-pass-ratio", type=float, default=0.8)
    parser.add_argument("--deny-actions", default="rollback")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--report-prefix", default="chat_liveops_summary")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-pass-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-failure-total-increase", type=int, default=1)
    parser.add_argument("--max-rollback-count-increase", type=int, default=0)
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

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            summary,
            max_pass_ratio_drop=max(0.0, float(args.max_pass_ratio_drop)),
            max_failure_total_increase=max(0, int(args.max_failure_total_increase)),
            max_rollback_count_increase=max(0, int(args.max_rollback_count_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "reports_dir": str(reports_dir),
            "prefix": str(args.prefix),
            "limit": max(1, int(args.limit)),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "derived": {"summary": summary},
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_pass_ratio": float(args.min_pass_ratio),
                "deny_actions": sorted(deny_actions),
                "max_pass_ratio_drop": float(args.max_pass_ratio_drop),
                "max_failure_total_increase": int(args.max_failure_total_increase),
                "max_rollback_count_increase": int(args.max_rollback_count_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.report_prefix}_{stamp}.json"
    md_path = out_dir / f"{args.report_prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")
    if args.gate and not report["gate"]["pass"]:
        for item in failures:
            print(f"[gate-failure] {item}")
        for item in baseline_failures:
            print(f"[baseline-failure] {item}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
