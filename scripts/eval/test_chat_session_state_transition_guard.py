import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_session_state_transition_guard.py"
    spec = importlib.util.spec_from_file_location("chat_session_state_transition_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_session_state_transition_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "session_id": "s1",
            "session_quality_score": 0.90,
            "expected_state": "HEALTHY",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "session_id": "s1",
            "session_quality_score": 0.60,
            "expected_state": "AT_RISK",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "session_id": "s1",
            "session_quality_score": 0.30,
            "expected_state": "DEGRADED",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "session_id": "s1",
            "session_quality_score": 0.90,
            "expected_state": "HEALTHY",
        },
        {
            "timestamp": "2026-03-04T00:00:40Z",
            "session_id": "s2",
            "session_quality_score": 0.60,
            "expected_state": "HEALTHY",
            "false_alarm": True,
        },
    ]
    summary = module.summarize_session_state_transition_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 5
    assert summary["event_total"] == 5
    assert summary["classified_total"] == 5
    assert summary["state_healthy_total"] == 2
    assert summary["state_at_risk_total"] == 2
    assert summary["state_degraded_total"] == 1
    assert summary["state_mismatch_total"] == 1
    assert summary["invalid_transition_total"] == 1
    assert summary["false_alarm_total"] == 1
    assert abs(summary["stale_minutes"] - (1.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_state_transition_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "state_mismatch_total": 2,
            "invalid_transition_total": 1,
            "false_alarm_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        max_state_mismatch_total=0,
        max_invalid_transition_total=0,
        max_false_alarm_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "state_mismatch_total": 0,
            "invalid_transition_total": 0,
            "false_alarm_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        max_state_mismatch_total=1000000,
        max_invalid_transition_total=1000000,
        max_false_alarm_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
