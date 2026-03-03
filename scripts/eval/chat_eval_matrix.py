#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_module(script_name: str):
    path = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


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


def _critical_gate_pass_map(matrix: Any) -> dict[str, bool]:
    out: dict[str, bool] = {}
    if not isinstance(matrix, list):
        return out
    for row in matrix:
        if not isinstance(row, Mapping):
            continue
        gate = str(row.get("gate") or "")
        if gate not in {"contract_compat", "reason_taxonomy", "parity"}:
            continue
        out[gate] = bool(row.get("pass"))
    return out


def _parity_derived(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    parity = payload.get("parity") if isinstance(payload.get("parity"), Mapping) else {}
    derived = parity.get("derived") if isinstance(parity.get("derived"), Mapping) else {}
    return derived


def evaluate_matrix(
    *,
    cases_json: Path,
    responses_json: Path,
    contracts_root: Path,
    replay_dir: Path,
    shadow_limit: int,
    parity_run_sample_limit: int,
) -> dict[str, Any]:
    _bootstrap_pythonpath()
    contract_mod = _load_module("chat_contract_compat_eval.py")
    reason_mod = _load_module("chat_reason_taxonomy_eval.py")
    parity_mod = _load_module("chat_graph_parity_eval.py")

    contract_payload = contract_mod.load_json(cases_json)
    contract_derived = contract_mod.evaluate_cases(contract_payload, contracts_root=contracts_root)
    contract_failures = contract_mod.evaluate_gate(
        contract_derived,
        min_cases=3,
        require_all=True,
    )

    from app.core.chat_graph.reason_taxonomy import assess_reason_code

    def _assessor(reason_code: Any, source: str) -> Mapping[str, Any]:
        row = assess_reason_code(reason_code, source=source)
        return {
            "normalized_reason_code": row.normalized_reason_code,
            "invalid": row.invalid,
            "unknown": row.unknown,
        }

    reason_cases = reason_mod.load_json(cases_json.parent / "chat_reason_taxonomy_cases_v1.json")
    reason_responses = reason_mod.load_json(responses_json)
    reason_case_derived = reason_mod.evaluate_case_fixture(reason_cases, assessor=_assessor)
    reason_response_derived = reason_mod.evaluate_response_fixture(reason_responses, assessor=_assessor)
    reason_derived = {
        "case_total": int(reason_case_derived.get("case_total") or 0),
        "response_total": int(reason_response_derived.get("response_total") or 0),
        "mismatch_total": int(reason_case_derived.get("mismatch_total") or 0),
        "invalid_total": int(reason_response_derived.get("invalid_total") or 0),
        "unknown_total": int(reason_response_derived.get("unknown_total") or 0),
        "invalid_ratio": float(reason_response_derived.get("invalid_ratio") or 0.0),
        "unknown_ratio": float(reason_response_derived.get("unknown_ratio") or 0.0),
        "case_results": reason_case_derived.get("results") if isinstance(reason_case_derived.get("results"), list) else [],
        "response_results": reason_response_derived.get("results") if isinstance(reason_response_derived.get("results"), list) else [],
    }
    reason_failures = reason_mod.evaluate_gate(
        reason_derived,
        min_cases=5,
        min_response_total=1,
        max_invalid_ratio=0.0,
        max_unknown_ratio=0.05,
    )

    parity_derived = parity_mod.evaluate_parity(
        shadow_limit=max(1, int(shadow_limit)),
        replay_dir=replay_dir,
        run_sample_limit=max(1, int(parity_run_sample_limit)),
    )
    parity_failures = parity_mod.evaluate_gate(
        parity_derived,
        min_window=0,
        max_mismatch_ratio=0.10,
        max_blocker_ratio=0.02,
        min_graph_run_count=0,
    )

    matrix: list[dict[str, Any]] = []
    matrix.append(
        {
            "gate": "contract_compat",
            "engine": "contract",
            "graph_run_id": "",
            "node_path": [],
            "pass": len(contract_failures) == 0,
            "failures": contract_failures,
        }
    )
    matrix.append(
        {
            "gate": "reason_taxonomy",
            "engine": "graph",
            "graph_run_id": "",
            "node_path": [],
            "pass": len(reason_failures) == 0,
            "failures": reason_failures,
        }
    )
    matrix.append(
        {
            "gate": "parity",
            "engine": "shadow",
            "graph_run_id": "",
            "node_path": [],
            "pass": len(parity_failures) == 0,
            "failures": parity_failures,
            "mismatch_ratio": float(parity_derived.get("mismatch_ratio") or 0.0),
            "blocker_ratio": float(parity_derived.get("blocker_ratio") or 0.0),
        }
    )
    for row in parity_derived.get("graph_runs") or []:
        if not isinstance(row, Mapping):
            continue
        matrix.append(
            {
                "gate": "parity_run_sample",
                "engine": str(row.get("engine") or "graph"),
                "graph_run_id": str(row.get("graph_run_id") or ""),
                "node_path": list(row.get("node_path") or []),
                "pass": True,
                "status": str(row.get("status") or ""),
                "reason_code": str(row.get("reason_code") or ""),
            }
        )

    aggregate_failures: list[str] = []
    if contract_failures:
        aggregate_failures.append(f"contract_compat failures={len(contract_failures)}")
    if reason_failures:
        aggregate_failures.append(f"reason_taxonomy failures={len(reason_failures)}")
    if parity_failures:
        aggregate_failures.append(f"parity failures={len(parity_failures)}")

    return {
        "contract": {"derived": contract_derived, "failures": contract_failures},
        "reason_taxonomy": {"derived": reason_derived, "failures": reason_failures},
        "parity": {"derived": parity_derived, "failures": parity_failures},
        "matrix": matrix,
        "gate_fail_total": len(aggregate_failures),
        "aggregate_failures": aggregate_failures,
    }


def evaluate_gate(derived: Mapping[str, Any]) -> list[str]:
    failures = derived.get("aggregate_failures")
    if isinstance(failures, list):
        return [str(item) for item in failures]
    return []


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_derived: Mapping[str, Any],
    *,
    max_gate_fail_increase: int,
    max_parity_mismatch_ratio_increase: float,
    max_parity_blocker_ratio_increase: float,
    require_baseline_approval: bool,
    max_baseline_age_days: int,
) -> list[str]:
    failures: list[str] = []
    base = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_fail_total = int(base.get("gate_fail_total") or 0)
    cur_fail_total = int(current_derived.get("gate_fail_total") or 0)
    increase = max(0, cur_fail_total - base_fail_total)
    if increase > max(0, int(max_gate_fail_increase)):
        failures.append(
            f"gate fail regression: baseline={base_fail_total}, current={cur_fail_total}, allowed_increase={max(0, int(max_gate_fail_increase))}"
        )

    baseline_gate_pass = _critical_gate_pass_map(base.get("matrix"))
    current_gate_pass = _critical_gate_pass_map(current_derived.get("matrix"))
    for gate in ("contract_compat", "reason_taxonomy", "parity"):
        if gate in baseline_gate_pass and gate not in current_gate_pass:
            failures.append(f"critical gate missing from matrix: gate={gate}")
            continue
        if baseline_gate_pass.get(gate) and not current_gate_pass.get(gate, False):
            failures.append(f"critical gate regression: gate={gate} baseline_pass=true current_pass=false")

    base_parity = _parity_derived(base)
    current_parity = _parity_derived(current_derived)
    base_mismatch = float(base_parity.get("mismatch_ratio") or 0.0)
    cur_mismatch = float(current_parity.get("mismatch_ratio") or 0.0)
    mismatch_increase = max(0.0, cur_mismatch - base_mismatch)
    if mismatch_increase > max(0.0, float(max_parity_mismatch_ratio_increase)):
        failures.append(
            "parity mismatch ratio regression: "
            f"baseline={base_mismatch:.6f}, current={cur_mismatch:.6f}, allowed_increase={float(max_parity_mismatch_ratio_increase):.6f}"
        )

    base_blocker = float(base_parity.get("blocker_ratio") or 0.0)
    cur_blocker = float(current_parity.get("blocker_ratio") or 0.0)
    blocker_increase = max(0.0, cur_blocker - base_blocker)
    if blocker_increase > max(0.0, float(max_parity_blocker_ratio_increase)):
        failures.append(
            "parity blocker ratio regression: "
            f"baseline={base_blocker:.6f}, current={cur_blocker:.6f}, allowed_increase={float(max_parity_blocker_ratio_increase):.6f}"
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
    matrix = derived.get("matrix") if isinstance(derived.get("matrix"), list) else []

    lines: list[str] = []
    lines.append("# Chat Eval Matrix Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- gate_fail_total: {int(derived.get('gate_fail_total') or 0)}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    lines.append("")
    lines.append("## Matrix")
    lines.append("")
    for row in matrix:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- gate={row.get('gate')} engine={row.get('engine')} run={row.get('graph_run_id')} pass={str(bool(row.get('pass'))).lower()}"
        )
    if not matrix:
        lines.append("- (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run unified chat eval matrix for graph migration.")
    parser.add_argument("--cases-json", default="services/query-service/tests/fixtures/chat_contract_compat_v1.json")
    parser.add_argument("--responses-json", default="services/query-service/tests/fixtures/chat_reason_taxonomy_responses_v1.json")
    parser.add_argument("--contracts-root", default=".")
    parser.add_argument("--replay-dir", default="var/chat_graph/replay")
    parser.add_argument("--shadow-limit", type=int, default=200)
    parser.add_argument("--parity-run-sample-limit", type=int, default=50)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_eval_matrix")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-gate-fail-increase", type=int, default=0)
    parser.add_argument("--max-parity-mismatch-ratio-increase", type=float, default=0.02)
    parser.add_argument("--max-parity-blocker-ratio-increase", type=float, default=0.01)
    parser.add_argument("--require-baseline-approval", action="store_true")
    parser.add_argument("--max-baseline-age-days", type=int, default=0)
    parser.add_argument("--baseline-approved-by", default="")
    parser.add_argument("--baseline-evidence", default="")
    parser.add_argument("--write-baseline", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    derived = evaluate_matrix(
        cases_json=Path(args.cases_json),
        responses_json=Path(args.responses_json),
        contracts_root=Path(args.contracts_root),
        replay_dir=Path(args.replay_dir),
        shadow_limit=max(1, int(args.shadow_limit)),
        parity_run_sample_limit=max(1, int(args.parity_run_sample_limit)),
    )
    failures = evaluate_gate(derived)

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            derived,
            max_gate_fail_increase=max(0, int(args.max_gate_fail_increase)),
            max_parity_mismatch_ratio_increase=max(0.0, float(args.max_parity_mismatch_ratio_increase)),
            max_parity_blocker_ratio_increase=max(0.0, float(args.max_parity_blocker_ratio_increase)),
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
            "cases_json": str(args.cases_json),
            "responses_json": str(args.responses_json),
            "replay_dir": str(args.replay_dir),
            "shadow_limit": int(args.shadow_limit),
            "parity_run_sample_limit": int(args.parity_run_sample_limit),
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
                "max_gate_fail_increase": int(args.max_gate_fail_increase),
                "max_parity_mismatch_ratio_increase": float(args.max_parity_mismatch_ratio_increase),
                "max_parity_blocker_ratio_increase": float(args.max_parity_blocker_ratio_increase),
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
