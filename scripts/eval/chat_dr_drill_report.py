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


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_drill_summary(paths: list[Path]) -> dict[str, Any]:
    drills: list[dict[str, Any]] = []
    mttr_samples_sec: list[float] = []
    open_drill: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []

    for path in paths:
        payload = load_json(path)
        generated_at = str(payload.get("generated_at") or "")
        generated_dt = _parse_ts(generated_at)
        decision_root = payload.get("release_train") if isinstance(payload.get("release_train"), Mapping) else {}
        decision = decision_root.get("decision") if isinstance(decision_root.get("decision"), Mapping) else {}
        action = str(decision.get("action") or "unknown")
        failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
        passed = len(failures) == 0

        events.append(
            {
                "path": str(path),
                "generated_at": generated_at,
                "action": action,
                "pass": passed,
            }
        )

        if action == "rollback":
            if open_drill is None:
                open_drill = {
                    "opened_at": generated_at,
                    "opened_path": str(path),
                    "opened_reason": str(decision.get("reason") or "rollback"),
                }
            continue

        if action == "promote" and passed and open_drill is not None:
            opened_dt = _parse_ts(open_drill.get("opened_at"))
            mttr_sec = None
            if opened_dt is not None and generated_dt is not None and generated_dt >= opened_dt:
                mttr_sec = (generated_dt - opened_dt).total_seconds()
                mttr_samples_sec.append(mttr_sec)
            drill = dict(open_drill)
            drill.update(
                {
                    "recovered_at": generated_at,
                    "recovered_path": str(path),
                    "mttr_sec": mttr_sec,
                }
            )
            drills.append(drill)
            open_drill = None

    drill_total = len(drills) + (1 if open_drill is not None else 0)
    recovered_total = len(drills)
    recovery_ratio = 1.0 if drill_total == 0 else float(recovered_total) / float(drill_total)
    avg_mttr_sec = 0.0 if not mttr_samples_sec else float(sum(mttr_samples_sec)) / float(len(mttr_samples_sec))

    return {
        "window_size": len(paths),
        "drill_total": drill_total,
        "recovered_total": recovered_total,
        "open_drill_total": 1 if open_drill is not None else 0,
        "recovery_ratio": recovery_ratio,
        "avg_mttr_sec": avg_mttr_sec,
        "mttr_samples_sec": mttr_samples_sec[-20:],
        "drills": drills[-20:],
        "open_drill": open_drill,
        "events": events[-20:],
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    require_drill: bool,
    min_recovery_ratio: float,
    max_open_drill_total: int,
    max_avg_mttr_sec: float,
) -> list[str]:
    failures: list[str] = []
    window_size = int(summary.get("window_size") or 0)
    drill_total = int(summary.get("drill_total") or 0)
    recovery_ratio = float(summary.get("recovery_ratio") or 0.0)
    open_drill_total = int(summary.get("open_drill_total") or 0)
    avg_mttr_sec = float(summary.get("avg_mttr_sec") or 0.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"insufficient cycle samples: window_size={window_size} < min_window={min_window}")
    if require_drill and drill_total <= 0:
        failures.append("no rollback drill observed in the selected window")
    if recovery_ratio < max(0.0, float(min_recovery_ratio)):
        failures.append(f"recovery ratio below threshold: {recovery_ratio:.4f} < {float(min_recovery_ratio):.4f}")
    if open_drill_total > max(0, int(max_open_drill_total)):
        failures.append(f"open drill count exceeded: {open_drill_total} > {int(max_open_drill_total)}")
    if avg_mttr_sec > max(0.0, float(max_avg_mttr_sec)):
        failures.append(f"avg MTTR exceeded: {avg_mttr_sec:.2f}s > {float(max_avg_mttr_sec):.2f}s")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_recovery_ratio_drop: float,
    max_open_drill_increase: int,
    max_avg_mttr_sec_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_recovery_ratio = float(base_summary.get("recovery_ratio") or 0.0)
    cur_recovery_ratio = float(current_summary.get("recovery_ratio") or 0.0)
    recovery_ratio_drop = max(0.0, base_recovery_ratio - cur_recovery_ratio)
    if recovery_ratio_drop > max(0.0, float(max_recovery_ratio_drop)):
        failures.append(
            "recovery ratio regression: "
            f"baseline={base_recovery_ratio:.6f}, current={cur_recovery_ratio:.6f}, "
            f"allowed_drop={float(max_recovery_ratio_drop):.6f}"
        )

    base_open_total = int(base_summary.get("open_drill_total") or 0)
    cur_open_total = int(current_summary.get("open_drill_total") or 0)
    open_increase = max(0, cur_open_total - base_open_total)
    if open_increase > max(0, int(max_open_drill_increase)):
        failures.append(
            "open drill regression: "
            f"baseline={base_open_total}, current={cur_open_total}, allowed_increase={max(0, int(max_open_drill_increase))}"
        )

    base_avg_mttr = float(base_summary.get("avg_mttr_sec") or 0.0)
    cur_avg_mttr = float(current_summary.get("avg_mttr_sec") or 0.0)
    avg_mttr_increase = max(0.0, cur_avg_mttr - base_avg_mttr)
    if avg_mttr_increase > max(0.0, float(max_avg_mttr_sec_increase)):
        failures.append(
            "avg MTTR regression: "
            f"baseline={base_avg_mttr:.6f}, current={cur_avg_mttr:.6f}, "
            f"allowed_increase={float(max_avg_mttr_sec_increase):.6f}"
        )
    return failures


