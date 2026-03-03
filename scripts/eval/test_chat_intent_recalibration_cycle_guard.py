import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_intent_recalibration_cycle_guard.py"
    spec = importlib.util.spec_from_file_location("chat_intent_recalibration_cycle_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_intent_recalibration_cycle_guard_tracks_coverage_and_cadence():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-01-10T00:00:00Z",
            "intent": "ORDER_STATUS",
            "status": "SUCCESS",
            "threshold_updated": True,
        },
        {
            "timestamp": "2026-02-20T00:00:00Z",
            "intent": "ORDER_STATUS",
            "status": "SUCCESS",
            "threshold_updated": False,
        },
        {
            "timestamp": "2026-02-25T00:00:00Z",
            "intent": "REFUND_REQUEST",
            "status": "SUCCESS",
            "threshold_updated": True,
        },
        {
            "timestamp": "2026-02-28T00:00:00Z",
            "intent": "DELIVERY_TRACKING",
            "status": "SUCCESS",
            "threshold_updated": False,
        },
        {
            "timestamp": "2026-03-01T00:00:00Z",
            "intent": "POLICY_QA",
            "status": "FAILED",
            "threshold_updated": False,
        },
    ]
    summary = module.summarize_intent_recalibration_cycle_guard(
        rows,
        required_intents={"ORDER_STATUS", "REFUND_REQUEST", "DELIVERY_TRACKING", "POLICY_QA"},
        max_recalibration_age_days=35,
        now=datetime(2026, 3, 4, 0, 0, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["run_total"] == 5
    assert summary["successful_run_total"] == 4
    assert summary["failed_run_total"] == 1
    assert abs(summary["success_ratio"] - 0.8) < 1e-9
    assert summary["threshold_update_total"] == 2
    assert summary["required_intent_total"] == 4
    assert summary["covered_required_intent_total"] == 3
    assert abs(summary["required_intent_coverage_ratio"] - 0.75) < 1e-9
    assert summary["stale_intent_total"] == 1
    assert summary["stale_required_intents"] == ["POLICY_QA"]
    assert summary["cadence_violation_total"] == 1


def test_evaluate_gate_detects_intent_recalibration_cycle_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "run_total": 2,
            "success_ratio": 0.5,
            "required_intent_coverage_ratio": 0.4,
            "failed_run_total": 3,
            "stale_intent_total": 2,
            "cadence_violation_total": 2,
            "threshold_update_total": 0,
            "stale_minutes": 240.0,
        },
        min_window=10,
        min_run_total=3,
        min_success_ratio=0.9,
        min_required_intent_coverage_ratio=1.0,
        max_failed_run_total=0,
        max_stale_intent_total=0,
        max_cadence_violation_total=0,
        min_threshold_update_total=1,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "run_total": 0,
            "success_ratio": 1.0,
            "required_intent_coverage_ratio": 1.0,
            "failed_run_total": 0,
            "stale_intent_total": 0,
            "cadence_violation_total": 0,
            "threshold_update_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_run_total=0,
        min_success_ratio=0.0,
        min_required_intent_coverage_ratio=0.0,
        max_failed_run_total=1000000,
        max_stale_intent_total=1000000,
        max_cadence_violation_total=1000000,
        min_threshold_update_total=0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
