#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bootstrap_pythonpath() -> None:
    root = _project_root()
    query_service = root / "services" / "query-service"
    if str(query_service) not in sys.path:
        sys.path.insert(0, str(query_service))


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def _runs_dir(base_dir: Path) -> Path:
    return base_dir / "runs"


def _load_recent_run_rows(base_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    run_dir = _runs_dir(base_dir)
    if not run_dir.exists():
        return rows
    files = sorted(run_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[: max(1, int(limit))]:
        payload = load_json(path)
        checkpoints = payload.get("checkpoints") if isinstance(payload.get("checkpoints"), list) else []
        node_path = [str(item.get("node") or "") for item in checkpoints if isinstance(item, Mapping) and str(item.get("node") or "")]
        response = payload.get("response") if isinstance(payload.get("response"), Mapping) else {}
        rows.append(
            {
                "engine": "graph",
                "graph_run_id": str(payload.get("run_id") or path.stem),
                "node_path": node_path,
                "status": str(response.get("status") or ""),
                "reason_code": str(response.get("reason_code") or ""),
                "updated_at": int(payload.get("updated_at") or 0),
            }
        )
    return rows


def evaluate_parity(
    *,
    shadow_limit: int,
    replay_dir: Path,
    run_sample_limit: int,
) -> dict[str, Any]:
    _bootstrap_pythonpath()
    from app.core.chat_graph.shadow_comparator import build_shadow_summary

    summary = build_shadow_summary(limit=max(1, shadow_limit))
    runs = _load_recent_run_rows(replay_dir, limit=max(1, run_sample_limit))
    mismatched = int(summary.get("mismatched") or 0)
    matched = int(summary.get("matched") or 0)
    window_size = int(summary.get("window_size") or 0)
    blocker_ratio = float(summary.get("blocker_ratio") or 0.0)
    mismatch_ratio = float(summary.get("mismatch_ratio") or 0.0)
    return {
        "window_size": window_size,
        "matched": matched,
        "mismatched": mismatched,
        "mismatch_ratio": mismatch_ratio,
        "blocker_ratio": blocker_ratio,
        "by_type": summary.get("by_type") if isinstance(summary.get("by_type"), dict) else {},
        "by_severity": summary.get("by_severity") if isinstance(summary.get("by_severity"), dict) else {},
        "samples": summary.get("samples") if isinstance(summary.get("samples"), list) else [],
        "graph_runs": runs,
        "graph_run_count": len(runs),
    }


def evaluate_gate(
    derived: Mapping[str, Any],
    *,
    min_window: int,
    max_mismatch_ratio: float,
    max_blocker_ratio: float,
    min_graph_run_count: int,
) -> list[str]:
    failures: list[str] = []
    window_size = int(derived.get("window_size") or 0)
    graph_run_count = int(derived.get("graph_run_count") or 0)
    mismatch_ratio = float(derived.get("mismatch_ratio") or 0.0)
    blocker_ratio = float(derived.get("blocker_ratio") or 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"insufficient parity window: window_size={window_size} < min_window={max(0, int(min_window))}")
    if graph_run_count < max(0, int(min_graph_run_count)):
        failures.append(
            f"insufficient graph replay runs: graph_run_count={graph_run_count} < min_graph_run_count={max(0, int(min_graph_run_count))}"
        )
    if mismatch_ratio > max(0.0, float(max_mismatch_ratio)):
        failures.append(
            f"mismatch ratio exceeded: ratio={mismatch_ratio:.6f} > max={max(0.0, float(max_mismatch_ratio)):.6f}"
        )
    if blocker_ratio > max(0.0, float(max_blocker_ratio)):
        failures.append(
            f"blocker ratio exceeded: ratio={blocker_ratio:.6f} > max={max(0.0, float(max_blocker_ratio)):.6f}"
        )
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_derived: Mapping[str, Any],
    *,
    max_mismatch_ratio_increase: float,
    max_blocker_ratio_increase: float,
) -> list[str]:
    failures: list[str] = []
    base = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_mismatch = float(base.get("mismatch_ratio") or 0.0)
    base_blocker = float(base.get("blocker_ratio") or 0.0)
    cur_mismatch = float(current_derived.get("mismatch_ratio") or 0.0)
    cur_blocker = float(current_derived.get("blocker_ratio") or 0.0)

    mismatch_increase = max(0.0, cur_mismatch - base_mismatch)
    blocker_increase = max(0.0, cur_blocker - base_blocker)
    if mismatch_increase > max(0.0, float(max_mismatch_ratio_increase)):
        failures.append(
            "mismatch ratio regression: "
            f"baseline={base_mismatch:.6f}, current={cur_mismatch:.6f}, allowed_increase={float(max_mismatch_ratio_increase):.6f}"
        )
    if blocker_increase > max(0.0, float(max_blocker_ratio_increase)):
        failures.append(
            "blocker ratio regression: "
            f"baseline={base_blocker:.6f}, current={cur_blocker:.6f}, allowed_increase={float(max_blocker_ratio_increase):.6f}"
        )
    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    graph_runs = derived.get("graph_runs") if isinstance(derived.get("graph_runs"), list) else []
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat Graph Parity Eval Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| window_size | {int(derived.get('window_size') or 0)} |")
    lines.append(f"| matched | {int(derived.get('matched') or 0)} |")
    lines.append(f"| mismatched | {int(derived.get('mismatched') or 0)} |")
    lines.append(f"| mismatch_ratio | {float(derived.get('mismatch_ratio') or 0.0):.6f} |")
    lines.append(f"| blocker_ratio | {float(derived.get('blocker_ratio') or 0.0):.6f} |")
    lines.append(f"| graph_run_count | {int(derived.get('graph_run_count') or 0)} |")
    lines.append("")
    lines.append("## Graph Runs")
    lines.append("")
    for row in graph_runs:
        if not isinstance(row, Mapping):
            continue
        node_path = row.get("node_path") if isinstance(row.get("node_path"), list) else []
        lines.append(
            f"- run={row.get('graph_run_id')}, engine={row.get('engine')}, "
            f"status={row.get('status')}, reason={row.get('reason_code')}, node_path_len={len(node_path)}"
        )
    if not graph_runs:
        lines.append("- (none)")
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
    parser = argparse.ArgumentParser(description="Evaluate legacy-vs-graph parity using shadow + replay metadata.")
    parser.add_argument("--shadow-limit", type=int, default=200)
    parser.add_argument("--replay-dir", default="var/chat_graph/replay")
    parser.add_argument("--run-sample-limit", type=int, default=50)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_graph_parity_eval")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-graph-run-count", type=int, default=0)
    parser.add_argument("--max-mismatch-ratio", type=float, default=0.10)
    parser.add_argument("--max-blocker-ratio", type=float, default=0.02)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-mismatch-ratio-increase", type=float, default=0.02)
    parser.add_argument("--max-blocker-ratio-increase", type=float, default=0.01)
    parser.add_argument("--write-baseline", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    replay_dir = Path(args.replay_dir)

    derived = evaluate_parity(
        shadow_limit=max(1, int(args.shadow_limit)),
        replay_dir=replay_dir,
        run_sample_limit=max(1, int(args.run_sample_limit)),
    )

    failures = evaluate_gate(
        derived,
        min_window=max(0, int(args.min_window)),
        max_mismatch_ratio=max(0.0, float(args.max_mismatch_ratio)),
        max_blocker_ratio=max(0.0, float(args.max_blocker_ratio)),
        min_graph_run_count=max(0, int(args.min_graph_run_count)),
    )

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            derived,
            max_mismatch_ratio_increase=max(0.0, float(args.max_mismatch_ratio_increase)),
            max_blocker_ratio_increase=max(0.0, float(args.max_blocker_ratio_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "shadow_limit": int(args.shadow_limit),
            "replay_dir": str(replay_dir),
            "run_sample_limit": int(args.run_sample_limit),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "derived": derived,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_graph_run_count": int(args.min_graph_run_count),
                "max_mismatch_ratio": float(args.max_mismatch_ratio),
                "max_blocker_ratio": float(args.max_blocker_ratio),
                "max_mismatch_ratio_increase": float(args.max_mismatch_ratio_increase),
                "max_blocker_ratio_increase": float(args.max_blocker_ratio_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    if args.write_baseline:
        Path(args.write_baseline).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

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
