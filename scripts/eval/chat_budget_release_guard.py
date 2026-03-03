#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

MODE_ORDER: dict[str, int] = {"NORMAL": 0, "SOFT_CLAMP": 1, "HARD_CLAMP": 2}
RELEASE_STATE_ORDER: dict[str, int] = {"PROMOTE": 0, "HOLD": 1, "BLOCK": 2}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def resolve_latest_report(reports_dir: Path, *, prefix: str) -> Path | None:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    if not rows:
        return None
    return rows[-1]


def resolve_report_path(path: str, *, reports_dir: Path, prefix: str) -> Path | None:
    if str(path).strip():
        resolved = Path(path)
        if not resolved.exists():
            raise RuntimeError(f"report not found: {resolved}")
        return resolved
    return resolve_latest_report(reports_dir, prefix=prefix)


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def build_guard_summary(
    *,
    unit_payload: Mapping[str, Any],
    forecast_payload: Mapping[str, Any],
    optimizer_payload: Mapping[str, Any],
    monthly_budget_limit_usd: float,
) -> dict[str, Any]:
    unit_summary = unit_payload.get("summary") if isinstance(unit_payload.get("summary"), Mapping) else {}
    forecast_summary = forecast_payload.get("summary") if isinstance(forecast_payload.get("summary"), Mapping) else {}
    optimizer_decision = optimizer_payload.get("decision") if isinstance(optimizer_payload.get("decision"), Mapping) else {}

    forecast = forecast_summary.get("forecast") if isinstance(forecast_summary.get("forecast"), Mapping) else {}
    unit_total_cost = _safe_float(unit_summary.get("total_cost_usd"), 0.0)
    forecast_monthly_cost = _safe_float(forecast.get("monthly_cost_usd"), 0.0)

    optimizer_mode = str(optimizer_decision.get("mode") or "NORMAL").strip().upper() or "NORMAL"
    optimizer_budget_utilization = _safe_float(optimizer_decision.get("budget_utilization"), 0.0)
    estimated_savings_total_usd = _safe_float(optimizer_decision.get("estimated_savings_total_usd"), 0.0)

    savings_ratio = 0.0
    if unit_total_cost > 0.0:
        savings_ratio = max(0.0, min(0.9, estimated_savings_total_usd / unit_total_cost))
    projected_monthly_cost_after_optimizer = max(0.0, forecast_monthly_cost * (1.0 - savings_ratio))

    budget_limit = max(0.0, float(monthly_budget_limit_usd))
    pre_optimizer_budget_utilization = 0.0 if budget_limit <= 0.0 else forecast_monthly_cost / budget_limit
    post_optimizer_budget_utilization = (
        0.0 if budget_limit <= 0.0 else projected_monthly_cost_after_optimizer / budget_limit
    )

    return {
        "monthly_budget_limit_usd": budget_limit,
        "unit_window_size": _safe_int(unit_summary.get("window_size"), 0),
        "resolution_rate": _safe_float(unit_summary.get("resolution_rate"), 0.0),
        "cost_per_resolved_session": _safe_float(unit_summary.get("cost_per_resolved_session"), 0.0),
        "unresolved_cost_burn_total": _safe_float(unit_summary.get("unresolved_cost_burn_total"), 0.0),
        "forecast_monthly_cost_usd": forecast_monthly_cost,
        "forecast_peak_rps": _safe_float(forecast.get("peak_rps"), 0.0),
        "optimizer_mode": optimizer_mode,
        "optimizer_budget_utilization": optimizer_budget_utilization,
        "estimated_savings_total_usd": estimated_savings_total_usd,
        "savings_ratio": savings_ratio,
        "pre_optimizer_budget_utilization": pre_optimizer_budget_utilization,
        "post_optimizer_budget_utilization": post_optimizer_budget_utilization,
        "projected_monthly_cost_after_optimizer_usd": projected_monthly_cost_after_optimizer,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_resolution_rate: float,
    max_cost_per_resolved_session: float,
    max_unresolved_cost_burn_total: float,
    max_budget_utilization: float,
    clamp_trigger_utilization: float,
    require_clamp: bool,
) -> list[str]:
    failures: list[str] = []
    unit_window = _safe_int(summary.get("unit_window_size"), 0)
    resolution_rate = _safe_float(summary.get("resolution_rate"), 0.0)
    cost_per_resolved = _safe_float(summary.get("cost_per_resolved_session"), 0.0)
    unresolved_burn = _safe_float(summary.get("unresolved_cost_burn_total"), 0.0)
    post_budget_utilization = _safe_float(summary.get("post_optimizer_budget_utilization"), 0.0)
    optimizer_mode = str(summary.get("optimizer_mode") or "NORMAL").strip().upper()

    if unit_window < max(0, int(min_window)):
        failures.append(f"budget guard window too small: {unit_window} < {int(min_window)}")
    if unit_window == 0:
        return failures
    if optimizer_mode not in MODE_ORDER:
        failures.append(f"unknown optimizer mode: {optimizer_mode}")
        return failures

    if resolution_rate < max(0.0, float(min_resolution_rate)):
        failures.append(
            f"resolution rate below threshold: {resolution_rate:.4f} < {float(min_resolution_rate):.4f}"
        )
    if cost_per_resolved > max(0.0, float(max_cost_per_resolved_session)):
        failures.append(
            f"cost per resolved exceeded: {cost_per_resolved:.4f} > {float(max_cost_per_resolved_session):.4f}"
        )
    if unresolved_burn > max(0.0, float(max_unresolved_cost_burn_total)):
        failures.append(
            f"unresolved burn exceeded: {unresolved_burn:.4f} > {float(max_unresolved_cost_burn_total):.4f}"
        )
    if post_budget_utilization > max(0.0, float(max_budget_utilization)):
        failures.append(
            f"post-optimizer budget utilization exceeded: {post_budget_utilization:.4f} > {float(max_budget_utilization):.4f}"
        )
    if require_clamp and post_budget_utilization >= max(0.0, float(clamp_trigger_utilization)) and optimizer_mode == "NORMAL":
        failures.append(
            f"clamp required at utilization {post_budget_utilization:.4f}, but optimizer mode is NORMAL"
        )
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    current_release_state: str,
    *,
    max_release_state_step_increase: int,
    max_post_optimizer_budget_utilization_increase: float,
    max_resolution_rate_drop: float,
    max_cost_per_resolved_session_increase: float,
    max_unresolved_cost_burn_total_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]
    base_decision = baseline_report.get("decision") if isinstance(baseline_report.get("decision"), Mapping) else {}
    base_release_state = str(base_decision.get("release_state") or "PROMOTE").strip().upper() or "PROMOTE"
    cur_release_state = str(current_release_state or "PROMOTE").strip().upper() or "PROMOTE"

    base_release_rank = RELEASE_STATE_ORDER.get(base_release_state, 0)
    cur_release_rank = RELEASE_STATE_ORDER.get(cur_release_state, 0)
    release_state_step_increase = max(0, cur_release_rank - base_release_rank)
    if release_state_step_increase > max(0, int(max_release_state_step_increase)):
        failures.append(
            "release state regression: "
            f"baseline={base_release_state}, current={cur_release_state}, "
            f"allowed_step={max(0, int(max_release_state_step_increase))}"
        )

    base_post_budget = _safe_float(base_summary.get("post_optimizer_budget_utilization"), 0.0)
    cur_post_budget = _safe_float(current_summary.get("post_optimizer_budget_utilization"), 0.0)
    post_budget_increase = max(0.0, cur_post_budget - base_post_budget)
    if post_budget_increase > max(0.0, float(max_post_optimizer_budget_utilization_increase)):
        failures.append(
            "post-optimizer budget utilization regression: "
            f"baseline={base_post_budget:.6f}, current={cur_post_budget:.6f}, "
            f"allowed_increase={float(max_post_optimizer_budget_utilization_increase):.6f}"
        )

    base_resolution_rate = _safe_float(base_summary.get("resolution_rate"), 0.0)
    cur_resolution_rate = _safe_float(current_summary.get("resolution_rate"), 0.0)
    resolution_rate_drop = max(0.0, base_resolution_rate - cur_resolution_rate)
    if resolution_rate_drop > max(0.0, float(max_resolution_rate_drop)):
        failures.append(
            "resolution rate regression: "
            f"baseline={base_resolution_rate:.6f}, current={cur_resolution_rate:.6f}, "
            f"allowed_drop={float(max_resolution_rate_drop):.6f}"
        )

    base_cost_per_resolved = _safe_float(base_summary.get("cost_per_resolved_session"), 0.0)
    cur_cost_per_resolved = _safe_float(current_summary.get("cost_per_resolved_session"), 0.0)
    cost_per_resolved_increase = max(0.0, cur_cost_per_resolved - base_cost_per_resolved)
    if cost_per_resolved_increase > max(0.0, float(max_cost_per_resolved_session_increase)):
        failures.append(
            "cost per resolved regression: "
            f"baseline={base_cost_per_resolved:.6f}, current={cur_cost_per_resolved:.6f}, "
            f"allowed_increase={float(max_cost_per_resolved_session_increase):.6f}"
        )

    base_unresolved_burn = _safe_float(base_summary.get("unresolved_cost_burn_total"), 0.0)
    cur_unresolved_burn = _safe_float(current_summary.get("unresolved_cost_burn_total"), 0.0)
    unresolved_burn_increase = max(0.0, cur_unresolved_burn - base_unresolved_burn)
    if unresolved_burn_increase > max(0.0, float(max_unresolved_cost_burn_total_increase)):
        failures.append(
            "unresolved burn regression: "
            f"baseline={base_unresolved_burn:.6f}, current={cur_unresolved_burn:.6f}, "
            f"allowed_increase={float(max_unresolved_cost_burn_total_increase):.6f}"
        )
    return failures


