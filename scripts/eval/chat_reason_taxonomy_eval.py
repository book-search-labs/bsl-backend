#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bootstrap_pythonpath() -> None:
    import sys

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


def _expectation_match(expect: str, *, invalid: bool, unknown: bool) -> bool:
    rule = str(expect or "valid").strip().lower()
    if rule == "invalid":
        return invalid
    if rule == "unknown":
        return (not invalid) and unknown
    if rule in {"valid_or_unknown", "known"}:
        return not invalid
    return (not invalid) and (not unknown)


def evaluate_case_fixture(
    payload: Mapping[str, Any],
    *,
    assessor: Callable[[Any, str], Mapping[str, Any]],
) -> dict[str, Any]:
    rows = payload.get("cases")
    if not isinstance(rows, list):
        raise RuntimeError("cases must be a list")

    results: list[dict[str, Any]] = []
    mismatch_total = 0
    invalid_total = 0
    unknown_total = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        case_id = str(row.get("id") or "unknown_case")
        source = str(row.get("source") or "response")
        reason_code = row.get("reason_code")
        expect = str(row.get("expect") or "valid")
        assessed = dict(assessor(reason_code, source))
        invalid = bool(assessed.get("invalid"))
        unknown = bool(assessed.get("unknown"))
        if invalid:
            invalid_total += 1
        if unknown:
            unknown_total += 1
        matched = _expectation_match(expect, invalid=invalid, unknown=unknown)
        if not matched:
            mismatch_total += 1
        results.append(
            {
                "id": case_id,
                "source": source,
                "reason_code": reason_code,
                "expect": expect,
                "invalid": invalid,
                "unknown": unknown,
                "normalized_reason_code": assessed.get("normalized_reason_code"),
                "matched": matched,
            }
        )

    case_total = len(results)
    return {
        "case_total": case_total,
        "mismatch_total": mismatch_total,
        "invalid_total": invalid_total,
        "unknown_total": unknown_total,
        "invalid_ratio": 0.0 if case_total == 0 else float(invalid_total) / float(case_total),
        "unknown_ratio": 0.0 if case_total == 0 else float(unknown_total) / float(case_total),
        "results": results,
    }


