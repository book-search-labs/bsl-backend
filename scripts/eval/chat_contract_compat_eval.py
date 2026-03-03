import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*(?::[A-Z0-9_]+)*$")
_FOCUS_FIELDS = ("reason_code", "next_action", "recoverable")


def _validator_cls():
    try:
        from jsonschema import Draft202012Validator
    except Exception as exc:  # pragma: no cover - dependency gate
        raise RuntimeError("jsonschema package is required for chat_contract_compat_eval") from exc
    return Draft202012Validator


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def _resolve_path(data: Any, dotted_path: str) -> tuple[bool, Any]:
    current = data
    for raw in str(dotted_path or "").split("."):
        key = raw.strip()
        if not key:
            continue
        if isinstance(current, dict) and key in current:
            current = current[key]
            continue
        if isinstance(current, list):
            try:
                index = int(key)
            except Exception:
                return False, None
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
            continue
        return False, None
    return True, current


def _validate_reason_code(value: Any) -> bool:
    reason = str(value or "").strip()
    if not reason:
        return False
    return _REASON_CODE_PATTERN.match(reason) is not None


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _snapshot_path_types(value: Any, prefix: str = "$") -> dict[str, str]:
    snapshot: dict[str, str] = {prefix: _json_type(value)}
    if isinstance(value, dict):
        for key in sorted(value.keys()):
            child_prefix = f"{prefix}.{key}"
            snapshot.update(_snapshot_path_types(value[key], child_prefix))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_prefix = f"{prefix}.{index}"
            snapshot.update(_snapshot_path_types(item, child_prefix))
    return snapshot


def _snapshot_focus_fields(response: dict[str, Any]) -> dict[str, Any]:
    focus_fields: dict[str, Any] = {}
    for field in _FOCUS_FIELDS:
        exists, value = _resolve_path(response, field)
        if exists:
            focus_fields[field] = value
    return focus_fields


def evaluate_cases(
    payload: dict[str, Any],
    *,
    contracts_root: Path,
) -> dict[str, Any]:
    validator_cls = _validator_cls()
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("cases must be a list")

    results: List[Dict[str, Any]] = []
    schema_fail_total = 0
    required_path_fail_total = 0
    reason_code_fail_total = 0

    for item in cases:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id") or "").strip() or "unknown_case"
        schema_path_raw = str(item.get("schema") or "").strip()
        schema_path = contracts_root / schema_path_raw
        response = item.get("response")
        required_paths = item.get("required_paths")
        if not isinstance(response, dict):
            raise RuntimeError(f"case={case_id} response must be object")
        if not schema_path_raw:
            raise RuntimeError(f"case={case_id} schema is required")
        if not schema_path.exists():
            raise RuntimeError(f"case={case_id} schema not found: {schema_path}")

        schema_payload = load_json(schema_path)
        validator = validator_cls(schema_payload)
        errors = sorted(validator.iter_errors(response), key=lambda err: list(err.path))
        schema_ok = len(errors) == 0
        if not schema_ok:
            schema_fail_total += 1

        missing_paths: List[str] = []
        if isinstance(required_paths, list):
            for path in required_paths:
                exists, _ = _resolve_path(response, str(path))
                if not exists:
                    missing_paths.append(str(path))
        if missing_paths:
            required_path_fail_total += 1

        reason_code_ok = True
        if bool(item.get("check_reason_code", False)):
            exists, reason_value = _resolve_path(response, str(item.get("reason_code_path") or "reason_code"))
            reason_code_ok = bool(exists and _validate_reason_code(reason_value))
            if not reason_code_ok:
                reason_code_fail_total += 1

        signature = {
            "schema": schema_path_raw,
            "path_types": _snapshot_path_types(response),
            "focus_fields": _snapshot_focus_fields(response),
        }

        error_messages = [str(err.message) for err in errors[:5]]
        results.append(
            {
                "id": case_id,
                "schema": schema_path_raw,
                "schema_ok": schema_ok,
                "required_paths_missing": missing_paths,
                "reason_code_ok": reason_code_ok,
                "signature": signature,
                "errors": error_messages,
            }
        )

    case_total = len(results)
    failures_total = schema_fail_total + required_path_fail_total + reason_code_fail_total
    return {
        "case_total": case_total,
        "schema_fail_total": schema_fail_total,
        "required_path_fail_total": required_path_fail_total,
        "reason_code_fail_total": reason_code_fail_total,
        "failures_total": failures_total,
        "results": results,
    }


