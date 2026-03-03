import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_finops_tradeoff_report.py"
    spec = importlib.util.spec_from_file_location("chat_finops_tradeoff_report", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_audit_reasons_orders_by_cost():
    module = _load_module()
    rows = [
        {"reason_code": "NONE", "cost_usd": 0.1, "tokens": 100},
        {"reason_code": "TIMEOUT", "cost_usd": 0.3, "tokens": 200},
        {"reason_code": "TIMEOUT", "cost_usd": 0.2, "tokens": 150},
    ]
    summary = module.summarize_audit_reasons(rows)
    assert summary["window_size"] == 3
    assert summary["top_reasons"][0]["reason_code"] == "TIMEOUT"
    assert abs(summary["top_reasons"][0]["cost_usd"] - 0.5) < 1e-9


def test_build_tradeoff_summary_aggregates_cost_quality():
    module = _load_module()
    summary = module.build_tradeoff_summary(
        unit_rows=[
            {"cost_per_resolved_session": 2.0, "resolution_rate": 0.9, "unresolved_cost_burn_total": 30.0, "total_cost_usd": 100.0},
            {"cost_per_resolved_session": 1.0, "resolution_rate": 0.8, "unresolved_cost_burn_total": 20.0, "total_cost_usd": 80.0},
        ],
        budget_rows=[
            {"post_optimizer_budget_utilization": 0.7, "optimizer_mode": "SOFT_CLAMP", "release_state": "HOLD"},
            {"post_optimizer_budget_utilization": 0.6, "optimizer_mode": "NORMAL", "release_state": "PROMOTE"},
        ],
        audit_summary={"top_reasons": []},
    )
    assert summary["report_count"] == 2
    assert abs(summary["avg_cost_per_resolved_session"] - 1.5) < 1e-9
    assert abs(summary["avg_resolution_rate"] - 0.85) < 1e-9
    assert summary["tradeoff_index"] > 0.0


def test_evaluate_gate_detects_tradeoff_regression():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "report_count": 5,
            "tradeoff_index": 0.1,
            "avg_cost_per_resolved_session": 3.0,
            "avg_unresolved_cost_burn_total": 250.0,
            "quality_drop_with_cost_cut": True,
        },
        min_reports=1,
        min_tradeoff_index=0.2,
        max_avg_cost_per_resolved_session=2.5,
        max_avg_unresolved_cost_burn_total=200.0,
    )
    assert len(failures) == 4


def test_evaluate_gate_passes_healthy_metrics():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "report_count": 3,
            "tradeoff_index": 0.4,
            "avg_cost_per_resolved_session": 1.8,
            "avg_unresolved_cost_burn_total": 120.0,
            "quality_drop_with_cost_cut": False,
        },
        min_reports=1,
        min_tradeoff_index=0.2,
        max_avg_cost_per_resolved_session=2.5,
        max_avg_unresolved_cost_burn_total=200.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_tradeoff_cost_quality_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "tradeoff_index": 0.40,
                "avg_cost_per_resolved_session": 1.50,
                "avg_unresolved_cost_burn_total": 80.0,
                "avg_budget_utilization": 0.60,
                "quality_drop_with_cost_cut": False,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "tradeoff_index": 0.30,
            "avg_cost_per_resolved_session": 2.20,
            "avg_unresolved_cost_burn_total": 160.0,
            "avg_budget_utilization": 0.72,
            "quality_drop_with_cost_cut": True,
        },
        max_tradeoff_index_drop=0.05,
        max_avg_cost_per_resolved_session_increase=0.50,
        max_avg_unresolved_cost_burn_total_increase=50.0,
        max_avg_budget_utilization_increase=0.05,
        max_quality_drop_with_cost_cut_increase=0,
    )
    assert len(failures) == 5
