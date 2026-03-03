import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_intervention_recovery_feedback_guard.py"
    spec = importlib.util.spec_from_file_location("chat_intervention_recovery_feedback_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_intervention_recovery_feedback_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intervention_triggered": True,
            "intervention_type": "SUMMARY_RECONFIRM",
            "pre_state": "AT_RISK",
            "post_state": "HEALTHY",
            "completion_before": 0.0,
            "completion_after": 1.0,
            "feedback_logged": True,
            "ineffective_streak": 0,
            "decay_applied": False,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intervention_triggered": True,
            "intervention_type": "SAFE_MODE",
            "pre_state": "DEGRADED",
            "post_state": "DEGRADED",
            "completion_before": 0.0,
            "completion_after": 0.0,
            "intervention_result": "NO_EFFECT",
            "feedback_logged": True,
            "ineffective_streak": 3,
            "decay_applied": False,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "intervention_triggered": True,
            "intervention_type": "OPEN_SUPPORT_TICKET",
            "pre_state": "DEGRADED",
            "post_state": "AT_RISK",
            "completion_before": 0.0,
            "completion_after": 1.0,
            "feedback_logged": False,
            "ineffective_streak": 1,
            "decay_applied": True,
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "intervention_triggered": False,
            "intervention_type": "",
        },
    ]
    summary = module.summarize_intervention_recovery_feedback_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
        decay_ineffective_streak_threshold=3,
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["intervention_total"] == 3
    assert summary["recovered_total"] == 2
    assert abs(summary["recovery_rate"] - (2.0 / 3.0)) < 1e-9
    assert abs(summary["mean_completion_before"] - 0.0) < 1e-9
    assert abs(summary["mean_completion_after"] - (2.0 / 3.0)) < 1e-9
    assert abs(summary["completion_uplift"] - (2.0 / 3.0)) < 1e-9
    assert summary["feedback_missing_total"] == 1
    assert summary["ineffective_total"] == 1
    assert summary["auto_decay_missing_total"] == 1
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_feedback_loop_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "recovery_rate": 0.1,
            "completion_uplift": -0.2,
            "feedback_missing_total": 2,
            "auto_decay_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_recovery_rate=0.95,
        min_completion_uplift=0.1,
        max_feedback_missing_total=0,
        max_auto_decay_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "recovery_rate": 1.0,
            "completion_uplift": 0.0,
            "feedback_missing_total": 0,
            "auto_decay_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_recovery_rate=0.0,
        min_completion_uplift=-1.0,
        max_feedback_missing_total=1000000,
        max_auto_decay_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