def evaluate_gate(
    derived: dict[str, Any],
    *,
    min_cases: int,
    require_all: bool,
) -> list[str]:
    failures: list[str] = []
    case_total = int(derived.get("case_total") or 0)
    schema_fail_total = int(derived.get("schema_fail_total") or 0)
    required_path_fail_total = int(derived.get("required_path_fail_total") or 0)
    reason_code_fail_total = int(derived.get("reason_code_fail_total") or 0)

    if case_total < max(1, min_cases):
        failures.append(f"insufficient contract cases: case_total={case_total} < min_cases={max(1, min_cases)}")
    if require_all and schema_fail_total > 0:
        failures.append(f"schema compatibility failures: {schema_fail_total}")
    if require_all and required_path_fail_total > 0:
        failures.append(f"required path failures: {required_path_fail_total}")
    if require_all and reason_code_fail_total > 0:
        failures.append(f"reason_code format failures: {reason_code_fail_total}")
    return failures


def compare_with_baseline(
    baseline_report: dict[str, Any],
    current_derived: dict[str, Any],
    *,
    max_case_drop: int,
    max_failure_increase: int,
) -> list[str]:
    failures: list[str] = []
    base = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), dict) else {}
    base_case_total = int(base.get("case_total") or 0)
    base_failures_total = int(base.get("failures_total") or 0)
    current_case_total = int(current_derived.get("case_total") or 0)
    current_failures_total = int(current_derived.get("failures_total") or 0)

    case_drop = max(0, base_case_total - current_case_total)
    if case_drop > max(0, int(max_case_drop)):
        failures.append(
            f"case count regression: baseline={base_case_total}, current={current_case_total}, allowed_drop={max_case_drop}"
        )

    failure_increase = max(0, current_failures_total - base_failures_total)
    if failure_increase > max(0, int(max_failure_increase)):
        failures.append(
            "compat failures regression: "
            f"baseline={base_failures_total}, current={current_failures_total}, allowed_increase={max_failure_increase}"
        )

    base_results = base.get("results") if isinstance(base.get("results"), list) else []
    current_results = current_derived.get("results") if isinstance(current_derived.get("results"), list) else []
    if base_results and current_results:
        base_by_id = _index_results_by_case(base_results)
        current_by_id = _index_results_by_case(current_results)
        missing_case_ids = sorted(set(base_by_id.keys()) - set(current_by_id.keys()))
        if missing_case_ids:
            failures.append(f"case signature regression: missing_cases={','.join(missing_case_ids)}")
        for case_id in sorted(set(base_by_id.keys()) & set(current_by_id.keys())):
            failures.extend(_compare_case_signature(case_id, base_by_id[case_id], current_by_id[case_id]))
    return failures


