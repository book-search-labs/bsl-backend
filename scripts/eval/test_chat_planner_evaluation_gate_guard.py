import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_planner_evaluation_gate_guard.py"
    spec = importlib.util.spec_from_file_location("chat_planner_evaluation_gate_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_planner_evaluation_gate_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intent": "ORDER",
            "sample_count": 50,
            "path_deviation_rate": 0.05,
            "stage_omission_rate": 0.02,
            "wrong_escalation_rate": 0.01,
            "release_decision": "ALLOW",
            "partial_rollback_applied": False,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intent": "REFUND",
            "sample_count": 50,
            "path_deviation_rate": 0.20,
            "stage_omission_rate": 0.05,
            "wrong_escalation_rate": 0.02,
            "release_decision": "ALLOW",
            "partial_rollback_applied": False,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "intent": "SHIPPING",
            "path_deviation": True,
            "stage_omission": True,
            "wrong_escalation": False,
            "release_decision": "BLOCK",
            "partial_rollback_applied": True,
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "intent": "GENERAL",
            "sample_count": 20,
            "path_deviation_rate": 0.01,
            "stage_omission_rate": 0.01,
            "wrong_escalation_rate": 0.0,
            "release_decision": "BLOCK",
        },
    ]
    summary = module.summarize_planner_evaluation_gate_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
        max_path_deviation_rate=0.10,
        max_stage_omission_rate=0.05,
        max_wrong_escalation_rate=0.03,
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert abs(summary["sample_total"] - 121.0) < 1e-9
    assert abs(summary["path_deviation_rate"] - (13.2 / 121.0)) < 1e-9
    assert abs(summary["stage_omission_rate"] - (4.7 / 121.0)) < 1e-9
    assert abs(summary["wrong_escalation_rate"] - (1.5 / 121.0)) < 1e-9
    assert summary["missed_release_block_total"] == 1
    assert summary["partial_rollback_missing_total"] == 1
    assert summary["false_release_block_total"] == 1
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_planner_evaluation_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "path_deviation_rate": 0.2,
            "stage_omission_rate": 0.1,
            "wrong_escalation_rate": 0.08,
            "missed_release_block_total": 2,
            "false_release_block_total": 1,
            "partial_rollback_missing_total": 3,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        max_path_deviation_rate=0.1,
        max_stage_omission_rate=0.05,
        max_wrong_escalation_rate=0.03,
        max_missed_release_block_total=0,
        max_false_release_block_total=0,
        max_partial_rollback_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "path_deviation_rate": 0.0,
            "stage_omission_rate": 0.0,
            "wrong_escalation_rate": 0.0,
            "missed_release_block_total": 0,
            "false_release_block_total": 0,
            "partial_rollback_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        max_path_deviation_rate=1.0,
        max_stage_omission_rate=1.0,
        max_wrong_escalation_rate=1.0,
        max_missed_release_block_total=1000000,
        max_false_release_block_total=1000000,
        max_partial_rollback_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
