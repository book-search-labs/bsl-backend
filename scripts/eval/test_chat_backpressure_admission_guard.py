import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_backpressure_admission_guard.py"
    spec = importlib.util.spec_from_file_location("chat_backpressure_admission_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_backpressure_tracks_drop_core_protection_and_guidance():
    module = _load_module()
    now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    rows = [
        {"timestamp": "2026-03-03T11:50:00Z", "priority": "critical", "admitted": True, "dropped": False, "queue_depth": 10, "queue_latency_ms": 300, "core_intent": True},
        {"timestamp": "2026-03-03T11:51:00Z", "priority": "low", "admitted": False, "dropped": True, "queue_depth": 100, "queue_latency_ms": 4500, "backpressure_mode": "OPEN", "circuit_open": True, "user_guidance_sent": False},
    ]

    summary = module.summarize_backpressure(rows, now=now)
    assert summary["window_size"] == 2
    assert summary["drop_total"] == 1
    assert summary["critical_drop_total"] == 0
    assert summary["core_protected_ratio"] == 1.0
    assert summary["guidance_missing_total"] == 1


def test_evaluate_gate_detects_threshold_violations():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "drop_ratio": 0.3,
            "critical_drop_total": 2,
            "core_protected_ratio": 0.7,
            "p95_queue_depth": 120,
            "p95_queue_latency_ms": 6000,
            "guidance_missing_total": 1,
            "stale_minutes": 120,
        },
        min_window=1,
        max_drop_ratio=0.2,
        max_critical_drop_total=0,
        min_core_protected_ratio=0.98,
        max_p95_queue_depth=80,
        max_p95_queue_latency_ms=3000,
        max_guidance_missing_total=0,
        max_stale_minutes=60,
    )
    assert len(failures) == 7


def test_evaluate_gate_passes_when_within_thresholds():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 20,
            "drop_ratio": 0.05,
            "critical_drop_total": 0,
            "core_protected_ratio": 1.0,
            "p95_queue_depth": 30,
            "p95_queue_latency_ms": 800,
            "guidance_missing_total": 0,
            "stale_minutes": 5,
        },
        min_window=1,
        max_drop_ratio=0.2,
        max_critical_drop_total=0,
        min_core_protected_ratio=0.98,
        max_p95_queue_depth=80,
        max_p95_queue_latency_ms=3000,
        max_guidance_missing_total=0,
        max_stale_minutes=60,
    )
    assert failures == []