def render_markdown(
    report: Mapping[str, Any],
) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    summary = derived.get("summary") if isinstance(derived.get("summary"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat DR Drill Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- window_size: {int(summary.get('window_size') or 0)}")
    lines.append(f"- drill_total: {int(summary.get('drill_total') or 0)}")
    lines.append(f"- recovered_total: {int(summary.get('recovered_total') or 0)}")
    lines.append(f"- open_drill_total: {int(summary.get('open_drill_total') or 0)}")
    lines.append(f"- recovery_ratio: {float(summary.get('recovery_ratio') or 0.0):.4f}")
    lines.append(f"- avg_mttr_sec: {float(summary.get('avg_mttr_sec') or 0.0):.2f}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate chat DR drill report from liveops cycle reports.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_liveops_cycle")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--report-prefix", default="chat_dr_drill_report")
    parser.add_argument("--min-window", type=int, default=3)
    parser.add_argument("--require-drill", action="store_true")
    parser.add_argument("--min-recovery-ratio", type=float, default=1.0)
    parser.add_argument("--max-open-drill-total", type=int, default=0)
    parser.add_argument("--max-avg-mttr-sec", type=float, default=7200.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-recovery-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-open-drill-increase", type=int, default=0)
    parser.add_argument("--max-avg-mttr-sec-increase", type=float, default=600.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)
    paths = resolve_cycle_reports(reports_dir, prefix=str(args.prefix), limit=max(1, int(args.limit)))
    summary = build_drill_summary(paths)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        require_drill=bool(args.require_drill),
        min_recovery_ratio=max(0.0, float(args.min_recovery_ratio)),
        max_open_drill_total=max(0, int(args.max_open_drill_total)),
        max_avg_mttr_sec=max(0.0, float(args.max_avg_mttr_sec)),
    )

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            summary,
            max_recovery_ratio_drop=max(0.0, float(args.max_recovery_ratio_drop)),
            max_open_drill_increase=max(0, int(args.max_open_drill_increase)),
            max_avg_mttr_sec_increase=max(0.0, float(args.max_avg_mttr_sec_increase)),
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
                "require_drill": bool(args.require_drill),
                "min_recovery_ratio": float(args.min_recovery_ratio),
                "max_open_drill_total": int(args.max_open_drill_total),
                "max_avg_mttr_sec": float(args.max_avg_mttr_sec),
                "max_recovery_ratio_drop": float(args.max_recovery_ratio_drop),
                "max_open_drill_increase": int(args.max_open_drill_increase),
                "max_avg_mttr_sec_increase": float(args.max_avg_mttr_sec_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.report_prefix}_{stamp}.json"
    md_path = out_dir / f"{args.report_prefix}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"drill_total={int(summary.get('drill_total') or 0)}")
    print(f"open_drill_total={int(summary.get('open_drill_total') or 0)}")
    print(f"recovery_ratio={float(summary.get('recovery_ratio') or 0.0):.4f}")
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
