import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_event_delivery_guarantee.py"
    spec = importlib.util.spec_from_file_location("chat_event_delivery_guarantee", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_delivery_tracks_order_duplicates_ack_and_sync_gap():
    module = _load_module()
    now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    rows = [
        {"timestamp": "2026-03-03T11:50:00Z", "session_id": "s1", "event_seq": 1, "expected_seq": 1, "delivered": True, "acked": True},
        {"timestamp": "2026-03-03T11:51:00Z", "session_id": "s1", "event_seq": 1, "expected_seq": 2, "delivered": True, "acked": False, "duplicate": True, "redelivery_count": 1},
        {"timestamp": "2026-03-03T11:52:00Z", "session_id": "s1", "event_seq": 3, "expected_seq": 3, "delivered": False, "acked": False, "sync_gap_events": 9, "reason_code": "TTL_EXPIRED"},
    ]

    summary = module.summarize_delivery(rows, now=now)
    assert summary["window_size"] == 3
    assert summary["order_violation_total"] >= 2
    assert summary["duplicate_total"] == 1
    assert summary["ack_missing_total"] == 2
    assert summary["max_sync_gap"] == 9
    assert summary["ttl_drop_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "delivery_success_ratio": 0.9,
            "order_violation_total": 2,
            "duplicate_ratio": 0.2,
            "ack_missing_ratio": 0.3,
            "max_sync_gap": 10,
            "ttl_drop_total": 2,
            "stale_minutes": 120,
        },
        min_window=1,
        min_delivery_success_ratio=0.99,
        max_order_violation_total=0,
        max_duplicate_ratio=0.01,
        max_ack_missing_ratio=0.02,
        max_sync_gap=5,
        max_ttl_drop_total=0,
        max_stale_minutes=60,
    )
    assert len(failures) == 7


def test_evaluate_gate_passes_when_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 20,
            "delivery_success_ratio": 1.0,
            "order_violation_total": 0,
            "duplicate_ratio": 0.0,
            "ack_missing_ratio": 0.0,
            "max_sync_gap": 1,
            "ttl_drop_total": 0,
            "stale_minutes": 10,
        },
        min_window=1,
        min_delivery_success_ratio=0.99,
        max_order_violation_total=0,
        max_duplicate_ratio=0.01,
        max_ack_missing_ratio=0.02,
        max_sync_gap=5,
        max_ttl_drop_total=0,
        max_stale_minutes=60,
    )
    assert failures == []
