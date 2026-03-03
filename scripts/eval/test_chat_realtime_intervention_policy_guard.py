import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_realtime_intervention_policy_guard.py"
    spec = importlib.util.spec_from_file_location("chat_realtime_intervention_policy_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_realtime_intervention_policy_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "session_state": "AT_RISK",
            "intervention_types": ["SUMMARY_RECONFIRM"],
            "intervention_triggered": True,
            "consecutive_failures": 1,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "session_state": "AT_RISK",
            "intervention_types": [],
            "intervention_triggered": False,
            "consecutive_failures": 2,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "session_state": "DEGRADED",
            "intervention_types": ["SAFE_MODE"],
            "intervention_triggered": True,
            "consecutive_failures": 3,
            "escalated": True,
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "session_state": "DEGRADED",
            "intervention_types": ["QUICK_ACTION_BUTTONS"],
            "intervention_triggered": True,
            "consecutive_failures": 3,
            "escalated": False,
        },
    ]
    summary = module.summarize_realtime_intervention_policy_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
        escalation_failure_threshold=3,
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["intervention_triggered_total"] == 3
    assert abs(summary["intervention_trigger_rate"] - 0.75) < 1e-9
    assert summary["at_risk_total"] == 2
    assert summary["degraded_total"] == 2
    assert summary["at_risk_intervention_missing_total"] == 1
    assert summary["degraded_intervention_missing_total"] == 1
    assert summary["escalation_required_total"] == 2
    assert summary["escalation_missing_total"] == 1
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_realtime_intervention_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "intervention_trigger_rate": 0.2,
            "at_risk_intervention_missing_total": 1,
            "degraded_intervention_missing_total": 1,
            "escalation_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_intervention_trigger_rate=0.95,
        max_at_risk_intervention_missing_total=0,
        max_degraded_intervention_missing_total=0,
        max_escalation_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "intervention_trigger_rate": 0.0,
            "at_risk_intervention_missing_total": 0,
            "degraded_intervention_missing_total": 0,
            "escalation_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_intervention_trigger_rate=0.0,
        max_at_risk_intervention_missing_total=1000000,
        max_degraded_intervention_missing_total=1000000,
        max_escalation_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
