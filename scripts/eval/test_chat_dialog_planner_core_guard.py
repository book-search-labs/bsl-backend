import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_dialog_planner_core_guard.py"
    spec = importlib.util.spec_from_file_location("chat_dialog_planner_core_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_dialog_planner_core_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "from_state": "INIT",
            "to_state": "CONFIRM",
            "transition_result": "SUCCESS",
            "policy_guard_passed": True,
            "required_slots": ["order_id"],
            "provided_slots": ["order_id"],
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "from_state": "JUDGE",
            "to_state": "EXECUTE",
            "transition_result": "SUCCESS",
            "policy_blocked": True,
            "required_slots": ["refund_fee"],
            "provided_slots": ["refund_fee"],
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "from_state": "ASK",
            "to_state": "JUDGE",
            "transition_result": "SUCCESS",
            "policy_guard_passed": True,
            "required_slots": ["order_id", "received"],
            "provided_slots": ["order_id"],
            "question_strategy_applied": False,
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "from_state": "EXECUTE",
            "to_state": "CONFIRM",
            "transition_result": "SUCCESS",
            "policy_guard_passed": True,
            "required_slots": [],
            "provided_slots": [],
        },
    ]
    summary = module.summarize_dialog_planner_core_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["transition_total"] == 4
    assert summary["valid_transition_total"] == 3
    assert summary["invalid_transition_total"] == 1
    assert abs(summary["valid_transition_ratio"] - 0.75) < 1e-9
    assert summary["policy_blocked_total"] == 1
    assert summary["policy_block_violation_total"] == 1
    assert summary["missing_required_slots_total"] == 1
    assert summary["missing_slot_question_missing_total"] == 1
    assert abs(summary["missing_slot_question_coverage_ratio"] - 0.0) < 1e-9
    assert summary["planner_path_deviation_total"] == 1
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_dialog_planner_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "valid_transition_ratio": 0.2,
            "missing_slot_question_coverage_ratio": 0.3,
            "invalid_transition_total": 5,
            "policy_block_violation_total": 2,
            "missing_slot_question_missing_total": 3,
            "planner_path_deviation_total": 7,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_valid_transition_ratio=0.95,
        min_missing_slot_question_coverage_ratio=0.9,
        max_invalid_transition_total=0,
        max_policy_block_violation_total=0,
        max_missing_slot_question_missing_total=0,
        max_planner_path_deviation_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "valid_transition_ratio": 1.0,
            "missing_slot_question_coverage_ratio": 1.0,
            "invalid_transition_total": 0,
            "policy_block_violation_total": 0,
            "missing_slot_question_missing_total": 0,
            "planner_path_deviation_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_valid_transition_ratio=0.0,
        min_missing_slot_question_coverage_ratio=0.0,
        max_invalid_transition_total=1000000,
        max_policy_block_violation_total=1000000,
        max_missing_slot_question_missing_total=1000000,
        max_planner_path_deviation_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
