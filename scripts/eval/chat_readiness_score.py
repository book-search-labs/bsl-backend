#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

MODE_ORDER: dict[str, int] = {
    "NORMAL": 0,
    "DEGRADE_LEVEL_1": 1,
    "DEGRADE_LEVEL_2": 2,
    "FAIL_CLOSED": 3,
}


def _load_eval_module(script_name: str):
    path = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _safe_mode(value: Any, default: str = "NORMAL") -> str:
    mode = str(value or "").strip().upper()
    if mode in MODE_ORDER:
        return mode
    return default


def compute_readiness(
    *,
    launch_pass: bool,
    canary_pass: bool,
    insufficient_ratio: float,
    reason_invalid_ratio: float,
    reason_unknown_ratio: float,
    liveops_pass_ratio: float,
    rollback_rate: float,
    open_incident_total: int,
    mtta_sec: float,
    mttr_sec: float,
    capacity_mode: str,
    dr_recovery_ratio: float,
    dr_open_total: int,
    dr_drill_total: int,
    target_mtta_sec: float,
    target_mttr_sec: float,
) -> dict[str, Any]:
    quality = 100.0 if launch_pass else 40.0
    if not canary_pass:
        quality -= 20.0
    quality -= max(0.0, insufficient_ratio) * 50.0
    quality = _clamp(quality)

    safety = 100.0
    safety -= max(0.0, reason_invalid_ratio) * 200.0
    safety -= max(0.0, reason_unknown_ratio) * 60.0
    if not launch_pass:
        safety -= 20.0
    safety = _clamp(safety)

    reliability = _clamp(max(0.0, liveops_pass_ratio) * 100.0)
    reliability -= max(0.0, rollback_rate) * 50.0
    reliability -= max(0, int(open_incident_total)) * 25.0
    if mtta_sec > target_mtta_sec > 0:
        reliability -= min(20.0, ((mtta_sec - target_mtta_sec) / target_mtta_sec) * 20.0)
    if mttr_sec > target_mttr_sec > 0:
        reliability -= min(25.0, ((mttr_sec - target_mttr_sec) / target_mttr_sec) * 25.0)
    reliability = _clamp(reliability)

    mode = str(capacity_mode or "NORMAL").upper()
    cost_map = {
        "NORMAL": 100.0,
        "DEGRADE_LEVEL_1": 75.0,
        "DEGRADE_LEVEL_2": 45.0,
        "FAIL_CLOSED": 0.0,
    }
    cost = _clamp(cost_map.get(mode, 60.0))

    recovery = _clamp(max(0.0, dr_recovery_ratio) * 100.0)
    if int(dr_drill_total) <= 0:
        recovery = min(recovery, 70.0)
    recovery -= max(0, int(dr_open_total)) * 30.0
    recovery = _clamp(recovery)

    weights = {
        "quality": 25.0,
        "safety": 20.0,
        "reliability": 25.0,
        "cost": 15.0,
        "recovery": 15.0,
    }
    weighted_total = (
        quality * weights["quality"]
        + safety * weights["safety"]
        + reliability * weights["reliability"]
        + cost * weights["cost"]
        + recovery * weights["recovery"]
    ) / 100.0
    total_score = _clamp(weighted_total, 0.0, 100.0)

    blockers: list[str] = []
    warnings: list[str] = []
    if not launch_pass:
        blockers.append("launch_gate_failed")
    if int(open_incident_total) > 0:
        blockers.append("open_incident_exists")
    if mode == "FAIL_CLOSED":
        blockers.append("capacity_mode_fail_closed")
    if mode in {"DEGRADE_LEVEL_1", "DEGRADE_LEVEL_2"}:
        warnings.append(f"capacity_mode={mode}")
    if int(dr_drill_total) <= 0:
        warnings.append("no_recent_drill")

    if total_score >= 85.0 and not blockers:
        tier = "READY"
        action = "promote"
    elif total_score >= 70.0 and not blockers:
        tier = "WATCH"
        action = "hold"
    else:
        tier = "HOLD"
        action = "hold"

    return {
        "total_score": total_score,
        "tier": tier,
        "recommended_action": action,
        "components": {
            "quality": quality,
            "safety": safety,
            "reliability": reliability,
            "cost": cost,
            "recovery": recovery,
        },
        "weights": weights,
        "blockers": blockers,
        "warnings": warnings,
    }


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_payload: Mapping[str, Any],
    *,
    max_score_drop: float,
    max_open_incident_increase: int,
    max_rollback_rate_increase: float,
    max_capacity_mode_step_increase: int,
) -> list[str]:
    failures: list[str] = []
    base_readiness = baseline_report.get("readiness") if isinstance(baseline_report.get("readiness"), Mapping) else {}
    base_signals = baseline_report.get("signals") if isinstance(baseline_report.get("signals"), Mapping) else {}

    current_readiness = (
        current_payload.get("readiness") if isinstance(current_payload.get("readiness"), Mapping) else {}
    )
    current_signals = current_payload.get("signals") if isinstance(current_payload.get("signals"), Mapping) else {}

    base_score = _safe_float(base_readiness.get("total_score"), 0.0)
    cur_score = _safe_float(current_readiness.get("total_score"), 0.0)
    score_drop = max(0.0, base_score - cur_score)
    if score_drop > max(0.0, float(max_score_drop)):
        failures.append(
            "readiness score regression: "
            f"baseline={base_score:.6f}, current={cur_score:.6f}, allowed_drop={float(max_score_drop):.6f}"
        )

    base_open_incident = int(base_signals.get("open_incident_total") or 0)
    cur_open_incident = int(current_signals.get("open_incident_total") or 0)
    open_increase = max(0, cur_open_incident - base_open_incident)
    if open_increase > max(0, int(max_open_incident_increase)):
        failures.append(
            "open incident regression: "
            f"baseline={base_open_incident}, current={cur_open_incident}, allowed_increase={max(0, int(max_open_incident_increase))}"
        )

    base_rollback_rate = _safe_float(base_signals.get("rollback_rate"), 0.0)
    cur_rollback_rate = _safe_float(current_signals.get("rollback_rate"), 0.0)
    rollback_increase = max(0.0, cur_rollback_rate - base_rollback_rate)
    if rollback_increase > max(0.0, float(max_rollback_rate_increase)):
        failures.append(
            "rollback rate regression: "
            f"baseline={base_rollback_rate:.6f}, current={cur_rollback_rate:.6f}, "
            f"allowed_increase={float(max_rollback_rate_increase):.6f}"
        )

    base_capacity_mode = _safe_mode(base_signals.get("capacity_mode"), "NORMAL")
    cur_capacity_mode = _safe_mode(current_signals.get("capacity_mode"), "NORMAL")
    mode_step = max(0, MODE_ORDER[cur_capacity_mode] - MODE_ORDER[base_capacity_mode])
    if mode_step > max(0, int(max_capacity_mode_step_increase)):
        failures.append(
            "capacity mode regression: "
            f"baseline={base_capacity_mode}, current={cur_capacity_mode}, "
            f"allowed_step={max(0, int(max_capacity_mode_step_increase))}"
        )

    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), Mapping) else {}
    components = readiness.get("components") if isinstance(readiness.get("components"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    lines: list[str] = []
    lines.append("# Chat Production Readiness Score")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- score: {float(readiness.get('total_score') or 0.0):.2f}")
    lines.append(f"- tier: {readiness.get('tier')}")
    lines.append(f"- recommended_action: {readiness.get('recommended_action')}")
    lines.append("")
    lines.append("## Components")
    lines.append("")
    for key in ("quality", "safety", "reliability", "cost", "recovery"):
        lines.append(f"- {key}: {float(components.get(key) or 0.0):.2f}")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    blockers = readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
    if blockers:
        for item in blockers:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    warnings = readiness.get("warnings") if isinstance(readiness.get("warnings"), list) else []
    if warnings:
        for item in warnings:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    if failures:
        for item in failures:
            lines.append(f"- failure: {item}")
    if baseline_failures:
        for item in baseline_failures:
            lines.append(f"- baseline_failure: {item}")
    if not failures and not baseline_failures:
        lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute chat production readiness score from liveops artifacts.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--launch-gate-report", default="")
    parser.add_argument("--launch-prefix", default="chat_production_launch_gate")
    parser.add_argument("--cycle-prefix", default="chat_liveops_cycle")
    parser.add_argument("--cycle-limit", type=int, default=20)
    parser.add_argument("--llm-audit-log", default="var/llm_gateway/audit.log")
    parser.add_argument("--audit-window-minutes", type=int, default=60)
    parser.add_argument("--audit-limit", type=int, default=5000)
    parser.add_argument("--max-audit-error-ratio", type=float, default=0.08)
    parser.add_argument("--max-cost-usd-per-hour", type=float, default=5.0)
    parser.add_argument("--max-tokens-per-hour", type=float, default=300000.0)
    parser.add_argument("--max-llm-p95-ms", type=float, default=4000.0)
    parser.add_argument("--max-fallback-ratio", type=float, default=0.15)
    parser.add_argument("--max-insufficient-evidence-ratio", type=float, default=0.30)
    parser.add_argument("--capacity-max-mode", default="DEGRADE_LEVEL_1")
    parser.add_argument("--target-mtta-sec", type=float, default=600.0)
    parser.add_argument("--target-mttr-sec", type=float, default=7200.0)
    parser.add_argument("--min-score", type=float, default=80.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-score-drop", type=float, default=3.0)
    parser.add_argument("--max-open-incident-increase", type=int, default=0)
    parser.add_argument("--max-rollback-rate-increase", type=float, default=0.05)
    parser.add_argument("--max-capacity-mode-step-increase", type=int, default=0)
    parser.add_argument("--require-promote", action="store_true")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_readiness_score")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)

    capacity_mod = _load_eval_module("chat_capacity_cost_guard.py")
    liveops_mod = _load_eval_module("chat_liveops_summary.py")
    incident_mod = _load_eval_module("chat_liveops_incident_summary.py")
    dr_mod = _load_eval_module("chat_dr_drill_report.py")

    launch_report_path = capacity_mod.resolve_launch_gate_report(
        str(args.launch_gate_report),
        reports_dir=str(args.reports_dir),
        prefix=str(args.launch_prefix),
    )
    launch_report = capacity_mod.load_json(launch_report_path)
    derived = launch_report.get("derived") if isinstance(launch_report.get("derived"), Mapping) else {}
    canary = derived.get("canary") if isinstance(derived.get("canary"), Mapping) else {}
    reason = derived.get("reason") if isinstance(derived.get("reason"), Mapping) else {}
    completion = derived.get("completion") if isinstance(derived.get("completion"), Mapping) else {}
    perf = derived.get("perf") if isinstance(derived.get("perf"), Mapping) else {}
    gate = launch_report.get("gate") if isinstance(launch_report.get("gate"), Mapping) else {}

    cycle_paths = liveops_mod.resolve_cycle_reports(
        reports_dir,
        prefix=str(args.cycle_prefix),
        limit=max(1, int(args.cycle_limit)),
    )
    liveops_summary = liveops_mod.build_summary(cycle_paths)
    incident_summary = incident_mod.build_incident_summary(cycle_paths)
    dr_summary = dr_mod.build_drill_summary(cycle_paths)

    audit_rows = capacity_mod.read_audit_rows(
        Path(args.llm_audit_log),
        window_minutes=max(1, int(args.audit_window_minutes)),
        limit=max(1, int(args.audit_limit)),
    )
    audit_summary = capacity_mod.summarize_audit(audit_rows, window_minutes=max(1, int(args.audit_window_minutes)))
    capacity_decision = capacity_mod.decide_guard_mode(
        audit_summary=audit_summary,
        perf_summary=perf,
        completion_summary=completion,
        max_audit_error_ratio=max(0.0, float(args.max_audit_error_ratio)),
        max_cost_usd_per_hour=max(0.0, float(args.max_cost_usd_per_hour)),
        max_tokens_per_hour=max(0.0, float(args.max_tokens_per_hour)),
        max_llm_p95_ms=max(0.0, float(args.max_llm_p95_ms)),
        max_fallback_ratio=max(0.0, float(args.max_fallback_ratio)),
        max_insufficient_evidence_ratio=max(0.0, float(args.max_insufficient_evidence_ratio)),
    )
    capacity_failures = capacity_mod.evaluate_gate(capacity_decision, max_mode=str(args.capacity_max_mode))

    action_counts = liveops_summary.get("action_counts") if isinstance(liveops_summary.get("action_counts"), Mapping) else {}
    rollback_count = int(action_counts.get("rollback") or 0)
    window_size = max(1, int(liveops_summary.get("window_size") or 0))
    rollback_rate = float(rollback_count) / float(window_size)

    readiness = compute_readiness(
        launch_pass=_safe_bool(gate.get("pass"), False),
        canary_pass=_safe_bool(canary.get("passed"), False),
        insufficient_ratio=_safe_float(completion.get("insufficient_evidence_ratio"), 0.0),
        reason_invalid_ratio=_safe_float(reason.get("invalid_ratio"), 0.0),
        reason_unknown_ratio=_safe_float(reason.get("unknown_ratio"), 0.0),
        liveops_pass_ratio=_safe_float(liveops_summary.get("pass_ratio"), 0.0),
        rollback_rate=rollback_rate,
        open_incident_total=int(incident_summary.get("open_incident_total") or 0),
        mtta_sec=_safe_float(incident_summary.get("mtta_sec"), 0.0),
        mttr_sec=_safe_float(incident_summary.get("mttr_sec"), 0.0),
        capacity_mode=str(capacity_decision.get("mode") or "NORMAL"),
        dr_recovery_ratio=_safe_float(dr_summary.get("recovery_ratio"), 1.0),
        dr_open_total=int(dr_summary.get("open_drill_total") or 0),
        dr_drill_total=int(dr_summary.get("drill_total") or 0),
        target_mtta_sec=max(1.0, float(args.target_mtta_sec)),
        target_mttr_sec=max(1.0, float(args.target_mttr_sec)),
    )

    failures: list[str] = []
    total_score = float(readiness.get("total_score") or 0.0)
    if total_score < max(0.0, float(args.min_score)):
        failures.append(f"readiness score below threshold: {total_score:.2f} < {float(args.min_score):.2f}")
    if capacity_failures:
        failures.extend([f"capacity_guard: {item}" for item in capacity_failures])
    blockers = readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
    if blockers:
        failures.extend([f"blocker: {item}" for item in blockers])
    if args.require_promote and str(readiness.get("recommended_action") or "") != "promote":
        failures.append(f"require_promote enabled but action={readiness.get('recommended_action')}")
    baseline_failures: list[str] = []
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "launch_gate_report_path": str(launch_report_path),
        "cycle_window_size": int(liveops_summary.get("window_size") or 0),
        "sources": {
            "reports_dir": str(reports_dir),
            "cycle_prefix": str(args.cycle_prefix),
            "launch_prefix": str(args.launch_prefix),
            "llm_audit_log": str(args.llm_audit_log),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "signals": {
            "launch_pass": _safe_bool(gate.get("pass"), False),
            "canary_pass": _safe_bool(canary.get("passed"), False),
            "liveops_pass_ratio": _safe_float(liveops_summary.get("pass_ratio"), 0.0),
            "rollback_rate": rollback_rate,
            "open_incident_total": int(incident_summary.get("open_incident_total") or 0),
            "mtta_sec": _safe_float(incident_summary.get("mtta_sec"), 0.0),
            "mttr_sec": _safe_float(incident_summary.get("mttr_sec"), 0.0),
            "capacity_mode": str(capacity_decision.get("mode") or "NORMAL"),
            "dr_recovery_ratio": _safe_float(dr_summary.get("recovery_ratio"), 1.0),
            "dr_open_total": int(dr_summary.get("open_drill_total") or 0),
            "dr_drill_total": int(dr_summary.get("drill_total") or 0),
        },
        "readiness": readiness,
        "gate": {
            "enabled": bool(args.gate),
            "pass": True,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_score": float(args.min_score),
                "capacity_max_mode": str(args.capacity_max_mode),
                "require_promote": bool(args.require_promote),
                "max_score_drop": float(args.max_score_drop),
                "max_open_incident_increase": int(args.max_open_incident_increase),
                "max_rollback_rate_increase": float(args.max_rollback_rate_increase),
                "max_capacity_mode_step_increase": int(args.max_capacity_mode_step_increase),
            },
        },
    }
    if args.baseline_report:
        baseline_payload = capacity_mod.load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            payload,
            max_score_drop=max(0.0, float(args.max_score_drop)),
            max_open_incident_increase=max(0, int(args.max_open_incident_increase)),
            max_rollback_rate_increase=max(0.0, float(args.max_rollback_rate_increase)),
            max_capacity_mode_step_increase=max(0, int(args.max_capacity_mode_step_increase)),
        )
        payload["gate"]["baseline_failures"] = baseline_failures
    payload["gate"]["pass"] = len(failures) == 0 and len(baseline_failures) == 0

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"score={total_score:.2f}")
    print(f"tier={readiness.get('tier')}")
    print(f"recommended_action={readiness.get('recommended_action')}")
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
