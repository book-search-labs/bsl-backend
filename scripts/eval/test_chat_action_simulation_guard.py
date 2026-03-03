import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_action_simulation_guard.py"
    spec = importlib.util.spec_from_file_location("chat_action_simulation_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_action_simulation_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "action_type": "REFUND_REQUEST",
            "simulation_run": True,
            "estimated_refund_amount": 9000,
            "estimated_fee": 1000,
            "execution_done": True,
            "executed_refund_amount": 9050,
            "estimated_value": 9000,
            "executed_value": 9050,
            "policy_blocked": False,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "action_type": "SHIPPING_OPTION_CHANGE",
            "simulation_run": True,
            "estimated_shipping_fee": None,
            "estimated_arrival_days": 2,
            "policy_blocked": False,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "action_type": "REFUND_REQUEST",
            "simulation_run": True,
            "estimated_refund_amount": 5000,
            "estimated_fee": 500,
            "simulation_result": "BLOCKED",
            "alternative_paths": [],
            "next_action": "NONE",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "action_type": "",
            "simulation_run": False,
        },
    ]
    summary = module.summarize_action_simulation_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
        max_value_drift=30.0,
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["simulation_total"] == 3
    assert abs(summary["simulation_coverage_rate"] - 0.75) < 1e-9
    assert summary["refund_simulation_total"] == 2
    assert summary["shipping_option_simulation_total"] == 1
    assert summary["missing_estimate_fields_total"] == 1
    assert summary["policy_blocked_total"] == 1
    assert summary["policy_blocked_alt_path_missing_total"] == 1
    assert abs(summary["blocked_alt_path_ratio"] - 0.0) < 1e-9
    assert summary["execution_drift_total"] == 1
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_action_simulation_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "simulation_coverage_rate": 0.1,
            "blocked_alt_path_ratio": 0.2,
            "missing_estimate_fields_total": 2,
            "execution_drift_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_simulation_coverage_rate=0.8,
        min_blocked_alt_path_ratio=0.9,
        max_missing_estimate_fields_total=0,
        max_execution_drift_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "simulation_coverage_rate": 0.0,
            "blocked_alt_path_ratio": 1.0,
            "missing_estimate_fields_total": 0,
            "execution_drift_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_simulation_coverage_rate=0.0,
        min_blocked_alt_path_ratio=0.0,
        max_missing_estimate_fields_total=1000000,
        max_execution_drift_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
