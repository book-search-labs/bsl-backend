import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_data_retention_guard.py"
    spec = importlib.util.spec_from_file_location("chat_data_retention_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_retention_tracks_overdue_exceptions_and_trace():
    module = _load_module()
    now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": "2026-03-03T11:50:00Z",
            "data_class": "chat_turn_raw",
            "action": "PURGED",
            "expires_at": "2026-03-03T11:45:00Z",
            "trace_id": "t-1",
            "request_id": "r-1",
        },
        {
            "timestamp": "2026-03-03T11:40:00Z",
            "data_class": "chat_turn_raw",
            "action": "PENDING",
            "expires_at": "2026-03-03T11:30:00Z",
            "trace_id": "t-2",
            "request_id": "r-2",
        },
        {
            "timestamp": "2026-03-03T11:30:00Z",
            "data_class": "chat_summary",
            "action": "EXEMPT_APPROVED",
            "expires_at": "2026-03-03T11:20:00Z",
            "approval_id": "",
            "trace_id": "",
            "request_id": "",
        },
    ]

    summary = module.summarize_retention(rows, now=now)
    assert summary["window_size"] == 3
    assert summary["expired_total"] == 3
    assert summary["overdue_total"] == 2
    assert summary["unapproved_exception_total"] == 1
    assert summary["missing_trace_total"] == 1
    assert 0.0 < summary["trace_coverage_ratio"] < 1.0


def test_evaluate_gate_detects_overdue_and_trace_coverage_failure():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "overdue_total": 2,
            "overdue_ratio": 0.4,
            "purge_coverage_ratio": 0.6,
            "unapproved_exception_total": 1,
            "stale_minutes": 30.0,
            "trace_coverage_ratio": 0.8,
            "missing_trace_total": 1,
        },
        min_window=1,
        max_overdue_total=0,
        max_overdue_ratio=0.0,
        min_purge_coverage_ratio=1.0,
        max_unapproved_exception_total=0,
        max_stale_minutes=60.0,
        min_trace_coverage_ratio=1.0,
        max_missing_trace_total=0,
    )
    assert len(failures) >= 5
    assert any("overdue records exceeded" in item for item in failures)
    assert any("trace coverage below threshold" in item for item in failures)


def test_evaluate_gate_passes_when_thresholds_met():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 2,
            "overdue_total": 0,
            "overdue_ratio": 0.0,
            "purge_coverage_ratio": 1.0,
            "unapproved_exception_total": 0,
            "stale_minutes": 10.0,
            "trace_coverage_ratio": 1.0,
            "missing_trace_total": 0,
        },
        min_window=1,
        max_overdue_total=0,
        max_overdue_ratio=0.0,
        min_purge_coverage_ratio=1.0,
        max_unapproved_exception_total=0,
        max_stale_minutes=60.0,
        min_trace_coverage_ratio=1.0,
        max_missing_trace_total=0,
    )
    assert failures == []
