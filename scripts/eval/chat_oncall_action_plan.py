#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def build_plan(rows: list[Mapping[str, Any]], *, top_n: int) -> dict[str, Any]:
    by_source = Counter()
    by_reason = Counter()
    severity_counter = Counter()
    for row in rows:
        by_source[str(row.get("source") or "unknown")] += 1
        by_reason[str(row.get("reason_code") or "unknown")] += 1
        severity_counter[str(row.get("severity") or "WARN")] += 1

    top_reasons = by_reason.most_common(max(1, int(top_n)))
    steps: list[str] = []
    for reason, _count in top_reasons:
        code = str(reason).upper()
        if code in {"LAUNCH_GATE_FAILURE", "BASELINE_REGRESSION"}:
            steps.append("baseline/threshold 설정을 재검토하고 최신 report baseline을 갱신할지 판단합니다.")
        elif "PROVIDER_TIMEOUT" in code:
            steps.append("LLM/Tool timeout budget과 의존 서비스 상태를 확인하고 fallback 비율 급증 여부를 점검합니다.")
        elif "OUTPUT_GUARD" in code:
            steps.append("출력 가드 차단 사유를 샘플링해 prompt/policy 업데이트 필요성을 검토합니다.")
        elif "AUTH" in code:
            steps.append("AuthZ scope/tenant context 전달 누락을 우선 점검하고 교차 사용자 접근 차단 테스트를 재실행합니다.")
        elif "LEGACY" in code:
            steps.append("legacy route 발생 원인을 확인하고 decommission/emergency 플래그 오설정을 점검합니다.")
        else:
            steps.append(f"사유 `{reason}` 케이스를 샘플링해 재현 후 policy/tool/guard 중 원인 축을 분류합니다.")

    if not steps:
        steps.append("triage case가 없어 즉시 조치 항목은 없습니다. 다음 cycle까지 모니터링을 유지합니다.")

    return {
        "case_total": len(rows),
        "severity_counts": dict(severity_counter),
        "source_counts": dict(by_source),
        "reason_counts": dict(by_reason),
        "top_reasons": [{"reason_code": reason, "count": count} for reason, count in top_reasons],
        "actions": steps,
    }


def _unknown_reason_total(summary: Mapping[str, Any]) -> int:
    reason_counts = summary.get("reason_counts") if isinstance(summary.get("reason_counts"), Mapping) else {}
    total = 0
    for key, value in reason_counts.items():
        code = str(key or "").strip().upper()
        if code in {"UNKNOWN", "NONE", ""}:
            try:
                total += int(value)
            except Exception:
                continue
    return total


def evaluate_gate(summary: Mapping[str, Any], *, require_cases: bool) -> list[str]:
    failures: list[str] = []
    case_total = int(summary.get("case_total") or 0)
    if require_cases and case_total <= 0:
        failures.append("triage case required but case_total=0")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_case_total_increase: int,
    max_blocker_increase: int,
    max_unknown_reason_increase: int,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_case_total = int(base_summary.get("case_total") or 0)
    cur_case_total = int(current_summary.get("case_total") or 0)
    case_total_increase = max(0, cur_case_total - base_case_total)
    if case_total_increase > max(0, int(max_case_total_increase)):
        failures.append(
            "case_total regression: "
            f"baseline={base_case_total}, current={cur_case_total}, allowed_increase={max(0, int(max_case_total_increase))}"
        )

    base_severity = base_summary.get("severity_counts") if isinstance(base_summary.get("severity_counts"), Mapping) else {}
    cur_severity = (
        current_summary.get("severity_counts") if isinstance(current_summary.get("severity_counts"), Mapping) else {}
    )
    base_blocker = int(base_severity.get("BLOCKER") or 0)
    cur_blocker = int(cur_severity.get("BLOCKER") or 0)
    blocker_increase = max(0, cur_blocker - base_blocker)
    if blocker_increase > max(0, int(max_blocker_increase)):
        failures.append(
            "blocker_count regression: "
            f"baseline={base_blocker}, current={cur_blocker}, allowed_increase={max(0, int(max_blocker_increase))}"
        )

    base_unknown = _unknown_reason_total(base_summary)
    cur_unknown = _unknown_reason_total(current_summary)
    unknown_increase = max(0, cur_unknown - base_unknown)
    if unknown_increase > max(0, int(max_unknown_reason_increase)):
        failures.append(
            "unknown_reason regression: "
            f"baseline={base_unknown}, current={cur_unknown}, allowed_increase={max(0, int(max_unknown_reason_increase))}"
        )

    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    source = report.get("source") if isinstance(report.get("source"), Mapping) else {}
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    summary = derived.get("summary") if isinstance(derived.get("summary"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat On-call Action Plan")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- triage_file: {source.get('triage_file')}")
    lines.append(f"- case_total: {int(summary.get('case_total') or 0)}")
    lines.append("")
    lines.append("## Top Reasons")
    lines.append("")
    top_reasons = summary.get("top_reasons") if isinstance(summary.get("top_reasons"), list) else []
    if top_reasons:
        for row in top_reasons:
            if not isinstance(row, Mapping):
                continue
            lines.append(f"- {row.get('reason_code')}: {row.get('count')}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Recommended Actions")
    lines.append("")
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    for idx, action in enumerate(actions, start=1):
        lines.append(f"{idx}. {action}")
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
    parser = argparse.ArgumentParser(description="Generate on-call action plan from chat launch triage queue.")
    parser.add_argument("--triage-file", default="var/chat_graph/triage/chat_launch_failure_cases.jsonl")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--report-prefix", default="chat_oncall_action_plan")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--require-cases", action="store_true")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-case-total-increase", type=int, default=3)
    parser.add_argument("--max-blocker-increase", type=int, default=0)
    parser.add_argument("--max-unknown-reason-increase", type=int, default=1)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    triage_path = Path(args.triage_file)
    rows = read_jsonl(triage_path)
    summary = build_plan(rows, top_n=max(1, int(args.top_n)))
    failures = evaluate_gate(summary, require_cases=bool(args.require_cases))

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            summary,
            max_case_total_increase=max(0, int(args.max_case_total_increase)),
            max_blocker_increase=max(0, int(args.max_blocker_increase)),
            max_unknown_reason_increase=max(0, int(args.max_unknown_reason_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "triage_file": str(triage_path),
            "top_n": max(1, int(args.top_n)),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "derived": {
            "summary": summary,
        },
        "gate": {
            "enabled": bool(args.gate or args.require_cases),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "require_cases": bool(args.require_cases),
                "max_case_total_increase": int(args.max_case_total_increase),
                "max_blocker_increase": int(args.max_blocker_increase),
                "max_unknown_reason_increase": int(args.max_unknown_reason_increase),
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
    print(f"case_total={int(summary.get('case_total') or 0)}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")

    if args.gate and not report["gate"]["pass"]:
        for item in failures:
            print(f"[gate-failure] {item}")
        for item in baseline_failures:
            print(f"[baseline-failure] {item}")
        return 2
    if args.require_cases and not report["gate"]["pass"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