def _index_results_by_case(results: list[Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id") or "").strip()
        if not case_id:
            continue
        indexed[case_id] = item
    return indexed


def _compare_case_signature(
    case_id: str,
    baseline_case: dict[str, Any],
    current_case: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    baseline_signature = baseline_case.get("signature") if isinstance(baseline_case.get("signature"), dict) else {}
    current_signature = current_case.get("signature") if isinstance(current_case.get("signature"), dict) else {}

    baseline_schema = str(baseline_signature.get("schema") or baseline_case.get("schema") or "")
    current_schema = str(current_signature.get("schema") or current_case.get("schema") or "")
    if baseline_schema and current_schema and baseline_schema != current_schema:
        failures.append(
            f"case {case_id} schema changed: baseline={baseline_schema}, current={current_schema}"
        )

    baseline_paths = (
        baseline_signature.get("path_types") if isinstance(baseline_signature.get("path_types"), dict) else None
    )
    current_paths = current_signature.get("path_types") if isinstance(current_signature.get("path_types"), dict) else None
    if baseline_paths and current_paths:
        removed_paths = sorted(set(baseline_paths.keys()) - set(current_paths.keys()))
        if removed_paths:
            failures.append(f"case {case_id} removed paths: {', '.join(removed_paths[:5])}")

        type_changes: list[str] = []
        for path in sorted(set(baseline_paths.keys()) & set(current_paths.keys())):
            before = str(baseline_paths.get(path))
            after = str(current_paths.get(path))
            if before != after:
                type_changes.append(f"{path}({before}->{after})")
        if type_changes:
            failures.append(f"case {case_id} type changes: {', '.join(type_changes[:5])}")

    baseline_focus = (
        baseline_signature.get("focus_fields") if isinstance(baseline_signature.get("focus_fields"), dict) else None
    )
    current_focus = current_signature.get("focus_fields") if isinstance(current_signature.get("focus_fields"), dict) else None
    if baseline_focus and current_focus:
        for field in _FOCUS_FIELDS:
            if field not in baseline_focus or field not in current_focus:
                continue
            before = baseline_focus.get(field)
            after = current_focus.get(field)
            if before != after:
                failures.append(
                    f"case {case_id} focus field changed: {field} baseline={before!r}, current={after!r}"
                )
    return failures


def render_markdown(report: dict[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), dict) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), dict) else {}
    results = derived.get("results") if isinstance(derived.get("results"), list) else []
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat Contract Compatibility Eval Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- cases_source: {report.get('source', {}).get('cases_json')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| case_total | {int(derived.get('case_total') or 0)} |")
    lines.append(f"| schema_fail_total | {int(derived.get('schema_fail_total') or 0)} |")
    lines.append(f"| required_path_fail_total | {int(derived.get('required_path_fail_total') or 0)} |")
    lines.append(f"| reason_code_fail_total | {int(derived.get('reason_code_fail_total') or 0)} |")
    lines.append(f"| failures_total | {int(derived.get('failures_total') or 0)} |")
    lines.append("")
    lines.append("## Case Results")
    lines.append("")
    for item in results:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "unknown")
        schema_ok = bool(item.get("schema_ok"))
        reason_ok = bool(item.get("reason_code_ok"))
        missing = item.get("required_paths_missing") if isinstance(item.get("required_paths_missing"), list) else []
        lines.append(
            f"- {cid}: schema_ok={str(schema_ok).lower()}, reason_code_ok={str(reason_ok).lower()}, missing_paths={len(missing)}"
        )
    if not results:
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
    parser = argparse.ArgumentParser(description="Evaluate chat contract compatibility freeze cases.")
    parser.add_argument(
        "--cases-json",
        default="services/query-service/tests/fixtures/chat_contract_compat_v1.json",
    )
    parser.add_argument("--contracts-root", default=".")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_contract_compat_eval")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--min-cases", type=int, default=3)
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-case-drop", type=int, default=0)
    parser.add_argument("--max-failure-increase", type=int, default=0)
    parser.add_argument("--write-baseline", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    cases_path = Path(args.cases_json)
    contracts_root = Path(args.contracts_root)

    payload = load_json(cases_path)
    derived = evaluate_cases(payload, contracts_root=contracts_root)
    failures = evaluate_gate(
        derived,
        min_cases=max(1, int(args.min_cases)),
        require_all=bool(args.require_all),
    )

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            derived,
            max_case_drop=max(0, int(args.max_case_drop)),
            max_failure_increase=max(0, int(args.max_failure_increase)),
        )

    gate_pass = not failures and not baseline_failures
    report = {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "cases_json": str(cases_path),
            "contracts_root": str(contracts_root),
            "baseline_report": args.baseline_report or None,
        },
        "thresholds": {
            "min_cases": max(1, int(args.min_cases)),
            "require_all": bool(args.require_all),
            "max_case_drop": max(0, int(args.max_case_drop)),
            "max_failure_increase": max(0, int(args.max_failure_increase)),
        },
        "derived": derived,
        "gate": {
            "pass": gate_pass,
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

    print(f"[chat_contract_compat_eval] report(json): {json_path}")
    print(f"[chat_contract_compat_eval] report(md): {md_path}")
    print(f"[chat_contract_compat_eval] gate_pass={str(gate_pass).lower()}")
    if args.gate and not gate_pass:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
