import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_cache_safety_fallback.py"
    spec = importlib.util.spec_from_file_location("chat_tool_cache_safety_fallback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_safety_fallback_flags_unhandled_and_fail_open():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-03T00:00:00Z", "event_type": "cache_corruption_detected", "incident_id": "i1"},
        {
            "timestamp": "2026-03-03T00:00:01Z",
            "event_type": "cache_fallback_origin",
            "incident_id": "i1",
            "success": True,
        },
        {"timestamp": "2026-03-03T00:01:00Z", "event_type": "cache_corruption_detected", "incident_id": "i2"},
        {"timestamp": "2026-03-03T00:01:01Z", "event_type": "cache_fail_open", "incident_id": "i2"},
        {"timestamp": "2026-03-03T00:02:00Z", "event_type": "cache_corruption_detected", "incident_id": "i3"},
        {"timestamp": "2026-03-03T00:02:01Z", "event_type": "recovery_failed", "incident_id": "i3"},
    ]
    summary = module.summarize_safety_fallback(rows, now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc))
    assert summary["corruption_detected_total"] == 3
    assert summary["origin_fallback_total"] == 1
    assert summary["fail_open_total"] == 1
    assert summary["recovery_failed_total"] == 1
    assert summary["corruption_unhandled_total"] == 2


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "corruption_detected_total": 10,
            "corruption_unhandled_total": 1,
            "fail_open_total": 1,
            "recovery_success_ratio": 0.4,
            "recovery_failed_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_corruption_unhandled_total=0,
        max_fail_open_total=0,
        min_recovery_success_ratio=0.95,
        max_recovery_failed_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "corruption_detected_total": 0,
            "corruption_unhandled_total": 0,
            "fail_open_total": 0,
            "recovery_success_ratio": 1.0,
            "recovery_failed_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_corruption_unhandled_total=0,
        max_fail_open_total=0,
        min_recovery_success_ratio=0.95,
        max_recovery_failed_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []
