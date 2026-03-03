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


def _parse_allow_reasons(raw: str) -> set[str]:
    return {item.strip() for item in str(raw).split(",") if item.strip()}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


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


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_legacy_count_increase: int,
    max_legacy_ratio_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_legacy_count = _int_value(base_summary, "legacy_count", 0)
    cur_legacy_count = _int_value(current_summary, "legacy_count", 0)
    count_increase = max(0, cur_legacy_count - base_legacy_count)
    if count_increase > max(0, int(max_legacy_count_increase)):
        failures.append(
            "legacy count regression: "
            f"baseline={base_legacy_count}, current={cur_legacy_count}, allowed_increase={max(0, int(max_legacy_count_increase))}"
        )

    base_legacy_ratio = _float_value(base_summary, "legacy_ratio", 0.0)
    cur_legacy_ratio = _float_value(current_summary, "legacy_ratio", 0.0)
    ratio_increase = max(0.0, cur_legacy_ratio - base_legacy_ratio)
    if ratio_increase > max(0.0, float(max_legacy_ratio_increase)):
        failures.append(
            "legacy ratio regression: "
            f"baseline={base_legacy_ratio:.6f}, current={cur_legacy_ratio:.6f}, allowed_increase={float(max_legacy_ratio_increase):.6f}"
        )
    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    summary = derived.get("summary") if isinstance(derived.get("summary"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat Legacy Decommission Gate Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- window_size: {_int_value(summary, 'window_size', 0)}")
    lines.append(f"- legacy_count: {_int_value(summary, 'legacy_count', 0)}")
    lines.append(f"- legacy_ratio: {_float_value(summary, 'legacy_ratio', 0.0):.6f}")
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
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_legacy_decommission_check")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-legacy-count-increase", type=int, default=0)
    parser.add_argument("--max-legacy-ratio-increase", type=float, default=0.0)
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

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            summary,
            max_legacy_count_increase=max(0, int(args.max_legacy_count_increase)),
            max_legacy_ratio_increase=max(0.0, float(args.max_legacy_ratio_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "limit": max(1, int(args.limit)),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "derived": {
            "summary": summary,
            "allow_legacy_reasons": sorted(allow_legacy_reasons),
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": max(0, int(args.min_window)),
                "max_legacy_count": max(0, int(args.max_legacy_count)),
                "max_legacy_ratio": max(0.0, float(args.max_legacy_ratio)),
                "allow_legacy_reasons": sorted(allow_legacy_reasons),
                "max_legacy_count_increase": max(0, int(args.max_legacy_count_increase)),
                "max_legacy_ratio_increase": max(0.0, float(args.max_legacy_ratio_increase)),
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
