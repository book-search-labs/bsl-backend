import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_sensitive_action_double_confirmation.py"
    spec = importlib.util.spec_from_file_location("chat_sensitive_action_double_confirmation", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_double_confirmation_flags_unconfirmed_execute():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-03T00:00:00Z", "action_id": "a1", "risk_level": "HIGH", "event_type": "request"},
        {"timestamp": "2026-03-03T00:00:01Z", "action_id": "a1", "risk_level": "HIGH", "event_type": "confirm1_received"},
        {"timestamp": "2026-03-03T00:00:02Z", "action_id": "a1", "risk_level": "HIGH", "event_type": "execute"},
        {"timestamp": "2026-03-03T00:01:00Z", "action_id": "a2", "risk_level": "HIGH", "event_type": "request"},
        {"timestamp": "2026-03-03T00:01:01Z", "action_id": "a2", "risk_level": "HIGH", "event_type": "confirm1_received"},
        {"timestamp": "2026-03-03T00:01:02Z", "action_id": "a2", "risk_level": "HIGH", "event_type": "confirm2_received"},
        {"timestamp": "2026-03-03T00:01:03Z", "action_id": "a2", "risk_level": "HIGH", "event_type": "token_issued"},
        {"timestamp": "2026-03-03T00:01:04Z", "action_id": "a2", "risk_level": "HIGH", "event_type": "token_validated"},
        {"timestamp": "2026-03-03T00:01:05Z", "action_id": "a2", "risk_level": "HIGH", "event_type": "execute"},
    ]
    summary = module.summarize_double_confirmation(rows, now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc))
    assert summary["two_step_required_total"] == 2
    assert summary["execute_without_double_confirmation_total"] == 1
    assert summary["token_missing_on_execute_total"] == 1
    assert summary["token_validation_ratio"] == 1.0


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "execute_without_double_confirmation_total": 1,
            "token_missing_on_execute_total": 1,
            "token_reuse_total": 1,
            "token_mismatch_total": 1,
            "token_expired_total": 1,
            "token_validation_ratio": 0.5,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_execute_without_double_confirmation_total=0,
        max_token_missing_on_execute_total=0,
        max_token_reuse_total=0,
        max_token_mismatch_total=0,
        max_token_expired_total=0,
        min_token_validation_ratio=0.95,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "execute_without_double_confirmation_total": 0,
            "token_missing_on_execute_total": 0,
            "token_reuse_total": 0,
            "token_mismatch_total": 0,
            "token_expired_total": 0,
            "token_validation_ratio": 1.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_execute_without_double_confirmation_total=0,
        max_token_missing_on_execute_total=0,
        max_token_reuse_total=0,
        max_token_mismatch_total=0,
        max_token_expired_total=0,
        min_token_validation_ratio=0.95,
        max_stale_minutes=60.0,
    )
    assert failures == []
