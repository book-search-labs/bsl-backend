import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_actionability_repair_loop_guard.py"
    spec = importlib.util.spec_from_file_location("chat_actionability_repair_loop_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_actionability_repair_loop_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intent": "REFUND_REQUEST",
            "actionability_score_before": 0.4,
            "repair_triggered": True,
            "repair_attempts": 1,
            "repair_result": "SUCCESS",
            "missing_slots_before": ["order_id", "fee"],
            "missing_slots_after": [],
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intent": "ORDER_CANCEL",
            "actionability_score_before": 0.5,
            "repair_triggered": True,
            "repair_attempts": 2,
            "repair_result": "FAILED",
            "fail_closed_enforced": True,
            "missing_slot_count_before": 1,
            "missing_slot_count_after": 1,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "intent": "SHIPPING_TRACK",
            "actionability_score_before": 0.2,
            "repair_triggered": False,
            "repair_attempts": 0,
            "repair_result": "NONE",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "intent": "FAQ",
            "actionability_score_before": 0.9,
            "repair_triggered": False,
            "repair_attempts": 0,
        },
    ]
    summary = module.summarize_actionability_repair_loop_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
        max_repair_attempts=2,
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["repair_required_total"] == 3
    assert summary["repair_triggered_total"] == 2
    assert abs(summary["repair_trigger_coverage_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["repair_success_total"] == 1
    assert summary["repair_failed_total"] == 1
    assert summary["repair_fail_closed_total"] == 1
    assert abs(summary["repair_success_rate"] - 0.5) < 1e-9
    assert summary["repair_trigger_missing_total"] == 1
    assert summary["fail_closed_missing_total"] == 0
    assert summary["slot_gap_before_total"] == 3
    assert summary["slot_gap_after_total"] == 1
    assert summary["slot_gap_reduced_total"] == 1
    assert abs(summary["slot_gap_reduction_ratio"] - 0.5) < 1e-9
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_repair_loop_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "repair_trigger_coverage_ratio": 0.2,
            "repair_success_rate": 0.1,
            "fail_closed_enforcement_ratio": 0.3,
            "slot_gap_reduction_ratio": 0.2,
            "repair_trigger_missing_total": 4,
            "fail_closed_missing_total": 3,
            "attempt_limit_violation_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_repair_trigger_coverage_ratio=0.95,
        min_repair_success_rate=0.80,
        min_fail_closed_enforcement_ratio=1.0,
        min_slot_gap_reduction_ratio=0.5,
        max_repair_trigger_missing_total=0,
        max_fail_closed_missing_total=0,
        max_attempt_limit_violation_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "repair_trigger_coverage_ratio": 1.0,
            "repair_success_rate": 1.0,
            "fail_closed_enforcement_ratio": 1.0,
            "slot_gap_reduction_ratio": 1.0,
            "repair_trigger_missing_total": 0,
            "fail_closed_missing_total": 0,
            "attempt_limit_violation_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_repair_trigger_coverage_ratio=0.0,
        min_repair_success_rate=0.0,
        min_fail_closed_enforcement_ratio=0.0,
        min_slot_gap_reduction_ratio=0.0,
        max_repair_trigger_missing_total=1000000,
        max_fail_closed_missing_total=1000000,
        max_attempt_limit_violation_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
