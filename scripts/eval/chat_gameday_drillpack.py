#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
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


def summarize_top_reasons(rows: list[Mapping[str, Any]], *, top_n: int) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("reason_code") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [{"reason_code": code, "count": count} for code, count in ranked[: max(1, int(top_n))]]


def build_default_scenarios(top_reasons: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    hot_reasons = [str(item.get("reason_code") or "unknown") for item in top_reasons]
    return [
        {
            "id": "gd-llm-timeout-surge",
            "title": "LLM timeout 급증",
            "reason_hints": [reason for reason in hot_reasons if "TIMEOUT" in reason.upper()] or ["PROVIDER_TIMEOUT"],
            "detection": [
                "chat fallback ratio 및 PROVIDER_TIMEOUT reason 급증 확인",
                "LLM gateway 응답시간(p95/p99)와 오류율 확인",
            ],
            "mitigation": [
                "capacity guard를 DEGRADE_LEVEL_1 이상으로 상향",
                "필요 시 release train hold 및 canary stage 축소",
            ],
            "validation": [
                "timeout reason 비율이 기준 이하로 복귀했는지 확인",
                "commerce completion rate 회복 여부 확인",
            ],
            "evidence": [
                "launch gate report",
                "capacity/cost guard output",
                "incident summary",
            ],
        },
        {
            "id": "gd-tool-outage",
            "title": "Tool 장애(조회/쓰기 API 실패)",
            "reason_hints": [reason for reason in hot_reasons if "TOOL" in reason.upper()] or ["TOOL_FAIL", "AUTHZ_DENY"],
            "detection": [
                "tool failure reason/top source 확인",
                "action audit에서 실패 전이(FAILED_RETRYABLE/FAILED_FINAL) 점검",
            ],
            "mitigation": [
                "tool retry budget/circuit breaker 상태 점검",
                "민감 write 경로를 fallback-safe 문구로 강등",
            ],
            "validation": [
                "중복 실행(idempotency 위반) 0건 확인",
                "claim verifier 오탐/미탐 샘플링 검토",
            ],
            "evidence": [
                "action audit log",
                "triage queue sample",
                "on-call action plan",
            ],
        },
        {
            "id": "gd-insufficient-evidence",
            "title": "근거부족 응답 급증",
            "reason_hints": [reason for reason in hot_reasons if "INSUFFICIENT" in reason.upper()] or ["insufficient_evidence"],
            "detection": [
                "insufficient_evidence_ratio 및 reason taxonomy 분포 확인",
                "RAG/retrieval 경로의 source window 변화 확인",
            ],
            "mitigation": [
                "query normalization/policy routing 임계치 재조정",
                "fallback 템플릿/next_action 안내 문구 품질 점검",
            ],
            "validation": [
                "insufficient ratio가 기준치 이하로 회복됐는지 확인",
                "사용자 후속 전환율(REFINE_QUERY/OPEN_SUPPORT_TICKET) 확인",
            ],
            "evidence": [
                "launch metrics",
                "reason taxonomy eval output",
                "chat replay samples",
            ],
        },
        {
            "id": "gd-cost-burst",
            "title": "비용/토큰 사용량 급등",
            "reason_hints": [reason for reason in hot_reasons if "BUDGET" in reason.upper()] or ["budget_gate_failed"],
            "detection": [
                "LLM audit tokens/cost per hour 급등 확인",
                "avg tool calls 및 llm path 비중 변화 확인",
            ],
            "mitigation": [
                "capacity mode 상향(DEGRADE_LEVEL_1/2) 및 heavy path admission 제한",
                "release hold 후 baseline 대비 변화량 점검",
            ],
            "validation": [
                "cost/tokens per hour가 목표 범위로 복귀했는지 확인",
                "핵심 커머스 intent 완결률 저하가 없는지 확인",
            ],
            "evidence": [
                "llm audit summary",
                "capacity/cost guard report",
                "readiness score report",
            ],
        },
    ]


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Chat Gameday Drillpack")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- triage_file: {payload.get('triage_file')}")
    lines.append(f"- triage_case_total: {payload.get('triage_case_total')}")
    lines.append("")
    lines.append("## Top Reasons")
    lines.append("")
    top_reasons = payload.get("top_reasons") if isinstance(payload.get("top_reasons"), list) else []
    if top_reasons:
        for row in top_reasons:
            if not isinstance(row, Mapping):
                continue
            lines.append(f"- {row.get('reason_code')}: {row.get('count')}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Scenarios")
    lines.append("")
    scenarios = payload.get("scenarios") if isinstance(payload.get("scenarios"), list) else []
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            continue
        lines.append(f"### {scenario.get('title')} ({scenario.get('id')})")
        lines.append("")
        lines.append(f"- reason_hints: {', '.join([str(item) for item in scenario.get('reason_hints') or []])}")
        lines.append("- Detection")
        for item in scenario.get("detection") or []:
            lines.append(f"  - [ ] {item}")
        lines.append("- Mitigation")
        for item in scenario.get("mitigation") or []:
            lines.append(f"  - [ ] {item}")
        lines.append("- Validation")
        for item in scenario.get("validation") or []:
            lines.append(f"  - [ ] {item}")
        lines.append("- Evidence")
        for item in scenario.get("evidence") or []:
            lines.append(f"  - [ ] {item}")
        lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate chat gameday drillpack checklist from triage reasons.")
    parser.add_argument("--triage-file", default="var/chat_graph/triage/chat_launch_failure_cases.jsonl")
    parser.add_argument("--top-reasons", type=int, default=5)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_gameday_drillpack")
    parser.add_argument("--require-triage", action="store_true")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    triage_path = Path(args.triage_file)
    triage_rows = read_jsonl(triage_path)
    top_reasons = summarize_top_reasons(triage_rows, top_n=max(1, int(args.top_reasons)))
    scenarios = build_default_scenarios(top_reasons)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "triage_file": str(triage_path),
        "triage_case_total": len(triage_rows),
        "top_reasons": top_reasons,
        "scenarios": scenarios,
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"scenario_total={len(scenarios)}")
    print(f"triage_case_total={len(triage_rows)}")

    failures: list[str] = []
    if args.require_triage and len(triage_rows) <= 0:
        failures.append("triage cases required but none found")
    if len(scenarios) <= 0:
        failures.append("no scenarios generated")
    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
