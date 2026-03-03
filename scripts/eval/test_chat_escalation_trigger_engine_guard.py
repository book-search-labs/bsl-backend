import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_escalation_trigger_engine_guard.py"
    spec = importlib.util.spec_from_file_location("chat_escalation_trigger_engine_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_escalation_trigger_engine_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "failure_count_recent": 4,
            "escalation_triggered": True,
            "threshold_version": "v1",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "reason_code": "PAYMENT_FAILURE",
            "escalation_triggered": False,
            "cooldown_active": True,
            "threshold_version": "v1",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "dissatisfaction_signal": True,
            "escalation_triggered": False,
            "cooldown_active": False,
            "hysteresis_applied": False,
            "threshold_version": "v1",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "failure_count_recent": 0,
            "high_risk_reason": False,
            "dissatisfaction_signal": False,
            "escalation_triggered": True,
            "threshold_version": "v1",
        },
        {
            "timestamp": "2026-03-04T00:00:40Z",
            "dissatisfaction_signal": True,
            "escalation_triggered": False,
            "hysteresis_applied": True,
            "threshold_version": "",
        },
    ]
    summary = module.summarize_escalation_trigger_engine_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
        failure_threshold=3,
    )
    assert summary["window_size"] == 5
    assert summary["event_total"] == 5
    assert summary["candidate_total"] == 4
    assert summary["escalation_triggered_total"] == 2
    assert summary["trigger_missed_total"] == 1
    assert summary["cooldown_suppressed_total"] == 1
    assert summary["hysteresis_suppressed_total"] == 1
    assert summary["false_positive_total"] == 1
    assert abs(summary["trigger_recall"] - 0.25) < 1e-9
    assert abs(summary["false_positive_rate"] - 0.5) < 1e-9
    assert summary["threshold_version_missing_total"] == 1
    assert abs(summary["stale_minutes"] - (1.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_escalation_trigger_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "trigger_recall": 0.3,
            "trigger_missed_total": 5,
            "false_positive_rate": 0.5,
            "threshold_version_missing_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_trigger_recall=0.9,
        max_trigger_missed_total=0,
        max_false_positive_rate=0.1,
        max_threshold_version_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "trigger_recall": 1.0,
            "trigger_missed_total": 0,
            "false_positive_rate": 0.0,
            "threshold_version_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_trigger_recall=0.0,
        max_trigger_missed_total=1000000,
        max_false_positive_rate=1.0,
        max_threshold_version_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
