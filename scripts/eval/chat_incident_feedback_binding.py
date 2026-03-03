#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def resolve_cycle_reports(reports_dir: Path, *, prefix: str, limit: int) -> list[Path]:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    return rows[-max(1, int(limit)) :]


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


def classify_reason_code(reason_code: str) -> str:
    code = str(reason_code or "").strip().upper()
    if not code:
        return "OTHER"
    if "TIMEOUT" in code:
        return "LLM_TIMEOUT"
    if "TOOL" in code:
        return "TOOL_OUTAGE"
    if "INSUFFICIENT" in code or "LOW_EVIDENCE" in code:
        return "EVIDENCE_GAP"
    if "BUDGET" in code or "COST" in code or "TOKEN" in code:
        return "COST_BURST"
    if "AUTH" in code:
        return "AUTHZ_POLICY"
    if "LEGACY" in code:
        return "LEGACY_ROUTING"
    return "OTHER"


def extract_incident_reasons(paths: list[Path]) -> list[str]:
    reasons: list[str] = []
    for path in paths:
        payload = load_json(path)
        release_train = payload.get("release_train") if isinstance(payload.get("release_train"), Mapping) else {}
        decision = release_train.get("decision") if isinstance(release_train.get("decision"), Mapping) else {}
        action = str(decision.get("action") or "")
        reason = str(decision.get("reason") or "")
        if action.lower() == "rollback" and reason:
            reasons.append(reason)
        failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
        for failure in failures:
            if not isinstance(failure, str):
                continue
            reasons.append(failure)
    return reasons


def build_binding_summary(incident_reasons: list[str], triage_reasons: list[str]) -> dict[str, Any]:
    category_counts: dict[str, dict[str, int]] = {}
    for reason in incident_reasons:
        category = classify_reason_code(reason)
        row = category_counts.setdefault(category, {"incident": 0, "triage": 0, "total": 0})
        row["incident"] += 1
        row["total"] += 1
    for reason in triage_reasons:
        category = classify_reason_code(reason)
        row = category_counts.setdefault(category, {"incident": 0, "triage": 0, "total": 0})
        row["triage"] += 1
        row["total"] += 1

    ranked = sorted(category_counts.items(), key=lambda item: item[1]["total"], reverse=True)
    categories = [
        {
            "category": category,
            "incident": counts["incident"],
            "triage": counts["triage"],
            "total": counts["total"],
        }
        for category, counts in ranked
    ]
    return {
        "incident_reason_total": len(incident_reasons),
        "triage_reason_total": len(triage_reasons),
        "bound_category_total": len(categories),
        "categories": categories,
    }


def build_recommendations(summary: Mapping[str, Any], *, top_n: int) -> list[str]:
    category_rows = summary.get("categories") if isinstance(summary.get("categories"), list) else []
    recommendations: list[str] = []
    for row in category_rows[: max(1, int(top_n))]:
        if not isinstance(row, Mapping):
            continue
        category = str(row.get("category") or "OTHER")
        if category == "LLM_TIMEOUT":
            recommendations.append("다음 gameday에 LLM timeout 급증 시나리오를 우선 배치하고 capacity mode 전이 검증을 포함합니다.")
        elif category == "TOOL_OUTAGE":
            recommendations.append("Tool outage drill에 idempotency/compensation 체크리스트를 추가하고 실패 UX를 회귀 검증합니다.")
        elif category == "EVIDENCE_GAP":
            recommendations.append("근거부족 시나리오에서 retrieval 품질/abstention 문구/상담 전환 경로를 함께 검증합니다.")
        elif category == "COST_BURST":
            recommendations.append("비용폭주 시나리오에서 토큰 상한/admission/degrade 단계 전이를 재현합니다.")
        elif category == "AUTHZ_POLICY":
            recommendations.append("권한 거부 케이스를 drillpack에 포함해 교차 사용자 접근 차단을 재검증합니다.")
        elif category == "LEGACY_ROUTING":
            recommendations.append("legacy routing 재발 시나리오를 drillpack에 추가하고 decommission gate를 강화합니다.")
        else:
            recommendations.append(f"카테고리 {category} 케이스를 샘플링해 drillpack 보강 항목으로 반영합니다.")
    if not recommendations:
        recommendations.append("피드백 바인딩 데이터가 부족해 기존 drillpack 유지 후 다음 주기 데이터를 수집합니다.")
    return recommendations


