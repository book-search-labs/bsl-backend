import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_workflow_confirmation_checkpoint.py"
    spec = importlib.util.spec_from_file_location("chat_workflow_confirmation_checkpoint", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_confirmation_checkpoint_tracks_sensitive_guard():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-03T00:00:00Z", "workflow_id": "w1", "workflow_type": "REFUND_REQUEST", "event_type": "confirm_requested"},
        {"timestamp": "2026-03-03T00:00:10Z", "workflow_id": "w1", "workflow_type": "REFUND_REQUEST", "event_type": "confirmed"},
        {"timestamp": "2026-03-03T00:00:20Z", "workflow_id": "w1", "workflow_type": "REFUND_REQUEST", "event_type": "execute"},
        {"timestamp": "2026-03-03T00:01:00Z", "workflow_id": "w2", "workflow_type": "REFUND_REQUEST", "event_type": "execute"},
        {"timestamp": "2026-03-03T00:02:00Z", "workflow_id": "w3", "workflow_type": "REFUND_REQUEST", "event_type": "timeout"},
        {"timestamp": "2026-03-03T00:02:05Z", "workflow_id": "w3", "workflow_type": "REFUND_REQUEST", "event_type": "auto_cancelled"},
    ]
    summary = module.summarize_confirmation_checkpoint(
        rows,
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )
    assert summary["workflow_total"] == 3
    assert summary["sensitive_execute_total"] == 2
    assert summary["execute_without_confirmation_total"] == 1
    assert summary["timeout_auto_cancel_ratio"] == 1.0


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "execute_without_confirmation_total": 2,
            "timeout_auto_cancel_ratio": 0.5,
            "confirmation_latency_p95_sec": 500.0,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_execute_without_confirmation_total=0,
        min_timeout_auto_cancel_ratio=1.0,
        max_confirmation_latency_p95_sec=300.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 4


def test_evaluate_gate_passes_when_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "execute_without_confirmation_total": 0,
            "timeout_auto_cancel_ratio": 1.0,
            "confirmation_latency_p95_sec": 30.0,
            "stale_minutes": 5.0,
        },
        min_window=1,
        max_execute_without_confirmation_total=0,
        min_timeout_auto_cancel_ratio=1.0,
        max_confirmation_latency_p95_sec=300.0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "execute_without_confirmation_total": 0,
            "timeout_auto_cancel_ratio": 0.0,
            "confirmation_latency_p95_sec": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_execute_without_confirmation_total=0,
        min_timeout_auto_cancel_ratio=1.0,
        max_confirmation_latency_p95_sec=300.0,
        max_stale_minutes=60.0,
    )
    assert failures == []
