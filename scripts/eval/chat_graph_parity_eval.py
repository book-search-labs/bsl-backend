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


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_diff_types(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        code = str(item or "").strip()
        if code:
            out.append(code)
    return out


def _primary_diff_type(diff_types: list[str]) -> str:
    if not diff_types:
        return "UNKNOWN_DIFF"
    priority = ("ACTION_DIFF", "ROUTE_DIFF", "REASON_DIFF", "CITATION_DIFF")
    normalized = set(diff_types)
    for code in priority:
        if code in normalized:
            return code
    return diff_types[0]


def _build_mismatch_samples(samples: list[Mapping[str, Any]], *, max_samples: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in reversed(samples):
        if bool(event.get("matched")):
            continue
        diff_types = _normalize_diff_types(event.get("diff_types"))
        out.append(
            {
                "ts": int(event.get("ts") or 0),
                "trace_id": str(event.get("trace_id") or ""),
                "request_id": str(event.get("request_id") or ""),
                "session_id": str(event.get("session_id") or ""),
                "intent": str(event.get("intent") or ""),
                "topic": str(event.get("topic") or ""),
                "severity": str(event.get("severity") or "INFO"),
                "diff_types": diff_types,
                "primary_diff_type": _primary_diff_type(diff_types),
            }
        )
        if len(out) >= max(1, int(max_samples)):
            break
    return out


def _diff_ratio(by_type: Mapping[str, Any], *, window_size: int, diff_type: str) -> float:
    if window_size <= 0:
        return 0.0
    count = int(by_type.get(diff_type) or 0)
    return max(0.0, float(count) / float(window_size))


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
    summary_samples = [item for item in (summary.get("samples") or []) if isinstance(item, Mapping)]
    mismatch_samples = _build_mismatch_samples(summary_samples, max_samples=min(20, max(1, int(run_sample_limit))))
    by_primary_diff_type: dict[str, int] = {}
    by_intent: dict[str, int] = {}
    by_topic: dict[str, int] = {}
    for item in mismatch_samples:
        diff_code = str(item.get("primary_diff_type") or "UNKNOWN_DIFF")
        by_primary_diff_type[diff_code] = by_primary_diff_type.get(diff_code, 0) + 1
        intent = str(item.get("intent") or "UNKNOWN")
        by_intent[intent] = by_intent.get(intent, 0) + 1
        topic = str(item.get("topic") or "")
        if topic:
            by_topic[topic] = by_topic.get(topic, 0) + 1
    return {
        "window_size": window_size,
        "matched": matched,
        "mismatched": mismatched,
        "mismatch_ratio": mismatch_ratio,
        "blocker_ratio": blocker_ratio,
        "by_type": summary.get("by_type") if isinstance(summary.get("by_type"), dict) else {},
        "by_severity": summary.get("by_severity") if isinstance(summary.get("by_severity"), dict) else {},
        "samples": summary.get("samples") if isinstance(summary.get("samples"), list) else [],
        "mismatch_samples": mismatch_samples,
        "mismatch_sample_count": len(mismatch_samples),
        "mismatch_classification": {
            "by_primary_diff_type": by_primary_diff_type,
            "by_intent": by_intent,
            "by_topic": by_topic,
        },
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
    max_action_diff_ratio_increase: float,
    require_baseline_approval: bool,
    max_baseline_age_days: int,
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

    base_by_type = base.get("by_type") if isinstance(base.get("by_type"), Mapping) else {}
    cur_by_type = current_derived.get("by_type") if isinstance(current_derived.get("by_type"), Mapping) else {}
    base_window = int(base.get("window_size") or 0)
    cur_window = int(current_derived.get("window_size") or 0)
    base_action_ratio = _diff_ratio(base_by_type, window_size=base_window, diff_type="ACTION_DIFF")
    cur_action_ratio = _diff_ratio(cur_by_type, window_size=cur_window, diff_type="ACTION_DIFF")
    action_ratio_increase = max(0.0, cur_action_ratio - base_action_ratio)
    if action_ratio_increase > max(0.0, float(max_action_diff_ratio_increase)):
        failures.append(
            "action diff ratio regression: "
            f"baseline={base_action_ratio:.6f}, current={cur_action_ratio:.6f}, allowed_increase={float(max_action_diff_ratio_increase):.6f}"
        )

    baseline_meta = baseline_report.get("baseline_meta") if isinstance(baseline_report.get("baseline_meta"), Mapping) else {}
    if require_baseline_approval:
        approved_by = str(baseline_meta.get("approved_by") or "").strip()
        approved_at = str(baseline_meta.get("approved_at") or "").strip()
        evidence = str(baseline_meta.get("evidence") or "").strip()
        if not approved_by:
            failures.append("baseline metadata missing approved_by")
        if not approved_at:
            failures.append("baseline metadata missing approved_at")
        if not evidence:
            failures.append("baseline metadata missing evidence")

    if max(0, int(max_baseline_age_days)) > 0:
        approved_at = ""
        if isinstance(baseline_meta, Mapping):
            approved_at = str(baseline_meta.get("approved_at") or "").strip()
        baseline_ts = _parse_iso_datetime(approved_at) or _parse_iso_datetime(baseline_report.get("generated_at"))
        if baseline_ts is None:
            failures.append("baseline timestamp missing or invalid for age check")
        else:
            age_days = (datetime.now(timezone.utc) - baseline_ts).total_seconds() / 86400.0
            if age_days > float(max(0, int(max_baseline_age_days))):
                failures.append(
                    f"baseline too old: age_days={age_days:.2f} > max_baseline_age_days={max(0, int(max_baseline_age_days))}"
                )
    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    graph_runs = derived.get("graph_runs") if isinstance(derived.get("graph_runs"), list) else []
    mismatch_samples = derived.get("mismatch_samples") if isinstance(derived.get("mismatch_samples"), list) else []
    mismatch_classification = (
        derived.get("mismatch_classification") if isinstance(derived.get("mismatch_classification"), Mapping) else {}
    )
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
    lines.append("## Mismatch Classification")
    lines.append("")
    by_primary = mismatch_classification.get("by_primary_diff_type") if isinstance(mismatch_classification, Mapping) else {}
    if isinstance(by_primary, Mapping) and by_primary:
        for diff_type, count in by_primary.items():
            lines.append(f"- {diff_type}: {int(count or 0)}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Mismatch Samples")
    lines.append("")
    for row in mismatch_samples:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- diff={row.get('primary_diff_type')}, severity={row.get('severity')}, "
            f"intent={row.get('intent')}, topic={row.get('topic')}, trace_id={row.get('trace_id')}, request_id={row.get('request_id')}"
        )
    if not mismatch_samples:
        lines.append("- (none)")
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
    parser.add_argument("--max-action-diff-ratio-increase", type=float, default=0.02)
    parser.add_argument("--require-baseline-approval", action="store_true")
    parser.add_argument("--max-baseline-age-days", type=int, default=0)
    parser.add_argument("--baseline-approved-by", default="")
    parser.add_argument("--baseline-evidence", default="")
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
            max_action_diff_ratio_increase=max(0.0, float(args.max_action_diff_ratio_increase)),
            require_baseline_approval=bool(args.require_baseline_approval),
            max_baseline_age_days=max(0, int(args.max_baseline_age_days)),
        )

    baseline_meta: dict[str, Any] = {}
    if str(args.baseline_approved_by or "").strip() or str(args.baseline_evidence or "").strip():
        baseline_meta = {
            "approved_by": str(args.baseline_approved_by or "").strip(),
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "evidence": str(args.baseline_evidence or "").strip(),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "shadow_limit": int(args.shadow_limit),
            "replay_dir": str(replay_dir),
            "run_sample_limit": int(args.run_sample_limit),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "baseline_meta": baseline_meta,
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
                "max_action_diff_ratio_increase": float(args.max_action_diff_ratio_increase),
                "require_baseline_approval": bool(args.require_baseline_approval),
                "max_baseline_age_days": int(args.max_baseline_age_days),
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
