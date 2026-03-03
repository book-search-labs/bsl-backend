import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_degrade_strategy_guard.py"
    spec = importlib.util.spec_from_file_location("chat_tool_degrade_strategy_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_tool_degrade_strategy_guard_tracks_retry_and_safe_fallback():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "request_id": "req-1",
            "attempt_no": 0,
            "tool": "order_lookup",
            "status": "FAILED",
        },
        {
            "timestamp": "2026-03-04T00:00:02Z",
            "request_id": "req-1",
            "attempt_no": 1,
            "tool": "order_lookup_backup",
            "status": "SUCCESS",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "request_id": "req-2",
            "attempt_no": 0,
            "tool": "refund_tool",
            "status": "ERROR",
        },
        {
            "timestamp": "2026-03-04T00:00:12Z",
            "request_id": "req-2",
            "attempt_no": 1,
            "tool": "refund_tool",
            "status": "FAILED",
        },
        {
            "timestamp": "2026-03-04T00:00:13Z",
            "request_id": "req-2",
            "attempt_no": 2,
            "route_result": "SAFE_FALLBACK",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "request_id": "req-3",
            "attempt_no": 0,
            "tool": "shipping_tool",
            "status": "SUCCESS",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "request_id": "req-4",
            "attempt_no": 0,
            "tool": "payment_tool",
            "status": "FAILED",
        },
    ]

    summary = module.summarize_tool_degrade_strategy_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 7
    assert summary["request_total"] == 4
    assert summary["degrade_required_total"] == 3
    assert summary["fallback_attempted_total"] == 2
    assert abs(summary["degrade_coverage_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["sequential_retry_success_total"] == 1
    assert summary["safe_fallback_total"] == 1
    assert summary["resolved_degrade_total"] == 2
    assert abs(summary["safe_fallback_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["stalled_degrade_total"] == 1
    assert summary["duplicate_tool_retry_total"] == 0
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_summarize_tool_degrade_strategy_guard_tracks_duplicate_tool_retry():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "request_id": "req-dup",
            "attempt_no": 0,
            "tool": "refund_tool",
            "status": "FAILED",
        },
        {
            "timestamp": "2026-03-04T00:00:02Z",
            "request_id": "req-dup",
            "attempt_no": 1,
            "tool": "refund_tool",
            "status": "ERROR",
        },
    ]
    summary = module.summarize_tool_degrade_strategy_guard(rows)
    assert summary["degrade_required_total"] == 1
    assert summary["duplicate_tool_retry_total"] == 1
    assert summary["stalled_degrade_total"] == 1


def test_evaluate_gate_detects_tool_degrade_strategy_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "request_total": 1,
            "degrade_coverage_ratio": 0.2,
            "safe_fallback_ratio": 0.3,
            "stalled_degrade_total": 3,
            "duplicate_tool_retry_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_request_total=2,
        min_degrade_coverage_ratio=0.9,
        min_safe_fallback_ratio=0.9,
        max_stalled_degrade_total=0,
        max_duplicate_tool_retry_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "request_total": 0,
            "degrade_coverage_ratio": 1.0,
            "safe_fallback_ratio": 1.0,
            "stalled_degrade_total": 0,
            "duplicate_tool_retry_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_request_total=0,
        min_degrade_coverage_ratio=0.0,
        min_safe_fallback_ratio=0.0,
        max_stalled_degrade_total=1000000,
        max_duplicate_tool_retry_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
