import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_execution_safety_contract_guard.py"
    spec = importlib.util.spec_from_file_location("chat_execution_safety_contract_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_execution_safety_contract_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "action_type": "REFUND_EXECUTE",
            "risk_level": "WRITE_SENSITIVE",
            "preflight_checks": {"authz": True, "inventory": True, "state_transition": True},
            "preflight_passed": True,
            "execution_attempted": True,
            "idempotency_key": "k1",
            "simulated_value": 1000.0,
            "executed_value": 1000.0,
            "execution_status": "EXECUTED",
            "duplicate_request": False,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "action_type": "REFUND_EXECUTE",
            "risk_level": "WRITE_SENSITIVE",
            "preflight_checks": {"authz": False, "inventory": True},
            "preflight_passed": False,
            "execution_attempted": True,
            "idempotency_key": "",
            "simulated_value": 1000.0,
            "executed_value": 1200.0,
            "execution_status": "FAILED",
            "execution_aborted": False,
            "ops_alert_sent": False,
            "duplicate_request": True,
            "idempotency_replayed": False,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "action_type": "SHIPPING_OPTION_CHANGE",
            "risk_level": "WRITE",
            "preflight_checks": {"authz": True, "inventory": True, "state_transition": True},
            "preflight_passed": True,
            "execution_attempted": False,
            "idempotency_key": "k3",
            "duplicate_request": True,
            "idempotency_replayed": True,
        },
    ]
    summary = module.summarize_execution_safety_contract_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
        max_outcome_drift=50.0,
    )
    assert summary["window_size"] == 3
    assert summary["event_total"] == 3
    assert summary["write_action_total"] == 3
    assert summary["preflight_checked_total"] == 2
    assert abs(summary["preflight_check_coverage_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["missing_preflight_checks_total"] == 1
    assert summary["preflight_block_violation_total"] == 1
    assert summary["simulation_mismatch_total"] == 1
    assert summary["mismatch_abort_missing_total"] == 1
    assert summary["mismatch_alert_missing_total"] == 1
    assert summary["idempotency_missing_total"] == 1
    assert abs(summary["idempotency_coverage_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["duplicate_unsafe_total"] == 1
    assert abs(summary["stale_minutes"] - (2.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_execution_safety_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "preflight_check_coverage_ratio": 0.2,
            "idempotency_coverage_ratio": 0.3,
            "preflight_block_violation_total": 2,
            "mismatch_abort_missing_total": 1,
            "mismatch_alert_missing_total": 1,
            "duplicate_unsafe_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_preflight_check_coverage_ratio=0.95,
        min_idempotency_coverage_ratio=1.0,
        max_preflight_block_violation_total=0,
        max_mismatch_abort_missing_total=0,
        max_mismatch_alert_missing_total=0,
        max_duplicate_unsafe_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "preflight_check_coverage_ratio": 1.0,
            "idempotency_coverage_ratio": 1.0,
            "preflight_block_violation_total": 0,
            "mismatch_abort_missing_total": 0,
            "mismatch_alert_missing_total": 0,
            "duplicate_unsafe_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_preflight_check_coverage_ratio=0.0,
        min_idempotency_coverage_ratio=0.0,
        max_preflight_block_violation_total=1000000,
        max_mismatch_abort_missing_total=1000000,
        max_mismatch_alert_missing_total=1000000,
        max_duplicate_unsafe_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
