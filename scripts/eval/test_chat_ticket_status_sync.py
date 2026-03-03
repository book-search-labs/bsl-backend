import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_status_sync.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_status_sync", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_ticket_status_sync_flags_invalid_and_stale():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "ticket_status_lookup",
            "result": "ok",
            "ticket_no": "T-1",
            "ticket_status": "IN_PROGRESS",
            "status_updated_at": "2026-03-01T00:00:00Z",
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "event_type": "ticket_status_lookup",
            "result": "ok",
            "ticket_no": "",
            "ticket_status": "UNKNOWN_STATUS",
            "status_updated_at": "2026-03-03T00:00:05Z",
        },
    ]
    summary = module.summarize_ticket_status_sync(
        rows,
        max_status_age_hours=24.0,
        now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
    )
    assert summary["lookup_total"] == 2
    assert summary["lookup_ok_total"] == 2
    assert summary["invalid_status_total"] == 1
    assert summary["missing_ticket_ref_total"] == 1
    assert summary["stale_status_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "lookup_ok_ratio": 0.4,
            "invalid_status_total": 1,
            "missing_ticket_ref_total": 1,
            "stale_status_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        min_lookup_ok_ratio=0.9,
        max_invalid_status_total=0,
        max_missing_ticket_ref_total=0,
        max_stale_status_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "lookup_ok_ratio": 1.0,
            "invalid_status_total": 0,
            "missing_ticket_ref_total": 0,
            "stale_status_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_lookup_ok_ratio=0.9,
        max_invalid_status_total=0,
        max_missing_ticket_ref_total=0,
        max_stale_status_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []
