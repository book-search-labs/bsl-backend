import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_session_gateway_durability.py"
    spec = importlib.util.spec_from_file_location("chat_session_gateway_durability", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_durability_tracks_resume_reconnect_heartbeat_and_affinity():
    module = _load_module()
    now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    rows = [
        {"timestamp": "2026-03-03T11:50:00Z", "event_type": "connect", "session_id": "s1"},
        {"timestamp": "2026-03-03T11:51:00Z", "event_type": "heartbeat", "session_id": "s1", "heartbeat_lag_ms": 1000},
        {"timestamp": "2026-03-03T11:52:00Z", "event_type": "heartbeat", "session_id": "s1", "heartbeat_lag_ms": 90000},
        {"timestamp": "2026-03-03T11:53:00Z", "event_type": "reconnect", "session_id": "s1", "success": True, "reconnect_reason": "network"},
        {"timestamp": "2026-03-03T11:54:00Z", "event_type": "resume", "session_id": "s1", "success": False, "affinity_miss": True},
    ]

    summary = module.summarize_durability(rows, heartbeat_lag_threshold_ms=30000.0, now=now)
    assert summary["window_size"] == 5
    assert summary["heartbeat_total"] == 2
    assert summary["heartbeat_miss_total"] == 1
    assert summary["reconnect_total"] == 1
    assert summary["reconnect_success_rate"] == 1.0
    assert summary["resume_total"] == 1
    assert summary["resume_success_rate"] == 0.0
    assert summary["affinity_miss_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "reconnect_success_rate": 0.8,
            "resume_success_rate": 0.7,
            "heartbeat_miss_ratio": 0.2,
            "affinity_miss_ratio": 0.1,
            "stale_minutes": 120,
        },
        min_window=1,
        min_reconnect_success_rate=0.95,
        min_resume_success_rate=0.98,
        max_heartbeat_miss_ratio=0.05,
        max_affinity_miss_ratio=0.02,
        max_stale_minutes=60,
    )
    assert len(failures) == 5


def test_evaluate_gate_passes_for_healthy_summary():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 20,
            "reconnect_success_rate": 1.0,
            "resume_success_rate": 1.0,
            "heartbeat_miss_ratio": 0.0,
            "affinity_miss_ratio": 0.0,
            "stale_minutes": 10,
        },
        min_window=1,
        min_reconnect_success_rate=0.95,
        min_resume_success_rate=0.98,
        max_heartbeat_miss_ratio=0.05,
        max_affinity_miss_ratio=0.02,
        max_stale_minutes=60,
    )
    assert failures == []