def _extract_response_entries(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("responses")
    if not isinstance(rows, list):
        raise RuntimeError("responses must be a list")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        response = row.get("response")
        if not isinstance(response, Mapping):
            continue
        out.append(
            {
                "id": str(row.get("id") or "unknown_response"),
                "source": str(row.get("source") or "response"),
                "reason_code": response.get("reason_code"),
                "status": response.get("status"),
            }
        )
    return out


def evaluate_response_fixture(
    payload: Mapping[str, Any],
    *,
    assessor: Callable[[Any, str], Mapping[str, Any]],
) -> dict[str, Any]:
    rows = _extract_response_entries(payload)
    invalid_total = 0
    unknown_total = 0
    results: list[dict[str, Any]] = []
    for row in rows:
        assessed = dict(assessor(row.get("reason_code"), str(row.get("source") or "response")))
        invalid = bool(assessed.get("invalid"))
        unknown = bool(assessed.get("unknown"))
        if invalid:
            invalid_total += 1
        if unknown:
            unknown_total += 1
        results.append(
            {
                "id": row.get("id"),
                "source": row.get("source"),
                "status": row.get("status"),
                "reason_code": row.get("reason_code"),
                "normalized_reason_code": assessed.get("normalized_reason_code"),
                "invalid": invalid,
                "unknown": unknown,
            }
        )
    total = len(results)
    return {
        "response_total": total,
        "invalid_total": invalid_total,
        "unknown_total": unknown_total,
        "invalid_ratio": 0.0 if total == 0 else float(invalid_total) / float(total),
        "unknown_ratio": 0.0 if total == 0 else float(unknown_total) / float(total),
        "results": results,
    }


def evaluate_gate(
    derived: Mapping[str, Any],
    *,
    min_cases: int,
    min_response_total: int,
    max_invalid_ratio: float,
    max_unknown_ratio: float,
) -> list[str]:
    failures: list[str] = []
    case_total = int(derived.get("case_total") or 0)
    response_total = int(derived.get("response_total") or 0)
    mismatch_total = int(derived.get("mismatch_total") or 0)
    invalid_ratio = float(derived.get("invalid_ratio") or 0.0)
    unknown_ratio = float(derived.get("unknown_ratio") or 0.0)

    if case_total < max(1, int(min_cases)):
        failures.append(f"insufficient taxonomy fixture cases: case_total={case_total} < min_cases={max(1, int(min_cases))}")
    if response_total < max(0, int(min_response_total)):
        failures.append(
            f"insufficient response samples: response_total={response_total} < min_response_total={max(0, int(min_response_total))}"
        )
    if mismatch_total > 0:
        failures.append(f"taxonomy fixture mismatches: {mismatch_total}")
    if invalid_ratio > max(0.0, float(max_invalid_ratio)):
        failures.append(f"invalid ratio exceeded: ratio={invalid_ratio:.6f} > max={float(max_invalid_ratio):.6f}")
    if unknown_ratio > max(0.0, float(max_unknown_ratio)):
        failures.append(f"unknown ratio exceeded: ratio={unknown_ratio:.6f} > max={float(max_unknown_ratio):.6f}")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_derived: Mapping[str, Any],
    *,
    max_invalid_ratio_increase: float,
    max_unknown_ratio_increase: float,
) -> list[str]:
    failures: list[str] = []
    base = baseline_report.get("derived")
    base_derived = base if isinstance(base, Mapping) else {}
    base_invalid = float(base_derived.get("invalid_ratio") or 0.0)
    base_unknown = float(base_derived.get("unknown_ratio") or 0.0)
    current_invalid = float(current_derived.get("invalid_ratio") or 0.0)
    current_unknown = float(current_derived.get("unknown_ratio") or 0.0)

    invalid_increase = max(0.0, current_invalid - base_invalid)
    unknown_increase = max(0.0, current_unknown - base_unknown)
    if invalid_increase > max(0.0, float(max_invalid_ratio_increase)):
        failures.append(
            "invalid ratio regression: "
            f"baseline={base_invalid:.6f}, current={current_invalid:.6f}, allowed_increase={float(max_invalid_ratio_increase):.6f}"
        )
    if unknown_increase > max(0.0, float(max_unknown_ratio_increase)):
        failures.append(
            "unknown ratio regression: "
            f"baseline={base_unknown:.6f}, current={current_unknown:.6f}, allowed_increase={float(max_unknown_ratio_increase):.6f}"
        )
    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    case_results = derived.get("case_results") if isinstance(derived.get("case_results"), list) else []
    response_results = derived.get("response_results") if isinstance(derived.get("response_results"), list) else []
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat Reason Taxonomy Eval Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- cases_source: {report.get('source', {}).get('cases_json')}")
    lines.append(f"- responses_source: {report.get('source', {}).get('responses_json')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| case_total | {int(derived.get('case_total') or 0)} |")
    lines.append(f"| response_total | {int(derived.get('response_total') or 0)} |")
    lines.append(f"| mismatch_total | {int(derived.get('mismatch_total') or 0)} |")
    lines.append(f"| fixture_invalid_total | {int(derived.get('fixture_invalid_total') or 0)} |")
    lines.append(f"| fixture_unknown_total | {int(derived.get('fixture_unknown_total') or 0)} |")
    lines.append(f"| invalid_total | {int(derived.get('invalid_total') or 0)} |")
    lines.append(f"| unknown_total | {int(derived.get('unknown_total') or 0)} |")
    lines.append(f"| invalid_ratio | {float(derived.get('invalid_ratio') or 0.0):.6f} |")
    lines.append(f"| unknown_ratio | {float(derived.get('unknown_ratio') or 0.0):.6f} |")
    lines.append("")
    lines.append("## Case Results")
    lines.append("")
    for item in case_results:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"- {item.get('id')}: matched={str(bool(item.get('matched'))).lower()}, "
            f"invalid={str(bool(item.get('invalid'))).lower()}, unknown={str(bool(item.get('unknown'))).lower()}"
        )
    if not case_results:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Response Results")
    lines.append("")
    for item in response_results:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"- {item.get('id')}: reason_code={item.get('normalized_reason_code')}, "
            f"invalid={str(bool(item.get('invalid'))).lower()}, unknown={str(bool(item.get('unknown'))).lower()}"
        )
    if not response_results:
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
    parser = argparse.ArgumentParser(description="Evaluate chat reason-code taxonomy governance gate.")
    parser.add_argument(
        "--cases-json",
        default="services/query-service/tests/fixtures/chat_reason_taxonomy_cases_v1.json",
    )
    parser.add_argument(
        "--responses-json",
        default="services/query-service/tests/fixtures/chat_reason_taxonomy_responses_v1.json",
    )
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_reason_taxonomy_eval")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--min-cases", type=int, default=5)
    parser.add_argument("--min-response-total", type=int, default=1)
    parser.add_argument("--max-invalid-ratio", type=float, default=0.0)
    parser.add_argument("--max-unknown-ratio", type=float, default=0.05)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-invalid-ratio-increase", type=float, default=0.0)
    parser.add_argument("--max-unknown-ratio-increase", type=float, default=0.01)
    parser.add_argument("--write-baseline", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _bootstrap_pythonpath()
    from app.core.chat_graph.reason_taxonomy import assess_reason_code

    def _assessor(reason_code: Any, source: str) -> Mapping[str, Any]:
        row = assess_reason_code(reason_code, source=source)
        return {
            "normalized_reason_code": row.normalized_reason_code,
            "invalid": row.invalid,
            "unknown": row.unknown,
        }

    cases_payload = load_json(Path(args.cases_json))
    responses_payload = load_json(Path(args.responses_json))

    case_derived = evaluate_case_fixture(cases_payload, assessor=_assessor)
    response_derived = evaluate_response_fixture(responses_payload, assessor=_assessor)
    derived = {
        "case_total": int(case_derived.get("case_total") or 0),
        "response_total": int(response_derived.get("response_total") or 0),
        "mismatch_total": int(case_derived.get("mismatch_total") or 0),
        "fixture_invalid_total": int(case_derived.get("invalid_total") or 0),
        "fixture_unknown_total": int(case_derived.get("unknown_total") or 0),
        "invalid_total": int(response_derived.get("invalid_total") or 0),
        "unknown_total": int(response_derived.get("unknown_total") or 0),
        "invalid_ratio": 0.0,
        "unknown_ratio": 0.0,
        "case_results": case_derived.get("results") if isinstance(case_derived.get("results"), list) else [],
        "response_results": response_derived.get("results") if isinstance(response_derived.get("results"), list) else [],
    }
    denom = int(derived["response_total"])
    if denom > 0:
        derived["invalid_ratio"] = float(derived["invalid_total"]) / float(denom)
        derived["unknown_ratio"] = float(derived["unknown_total"]) / float(denom)

    failures = evaluate_gate(
        derived,
        min_cases=max(1, int(args.min_cases)),
        min_response_total=max(0, int(args.min_response_total)),
        max_invalid_ratio=max(0.0, float(args.max_invalid_ratio)),
        max_unknown_ratio=max(0.0, float(args.max_unknown_ratio)),
    )

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            derived,
            max_invalid_ratio_increase=max(0.0, float(args.max_invalid_ratio_increase)),
            max_unknown_ratio_increase=max(0.0, float(args.max_unknown_ratio_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "cases_json": str(args.cases_json),
            "responses_json": str(args.responses_json),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "derived": derived,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_cases": max(1, int(args.min_cases)),
                "min_response_total": max(0, int(args.min_response_total)),
                "max_invalid_ratio": max(0.0, float(args.max_invalid_ratio)),
                "max_unknown_ratio": max(0.0, float(args.max_unknown_ratio)),
                "max_invalid_ratio_increase": max(0.0, float(args.max_invalid_ratio_increase)),
                "max_unknown_ratio_increase": max(0.0, float(args.max_unknown_ratio_increase)),
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
        for failure in failures:
            print(f"[gate-failure] {failure}")
        for failure in baseline_failures:
            print(f"[baseline-failure] {failure}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