def decide_release_state(failures: list[str]) -> str:
    if not failures:
        return "PROMOTE"
    severe_tokens = (
        "post-optimizer budget utilization exceeded",
        "resolution rate below threshold",
        "unknown optimizer mode",
    )
    if any(any(token in failure for token in severe_tokens) for failure in failures):
        return "BLOCK"
    return "HOLD"


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    decision = payload.get("decision") if isinstance(payload.get("decision"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Budget Release Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- forecast_report: {payload.get('forecast_report')}")
    lines.append(f"- unit_econ_report: {payload.get('unit_econ_report')}")
    lines.append(f"- optimizer_report: {payload.get('optimizer_report')}")
    lines.append(f"- unit_window_size: {_safe_int(summary.get('unit_window_size'), 0)}")
    lines.append(f"- resolution_rate: {_safe_float(summary.get('resolution_rate'), 0.0):.4f}")
    lines.append(f"- cost_per_resolved_session: {_safe_float(summary.get('cost_per_resolved_session'), 0.0):.4f}")
    lines.append(f"- unresolved_cost_burn_total: {_safe_float(summary.get('unresolved_cost_burn_total'), 0.0):.4f}")
    lines.append(f"- forecast_monthly_cost_usd: {_safe_float(summary.get('forecast_monthly_cost_usd'), 0.0):.2f}")
    lines.append(
        f"- post_optimizer_budget_utilization: {_safe_float(summary.get('post_optimizer_budget_utilization'), 0.0):.4f}"
    )
    lines.append(f"- optimizer_mode: {summary.get('optimizer_mode')}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- release_state: {decision.get('release_state')}")
    lines.append(f"- rationale: {decision.get('rationale')}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat release readiness from forecast + unit economics + optimizer reports.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--forecast-report", default="")
    parser.add_argument("--forecast-prefix", default="chat_capacity_forecast")
    parser.add_argument("--unit-econ-report", default="")
    parser.add_argument("--unit-econ-prefix", default="chat_unit_economics_slo")
    parser.add_argument("--optimizer-report", default="")
    parser.add_argument("--optimizer-prefix", default="chat_cost_optimizer_policy")
    parser.add_argument("--monthly-budget-limit-usd", type=float, default=15000.0)
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--min-resolution-rate", type=float, default=0.80)
    parser.add_argument("--max-cost-per-resolved-session", type=float, default=2.5)
    parser.add_argument("--max-unresolved-cost-burn-total", type=float, default=200.0)
    parser.add_argument("--max-budget-utilization", type=float, default=0.90)
    parser.add_argument("--clamp-trigger-utilization", type=float, default=0.75)
    parser.add_argument("--require-clamp", action="store_true")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-release-state-step-increase", type=int, default=0)
    parser.add_argument("--max-post-optimizer-budget-utilization-increase", type=float, default=0.05)
    parser.add_argument("--max-resolution-rate-drop", type=float, default=0.05)
    parser.add_argument("--max-cost-per-resolved-session-increase", type=float, default=0.50)
    parser.add_argument("--max-unresolved-cost-burn-total-increase", type=float, default=50.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_budget_release_guard")
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)

    forecast_report = resolve_report_path(
        args.forecast_report,
        reports_dir=reports_dir,
        prefix=str(args.forecast_prefix),
    )
    unit_report = resolve_report_path(
        args.unit_econ_report,
        reports_dir=reports_dir,
        prefix=str(args.unit_econ_prefix),
    )
    optimizer_report = resolve_report_path(
        args.optimizer_report,
        reports_dir=reports_dir,
        prefix=str(args.optimizer_prefix),
    )

    summary = build_guard_summary(
        unit_payload=load_json(unit_report),
        forecast_payload=load_json(forecast_report),
        optimizer_payload=load_json(optimizer_report),
        monthly_budget_limit_usd=max(0.0, float(args.monthly_budget_limit_usd)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_resolution_rate=max(0.0, float(args.min_resolution_rate)),
        max_cost_per_resolved_session=max(0.0, float(args.max_cost_per_resolved_session)),
        max_unresolved_cost_burn_total=max(0.0, float(args.max_unresolved_cost_burn_total)),
        max_budget_utilization=max(0.0, float(args.max_budget_utilization)),
        clamp_trigger_utilization=max(0.0, float(args.clamp_trigger_utilization)),
        require_clamp=bool(args.require_clamp),
    )
    release_state = decide_release_state(failures)
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            release_state,
            max_release_state_step_increase=max(0, int(args.max_release_state_step_increase)),
            max_post_optimizer_budget_utilization_increase=max(
                0.0, float(args.max_post_optimizer_budget_utilization_increase)
            ),
            max_resolution_rate_drop=max(0.0, float(args.max_resolution_rate_drop)),
            max_cost_per_resolved_session_increase=max(0.0, float(args.max_cost_per_resolved_session_increase)),
            max_unresolved_cost_burn_total_increase=max(0.0, float(args.max_unresolved_cost_burn_total_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "forecast_report": str(forecast_report) if forecast_report else None,
        "unit_econ_report": str(unit_report) if unit_report else None,
        "optimizer_report": str(optimizer_report) if optimizer_report else None,
        "source": {
            "reports_dir": str(reports_dir),
            "forecast_report": str(forecast_report) if forecast_report else None,
            "unit_econ_report": str(unit_report) if unit_report else None,
            "optimizer_report": str(optimizer_report) if optimizer_report else None,
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": summary,
        },
        "decision": {
            "release_state": release_state,
            "rationale": "all thresholds satisfied" if not failures else "threshold breaches detected",
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_resolution_rate": float(args.min_resolution_rate),
                "max_cost_per_resolved_session": float(args.max_cost_per_resolved_session),
                "max_unresolved_cost_burn_total": float(args.max_unresolved_cost_burn_total),
                "max_budget_utilization": float(args.max_budget_utilization),
                "clamp_trigger_utilization": float(args.clamp_trigger_utilization),
                "require_clamp": bool(args.require_clamp),
                "max_release_state_step_increase": int(args.max_release_state_step_increase),
                "max_post_optimizer_budget_utilization_increase": float(
                    args.max_post_optimizer_budget_utilization_increase
                ),
                "max_resolution_rate_drop": float(args.max_resolution_rate_drop),
                "max_cost_per_resolved_session_increase": float(args.max_cost_per_resolved_session_increase),
                "max_unresolved_cost_burn_total_increase": float(args.max_unresolved_cost_burn_total_increase),
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
    print(f"release_state={release_state}")
    print(f"post_optimizer_budget_utilization={_safe_float(summary.get('post_optimizer_budget_utilization'), 0.0):.4f}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
