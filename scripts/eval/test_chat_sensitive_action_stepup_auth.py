import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_sensitive_action_stepup_auth.py"
    spec = importlib.util.spec_from_file_location("chat_sensitive_action_stepup_auth", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_stepup_auth_flags_high_risk_execute_without_stepup():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-03T00:00:00Z", "action_id": "a1", "risk_level": "HIGH", "event_type": "execute"},
        {"timestamp": "2026-03-03T00:01:00Z", "action_id": "a2", "risk_level": "HIGH", "event_type": "stepup_challenge_issued"},
        {"timestamp": "2026-03-03T00:01:10Z", "action_id": "a2", "risk_level": "HIGH", "event_type": "stepup_failed"},
        {"timestamp": "2026-03-03T00:01:20Z", "action_id": "a2", "risk_level": "HIGH", "event_type": "handoff"},
    ]
    summary = module.summarize_stepup_auth(rows, now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc))
    assert summary["high_risk_total"] == 2
    assert summary["high_risk_execute_without_stepup_total"] == 1
    assert summary["stepup_failure_total"] == 1
    assert summary["stepup_failure_blocked_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "high_risk_execute_without_stepup_total": 1,
            "stepup_failed_then_execute_total": 1,
            "stepup_failure_block_ratio": 0.5,
            "stepup_latency_p95_sec": 500.0,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_high_risk_execute_without_stepup_total=0,
        max_stepup_failed_then_execute_total=0,
        min_stepup_failure_block_ratio=1.0,
        max_stepup_latency_p95_sec=300.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "high_risk_execute_without_stepup_total": 0,
            "stepup_failed_then_execute_total": 0,
            "stepup_failure_block_ratio": 1.0,
            "stepup_latency_p95_sec": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_high_risk_execute_without_stepup_total=0,
        max_stepup_failed_then_execute_total=0,
        min_stepup_failure_block_ratio=1.0,
        max_stepup_latency_p95_sec=300.0,
        max_stale_minutes=60.0,
    )
    assert failures == []
