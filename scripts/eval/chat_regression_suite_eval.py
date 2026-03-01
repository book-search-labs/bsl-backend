import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return data


def _normalized_queries(scenario: dict[str, Any]) -> str:
    turns = scenario.get("turns")
    if not isinstance(turns, list):
        return ""
    parts: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        query = str(turn.get("query") or "").strip().lower()
        if query:
            parts.append(query)
    return " ".join(parts)


def classify_domain(scenario: dict[str, Any]) -> str:
    scenario_id = str(scenario.get("id") or "").strip().lower()
    joined = f"{scenario_id} {_normalized_queries(scenario)}"
    if any(token in joined for token in ("추천", "recommend", "reference", "isbn", "출판사", "버전", "cart_recommend")):
        return "book"
    if any(token in joined for token in ("문의", "ticket", "stk")):
        return "support"
    if "policy" in joined and any(token in joined for token in ("refund", "shipping", "order", "환불", "배송", "주문")):
        return "policy"
    if any(token in joined for token in ("주문", "환불", "배송", "취소", "결제", "order", "refund", "shipment", "cancel")):
        return "commerce"
    return "generic"


def collect_suite_metrics(suite: dict[str, Any]) -> dict[str, Any]:
    scenarios = suite.get("scenarios")
    if not isinstance(scenarios, list):
        raise RuntimeError("fixture missing scenarios[]")
    valid_scenarios = [item for item in scenarios if isinstance(item, dict)]
    scenario_count = len(valid_scenarios)
    turn_counts: list[int] = []
    domain_counts: dict[str, int] = {}
    for scenario in valid_scenarios:
        turns = scenario.get("turns")
        turn_count = len(turns) if isinstance(turns, list) else 0
        turn_counts.append(turn_count)
        domain = classify_domain(scenario)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
    total_turns = sum(turn_counts)
    multi_turn_count = sum(1 for count in turn_counts if count >= 2)
    return {
        "suite_name": str(suite.get("suite") or "unknown"),
        "scenario_count": scenario_count,
        "turn_count": total_turns,
        "multi_turn_scenario_count": multi_turn_count,
        "single_turn_scenario_count": max(0, scenario_count - multi_turn_count),
        "max_turns_per_scenario": max(turn_counts) if turn_counts else 0,
        "domain_counts": domain_counts,
    }


def collect_ingest_count(ingest_dir: Path) -> int:
    if not ingest_dir.exists() or not ingest_dir.is_dir():
        return 0
    count = 0
    for path in ingest_dir.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".md", ".json"}:
            continue
        name = path.name.lower()
        if name in {"readme.md", "_index.md"}:
            continue
        if "feedback" in name or "feedback" in "/".join(part.lower() for part in path.parts):
            count += 1
    return count


def evaluate_gate(
    derived: dict[str, Any],
    *,
    min_scenarios: int,
    min_turns: int,
    min_multi_turn_scenarios: int,
    min_book_scenarios: int,
    ingest_count: int,
    require_ingest: bool,
    min_ingest_cases: int,
) -> list[str]:
    failures: list[str] = []
    scenario_count = int(derived.get("scenario_count") or 0)
    turn_count = int(derived.get("turn_count") or 0)
    multi_turn = int(derived.get("multi_turn_scenario_count") or 0)
    domain_counts = derived.get("domain_counts") if isinstance(derived.get("domain_counts"), dict) else {}
    book_count = int(domain_counts.get("book") or 0)

    if scenario_count < max(1, min_scenarios):
        failures.append(f"insufficient scenario count: {scenario_count} < {min_scenarios}")
    if turn_count < max(1, min_turns):
        failures.append(f"insufficient turn count: {turn_count} < {min_turns}")
    if multi_turn < max(1, min_multi_turn_scenarios):
        failures.append(f"insufficient multi-turn scenarios: {multi_turn} < {min_multi_turn_scenarios}")
    if book_count < max(1, min_book_scenarios):
        failures.append(f"insufficient book-domain scenarios: {book_count} < {min_book_scenarios}")
    if require_ingest and ingest_count < max(1, min_ingest_cases):
        failures.append(f"insufficient new-case ingestion: {ingest_count} < {min_ingest_cases}")
    return failures


def compare_with_baseline(
    baseline_report: dict[str, Any],
    current_derived: dict[str, Any],
    *,
    max_scenario_drop: int,
    max_turn_drop: int,
    max_book_drop: int,
) -> list[str]:
    failures: list[str] = []
    baseline_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), dict) else {}
    base_scenarios = int(baseline_derived.get("scenario_count") or 0)
    curr_scenarios = int(current_derived.get("scenario_count") or 0)
    if curr_scenarios < base_scenarios - max(0, max_scenario_drop):
        failures.append(
            "scenario count regression: "
            f"baseline={base_scenarios}, current={curr_scenarios}, allowed_drop={max_scenario_drop}"
        )

    base_turns = int(baseline_derived.get("turn_count") or 0)
    curr_turns = int(current_derived.get("turn_count") or 0)
    if curr_turns < base_turns - max(0, max_turn_drop):
        failures.append(
            "turn count regression: "
            f"baseline={base_turns}, current={curr_turns}, allowed_drop={max_turn_drop}"
        )

    base_domains = baseline_derived.get("domain_counts") if isinstance(baseline_derived.get("domain_counts"), dict) else {}
    curr_domains = current_derived.get("domain_counts") if isinstance(current_derived.get("domain_counts"), dict) else {}
    base_book = int(base_domains.get("book") or 0)
    curr_book = int(curr_domains.get("book") or 0)
    if curr_book < base_book - max(0, max_book_drop):
        failures.append(
            "book scenario regression: "
            f"baseline={base_book}, current={curr_book}, allowed_drop={max_book_drop}"
        )
    return failures


