import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_reasoning_budget_adaptive_policy.py"
    spec = importlib.util.spec_from_file_location("chat_reasoning_budget_adaptive_policy", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_adaptive_policy_tracks_unsafe_expansion_and_preconfirm():
    module = _load_module()
    rows = [
        {
            "request_id": "r1",
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "adaptive_adjust",
            "intent": "REFUND_REQUEST",
            "adjustment_direction": "DECREASE",
            "before_success_rate": 0.70,
            "after_success_rate": 0.80,
            "before_cost_per_session": 2.0,
            "after_cost_per_session": 1.8,
            "preconfirm_required": True,
        },
        {
            "request_id": "r2",
            "timestamp": "2026-03-03T00:01:00Z",
            "event_type": "adaptive_adjust",
            "intent": "REFUND_REQUEST",
            "adjustment_direction": "INCREASE",
            "before_success_rate": 0.80,
            "after_success_rate": 0.75,
            "before_cost_per_session": 1.0,
            "after_cost_per_session": 1.4,
        },
        {
            "request_id": "r3",
            "timestamp": "2026-03-03T00:02:00Z",
            "event_type": "adaptive_adjust",
            "intent": "SEARCH",
            "adjustment_direction": "INCREASE",
            "before_success_rate": 0.90,
            "after_success_rate": 0.91,
            "before_cost_per_session": 0.5,
            "after_cost_per_session": 0.6,
        },
    ]

    summary = module.summarize_adaptive_policy(
        rows,
        high_cost_intents={"REFUND_REQUEST", "CANCEL_ORDER", "PAYMENT_CHANGE"},
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 3
    assert summary["adjustment_total"] == 3
    assert summary["unsafe_expansion_total"] == 1
    assert summary["high_cost_request_total"] == 2
    assert summary["preconfirm_missing_total"] >= 1
    assert summary["preconfirm_coverage_ratio"] <= 0.5


def test_evaluate_gate_detects_policy_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "unsafe_expansion_total": 3,
            "preconfirm_missing_total": 2,
            "preconfirm_coverage_ratio": 0.4,
            "success_regression_ratio": 0.5,
            "cost_regression_ratio": 0.6,
            "stale_minutes": 120.0,
        },
        min_window=20,
        max_unsafe_expansion_total=0,
        max_preconfirm_missing_total=0,
        min_preconfirm_coverage_ratio=0.9,
        max_success_regression_ratio=0.2,
        max_cost_regression_ratio=0.2,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_open_thresholds():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "unsafe_expansion_total": 0,
            "preconfirm_missing_total": 0,
            "preconfirm_coverage_ratio": 1.0,
            "success_regression_ratio": 0.0,
            "cost_regression_ratio": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_unsafe_expansion_total=1000000,
        max_preconfirm_missing_total=1000000,
        min_preconfirm_coverage_ratio=0.0,
        max_success_regression_ratio=1.0,
        max_cost_regression_ratio=1.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_adaptive_policy_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "unsafe_expansion_total": 0,
            "preconfirm_missing_total": 0,
            "preconfirm_coverage_ratio": 1.0,
            "success_regression_ratio": 0.0,
            "cost_regression_ratio": 0.0,
            "rollback_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "unsafe_expansion_total": 2,
            "preconfirm_missing_total": 3,
            "preconfirm_coverage_ratio": 0.4,
            "success_regression_ratio": 0.5,
            "cost_regression_ratio": 0.6,
            "rollback_total": 4,
            "stale_minutes": 80.0,
        },
        max_unsafe_expansion_total_increase=0,
        max_preconfirm_missing_total_increase=0,
        max_preconfirm_coverage_ratio_drop=0.05,
        max_success_regression_ratio_increase=0.05,
        max_cost_regression_ratio_increase=0.05,
        max_rollback_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("unsafe_expansion_total regression" in item for item in failures)
    assert any("preconfirm_missing_total regression" in item for item in failures)
    assert any("preconfirm_coverage_ratio regression" in item for item in failures)
    assert any("success_regression_ratio regression" in item for item in failures)
    assert any("cost_regression_ratio regression" in item for item in failures)
    assert any("rollback_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
