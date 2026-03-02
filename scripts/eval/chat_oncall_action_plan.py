#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


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
        "top_reasons": [{"reason_code": reason, "count": count} for reason, count in top_reasons],
        "actions": steps,
    }


def render_markdown(plan: Mapping[str, Any], *, triage_path: Path) -> str:
    lines: list[str] = []
    lines.append("# Chat On-call Action Plan")
    lines.append("")
    lines.append(f"- triage_file: {triage_path}")
    lines.append(f"- case_total: {int(plan.get('case_total') or 0)}")
    lines.append("")
    lines.append("## Top Reasons")
    lines.append("")
    top_reasons = plan.get("top_reasons") if isinstance(plan.get("top_reasons"), list) else []
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
    actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
    for idx, action in enumerate(actions, start=1):
        lines.append(f"{idx}. {action}")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate on-call action plan from chat launch triage queue.")
    parser.add_argument("--triage-file", default="var/chat_graph/triage/chat_launch_failure_cases.jsonl")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_oncall_action_plan")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--require-cases", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    triage_path = Path(args.triage_file)
    rows = read_jsonl(triage_path)
    plan = build_plan(rows, top_n=max(1, int(args.top_n)))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(plan, triage_path=triage_path), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"case_total={int(plan.get('case_total') or 0)}")

    if args.require_cases and int(plan.get("case_total") or 0) <= 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