def render_markdown(report: dict[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), dict) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), dict) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    domain_counts = derived.get("domain_counts") if isinstance(derived.get("domain_counts"), dict) else {}

    lines: list[str] = []
    lines.append("# Chat Regression Suite Eval Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- fixture: {report.get('source', {}).get('fixture')}")
    lines.append(f"- ingest_dir: {report.get('source', {}).get('ingest_dir')}")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| scenario_count | {int(derived.get('scenario_count') or 0)} |")
    lines.append(f"| turn_count | {int(derived.get('turn_count') or 0)} |")
    lines.append(f"| multi_turn_scenario_count | {int(derived.get('multi_turn_scenario_count') or 0)} |")
    lines.append(f"| single_turn_scenario_count | {int(derived.get('single_turn_scenario_count') or 0)} |")
    lines.append(f"| max_turns_per_scenario | {int(derived.get('max_turns_per_scenario') or 0)} |")
    lines.append(f"| new_case_ingest_total | {int(report.get('ingest_count') or 0)} |")
    lines.append("")
    lines.append("## Domain Breakdown")
    lines.append("")
    if domain_counts:
        for domain, count in sorted(domain_counts.items(), key=lambda item: item[0]):
            lines.append(f"- {domain}: {int(count)}")
    else:
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
    parser = argparse.ArgumentParser(description="Evaluate chat multi-turn regression fixture coverage.")
    parser.add_argument(
        "--fixture",
        default="services/query-service/tests/fixtures/chat_state_regression_v1.json",
    )
    parser.add_argument("--ingest-dir", default="tasks/backlog/generated")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_regression_suite_eval")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--min-scenarios", type=int, default=30)
    parser.add_argument("--min-turns", type=int, default=45)
    parser.add_argument("--min-multi-turn-scenarios", type=int, default=12)
    parser.add_argument("--min-book-scenarios", type=int, default=8)
    parser.add_argument("--require-ingest", action="store_true")
    parser.add_argument("--min-ingest-cases", type=int, default=1)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-scenario-drop", type=int, default=0)
    parser.add_argument("--max-turn-drop", type=int, default=0)
    parser.add_argument("--max-book-drop", type=int, default=0)
    parser.add_argument("--write-baseline", default="")
    return parser.parse_args()


def _build_metric_snapshot(derived: dict[str, Any], ingest_count: int) -> dict[str, float]:
    metrics: dict[str, float] = {}
    metrics["chat_regression_suite_size{domain=all}"] = float(int(derived.get("scenario_count") or 0))
    domain_counts = derived.get("domain_counts") if isinstance(derived.get("domain_counts"), dict) else {}
    for domain, value in domain_counts.items():
        metrics[f"chat_regression_suite_size{{domain={domain}}}"] = float(int(value or 0))
    metrics["chat_regression_new_case_ingest_total"] = float(max(0, ingest_count))
    return metrics


def main() -> int:
    args = _parse_args()
    fixture_path = Path(args.fixture)
    ingest_dir = Path(args.ingest_dir)
    suite = load_json(fixture_path)
    derived = collect_suite_metrics(suite)
    ingest_count = collect_ingest_count(ingest_dir)

    failures = evaluate_gate(
        derived,
        min_scenarios=max(1, args.min_scenarios),
        min_turns=max(1, args.min_turns),
        min_multi_turn_scenarios=max(1, args.min_multi_turn_scenarios),
        min_book_scenarios=max(1, args.min_book_scenarios),
        ingest_count=ingest_count,
        require_ingest=bool(args.require_ingest),
        min_ingest_cases=max(1, args.min_ingest_cases),
    )

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            derived,
            max_scenario_drop=max(0, args.max_scenario_drop),
            max_turn_drop=max(0, args.max_turn_drop),
            max_book_drop=max(0, args.max_book_drop),
        )

    passed = not failures and not baseline_failures
    report = {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "fixture": str(fixture_path),
            "ingest_dir": str(ingest_dir),
            "baseline_report": args.baseline_report or None,
        },
        "thresholds": {
            "min_scenarios": max(1, args.min_scenarios),
            "min_turns": max(1, args.min_turns),
            "min_multi_turn_scenarios": max(1, args.min_multi_turn_scenarios),
            "min_book_scenarios": max(1, args.min_book_scenarios),
            "require_ingest": bool(args.require_ingest),
            "min_ingest_cases": max(1, args.min_ingest_cases),
            "max_scenario_drop": max(0, args.max_scenario_drop),
            "max_turn_drop": max(0, args.max_turn_drop),
            "max_book_drop": max(0, args.max_book_drop),
        },
        "derived": derived,
        "ingest_count": ingest_count,
        "metrics": _build_metric_snapshot(derived, ingest_count),
        "gate": {
            "pass": passed,
            "failures": failures,
            "baseline_failures": baseline_failures,
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{timestamp}.json"
    md_path = out_dir / f"{args.prefix}_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    if args.write_baseline:
        baseline_path = Path(args.write_baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[chat_regression_suite_eval] report(json): {json_path}")
    print(f"[chat_regression_suite_eval] report(md): {md_path}")
    print(f"[chat_regression_suite_eval] gate_pass={str(passed).lower()}")

    if args.gate and not passed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