def _category_total(summary: Mapping[str, Any], category: str) -> int:
    rows = summary.get("categories") if isinstance(summary.get("categories"), list) else []
    target = str(category or "").strip().upper()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("category") or "").strip().upper() == target:
            return int(row.get("total") or 0)
    return 0


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_bound_category_drop: int,
    max_incident_reason_increase: int,
    max_other_category_increase: int,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_bound_total = int(base_summary.get("bound_category_total") or 0)
    cur_bound_total = int(current_summary.get("bound_category_total") or 0)
    bound_drop = max(0, base_bound_total - cur_bound_total)
    if bound_drop > max(0, int(max_bound_category_drop)):
        failures.append(
            "bound category regression: "
            f"baseline={base_bound_total}, current={cur_bound_total}, allowed_drop={max(0, int(max_bound_category_drop))}"
        )

    base_incident_total = int(base_summary.get("incident_reason_total") or 0)
    cur_incident_total = int(current_summary.get("incident_reason_total") or 0)
    incident_increase = max(0, cur_incident_total - base_incident_total)
    if incident_increase > max(0, int(max_incident_reason_increase)):
        failures.append(
            "incident reason regression: "
            f"baseline={base_incident_total}, current={cur_incident_total}, "
            f"allowed_increase={max(0, int(max_incident_reason_increase))}"
        )

    base_other_total = _category_total(base_summary, "OTHER")
    cur_other_total = _category_total(current_summary, "OTHER")
    other_increase = max(0, cur_other_total - base_other_total)
    if other_increase > max(0, int(max_other_category_increase)):
        failures.append(
            "OTHER category regression: "
            f"baseline={base_other_total}, current={cur_other_total}, "
            f"allowed_increase={max(0, int(max_other_category_increase))}"
        )

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    categories = summary.get("categories") if isinstance(summary.get("categories"), list) else []
    recommendations = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
    lines: list[str] = []
    lines.append("# Chat Incident Feedback Binding")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- incident_reason_total: {summary.get('incident_reason_total')}")
    lines.append(f"- triage_reason_total: {summary.get('triage_reason_total')}")
    lines.append(f"- bound_category_total: {summary.get('bound_category_total')}")
    lines.append("")
    lines.append("## Bound Categories")
    lines.append("")
    if categories:
        for row in categories:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                f"- {row.get('category')}: total={row.get('total')} "
                f"(incident={row.get('incident')}, triage={row.get('triage')})"
            )
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Recommended Updates")
    lines.append("")
    for idx, recommendation in enumerate(recommendations, start=1):
        lines.append(f"{idx}. {recommendation}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    if not failures and not baseline_failures:
        lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bind incidents and triage reasons to drill taxonomy.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--cycle-prefix", default="chat_liveops_cycle")
    parser.add_argument("--cycle-limit", type=int, default=40)
    parser.add_argument("--triage-file", default="var/chat_graph/triage/chat_launch_failure_cases.jsonl")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_incident_feedback_binding")
    parser.add_argument("--min-bound-categories", type=int, default=1)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-bound-category-drop", type=int, default=1)
    parser.add_argument("--max-incident-reason-increase", type=int, default=3)
    parser.add_argument("--max-other-category-increase", type=int, default=1)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    cycle_paths = resolve_cycle_reports(Path(args.reports_dir), prefix=str(args.cycle_prefix), limit=max(1, int(args.cycle_limit)))
    incident_reasons = extract_incident_reasons(cycle_paths)
    triage_rows = read_jsonl(Path(args.triage_file))
    triage_reasons = [str(row.get("reason_code") or "unknown") for row in triage_rows]
    summary = build_binding_summary(incident_reasons, triage_reasons)
    recommendations = build_recommendations(summary, top_n=max(1, int(args.top_n)))
    failures: list[str] = []
    if int(summary.get("bound_category_total") or 0) < max(0, int(args.min_bound_categories)):
        failures.append(
            f"bound categories below threshold: {int(summary.get('bound_category_total') or 0)} < {int(args.min_bound_categories)}"
        )

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            summary,
            max_bound_category_drop=max(0, int(args.max_bound_category_drop)),
            max_incident_reason_increase=max(0, int(args.max_incident_reason_increase)),
            max_other_category_increase=max(0, int(args.max_other_category_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "reports_dir": str(args.reports_dir),
            "cycle_prefix": str(args.cycle_prefix),
            "cycle_limit": max(1, int(args.cycle_limit)),
            "triage_file": str(args.triage_file),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {"summary": summary},
        "recommendations": recommendations,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_bound_categories": int(args.min_bound_categories),
                "max_bound_category_drop": int(args.max_bound_category_drop),
                "max_incident_reason_increase": int(args.max_incident_reason_increase),
                "max_other_category_increase": int(args.max_other_category_increase),
            },
        },
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
    print(f"bound_category_total={int(summary.get('bound_category_total') or 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if args.gate and not payload["gate"]["pass"]:
        for failure in failures:
            print(f"[gate-failure] {failure}")
        for failure in baseline_failures:
            print(f"[baseline-failure] {failure}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
