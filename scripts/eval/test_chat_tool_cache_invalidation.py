import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_cache_invalidation.py"
    spec = importlib.util.spec_from_file_location("chat_tool_cache_invalidation", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_cache_invalidation_flags_coverage_and_lag():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-03T00:00:00Z", "event_type": "order_status_event", "order_id": "o1"},
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "event_type": "cache_invalidate",
            "order_id": "o1",
            "reason": "ORDER_STATUS_UPDATED",
        },
        {"timestamp": "2026-03-03T00:02:00Z", "event_type": "order_status_event", "order_id": "o2"},
        {
            "timestamp": "2026-03-03T00:20:00Z",
            "event_type": "cache_invalidate",
            "order_id": "o2",
            "reason": "ORDER_STATUS_UPDATED",
        },
        {"timestamp": "2026-03-03T00:03:00Z", "event_type": "shipping_status_event", "shipment_id": ""},
        {"timestamp": "2026-03-03T00:04:00Z", "event_type": "cache_invalidate", "order_id": "o3", "reason": ""},
        {"timestamp": "2026-03-03T00:05:00Z", "event_type": "order_status_event", "order_id": "o4"},
    ]
    summary = module.summarize_cache_invalidation(
        rows,
        max_invalidate_lag_minutes=5.0,
        now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
    )
    assert summary["domain_event_total"] == 4
    assert summary["invalidate_total"] == 3
    assert summary["domain_key_missing_total"] == 1
    assert summary["invalidation_reason_missing_total"] == 1
    assert summary["missing_invalidate_total"] == 1
    assert summary["late_invalidate_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "domain_event_total": 10,
            "coverage_ratio": 0.5,
            "domain_key_missing_total": 1,
            "invalidation_reason_missing_total": 1,
            "missing_invalidate_total": 1,
            "late_invalidate_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        min_coverage_ratio=0.95,
        max_domain_key_missing_total=0,
        max_invalidation_reason_missing_total=0,
        max_missing_invalidate_total=0,
        max_late_invalidate_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "domain_event_total": 0,
            "coverage_ratio": 1.0,
            "domain_key_missing_total": 0,
            "invalidation_reason_missing_total": 0,
            "missing_invalidate_total": 0,
            "late_invalidate_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_coverage_ratio=0.95,
        max_domain_key_missing_total=0,
        max_invalidation_reason_missing_total=0,
        max_missing_invalidate_total=0,
        max_late_invalidate_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []
