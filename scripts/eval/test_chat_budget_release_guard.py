import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_budget_release_guard.py"
    spec = importlib.util.spec_from_file_location("chat_budget_release_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_guard_summary_calculates_budget_utilization():
    module = _load_module()
    summary = module.build_guard_summary(
        unit_payload={
            "summary": {
                "window_size": 20,
                "resolution_rate": 0.9,
                "cost_per_resolved_session": 2.0,
                "unresolved_cost_burn_total": 50.0,
                "total_cost_usd": 200.0,
            }
        },
        forecast_payload={"summary": {"forecast": {"monthly_cost_usd": 12000.0, "peak_rps": 5.0}}},
        optimizer_payload={"decision": {"mode": "SOFT_CLAMP", "estimated_savings_total_usd": 40.0, "budget_utilization": 0.8}},
        monthly_budget_limit_usd=15000.0,
    )
    assert summary["unit_window_size"] == 20
    assert summary["optimizer_mode"] == "SOFT_CLAMP"
    assert summary["pre_optimizer_budget_utilization"] == 0.8
    assert summary["post_optimizer_budget_utilization"] < 0.8


def test_evaluate_gate_detects_budget_and_quality_breaches():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "unit_window_size": 10,
            "resolution_rate": 0.6,
            "cost_per_resolved_session": 3.0,
            "unresolved_cost_burn_total": 300.0,
            "post_optimizer_budget_utilization": 1.1,
            "optimizer_mode": "NORMAL",
        },
        min_window=1,
        min_resolution_rate=0.8,
        max_cost_per_resolved_session=2.5,
        max_unresolved_cost_burn_total=200.0,
        max_budget_utilization=0.9,
        clamp_trigger_utilization=0.75,
        require_clamp=True,
    )
    assert len(failures) == 5


def test_evaluate_gate_passes_empty_window_when_min_window_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "unit_window_size": 0,
            "resolution_rate": 0.0,
            "cost_per_resolved_session": 0.0,
            "unresolved_cost_burn_total": 0.0,
            "post_optimizer_budget_utilization": 0.0,
            "optimizer_mode": "NORMAL",
        },
        min_window=0,
        min_resolution_rate=0.8,
        max_cost_per_resolved_session=2.5,
        max_unresolved_cost_burn_total=200.0,
        max_budget_utilization=0.9,
        clamp_trigger_utilization=0.75,
        require_clamp=False,
    )
    assert failures == []


def test_decide_release_state_blocks_on_severe_failure():
    module = _load_module()
    state = module.decide_release_state(
        [
            "cost per resolved exceeded: 3.0000 > 2.5000",
            "post-optimizer budget utilization exceeded: 1.1000 > 0.9000",
        ]
    )
    assert state == "BLOCK"


def test_compare_with_baseline_detects_release_and_budget_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "post_optimizer_budget_utilization": 0.60,
                "resolution_rate": 0.90,
                "cost_per_resolved_session": 1.80,
                "unresolved_cost_burn_total": 40.0,
            }
        },
        "decision": {"release_state": "PROMOTE"},
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "post_optimizer_budget_utilization": 0.75,
            "resolution_rate": 0.80,
            "cost_per_resolved_session": 2.60,
            "unresolved_cost_burn_total": 120.0,
        },
        "BLOCK",
        max_release_state_step_increase=0,
        max_post_optimizer_budget_utilization_increase=0.05,
        max_resolution_rate_drop=0.05,
        max_cost_per_resolved_session_increase=0.50,
        max_unresolved_cost_burn_total_increase=50.0,
    )
    assert len(failures) == 5
