import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_workflow_plan_execute.py"
    spec = importlib.util.spec_from_file_location("chat_workflow_plan_execute", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_plan_execute_tracks_sequence_and_reentry():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-03T00:00:00Z", "workflow_id": "w1", "phase": "INTENT_CONFIRM", "result": "ok"},
        {"timestamp": "2026-03-03T00:00:05Z", "workflow_id": "w1", "phase": "INPUT_COLLECTION", "result": "ok"},
        {"timestamp": "2026-03-03T00:00:10Z", "workflow_id": "w1", "phase": "VALIDATION", "result": "ok"},
        {"timestamp": "2026-03-03T00:00:15Z", "workflow_id": "w1", "phase": "EXECUTE", "result": "ok"},
        {"timestamp": "2026-03-03T00:01:00Z", "workflow_id": "w2", "phase": "INPUT_COLLECTION", "result": "failed"},
        {"timestamp": "2026-03-03T00:01:10Z", "workflow_id": "w2", "phase": "VALIDATION", "result": "ok", "reentry_attempt": True},
        {"timestamp": "2026-03-03T00:01:15Z", "workflow_id": "w2", "phase": "EXECUTE", "result": "ok", "reentry_success": True},
    ]
    summary = module.summarize_plan_execute(
        rows,
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )
    assert summary["workflow_total"] == 2
    assert summary["step_error_total"] == 1
    assert summary["reentry_attempt_total"] == 1
    assert summary["reentry_success_total"] == 1
    assert summary["validation_before_execute_ratio"] == 1.0


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "sequence_valid_ratio": 0.5,
            "validation_before_execute_ratio": 0.5,
            "step_error_total": 3,
            "reentry_success_ratio": 0.4,
            "stale_minutes": 120.0,
        },
        min_window=1,
        min_sequence_valid_ratio=0.95,
        min_validation_before_execute_ratio=0.99,
        max_step_error_total=0,
        min_reentry_success_ratio=0.8,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_passes_when_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "sequence_valid_ratio": 1.0,
            "validation_before_execute_ratio": 1.0,
            "step_error_total": 0,
            "reentry_success_ratio": 1.0,
            "stale_minutes": 5.0,
        },
        min_window=1,
        min_sequence_valid_ratio=0.95,
        min_validation_before_execute_ratio=0.99,
        max_step_error_total=0,
        min_reentry_success_ratio=0.8,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "sequence_valid_ratio": 0.0,
            "validation_before_execute_ratio": 0.0,
            "step_error_total": 0,
            "reentry_success_ratio": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_sequence_valid_ratio=0.95,
        min_validation_before_execute_ratio=0.99,
        max_step_error_total=0,
        min_reentry_success_ratio=0.8,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_plan_execute_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "sequence_valid_ratio": 1.0,
                "validation_before_execute_ratio": 1.0,
                "step_error_total": 0,
                "reentry_success_ratio": 1.0,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "sequence_valid_ratio": 0.9,
            "validation_before_execute_ratio": 0.8,
            "step_error_total": 2,
            "reentry_success_ratio": 0.7,
            "stale_minutes": 50.0,
        },
        max_sequence_valid_ratio_drop=0.05,
        max_validation_before_execute_ratio_drop=0.05,
        max_step_error_total_increase=0,
        max_reentry_success_ratio_drop=0.10,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 5
