import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_health_score_guard.py"
    spec = importlib.util.spec_from_file_location("chat_tool_health_score_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_tool_health_score_guard_tracks_health_and_missing_telemetry():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-04T00:00:00Z", "tool": "order_lookup", "status": "SUCCESS", "latency_ms": 120},
        {"timestamp": "2026-03-04T00:00:05Z", "tool": "order_lookup", "status": "FAILED", "latency_ms": 2100},
        {"timestamp": "2026-03-04T00:00:10Z", "tool": "refund_tool", "status": "SUCCESS", "latency_ms": 300},
        {"timestamp": "2026-03-04T00:00:15Z", "tool": "refund_tool", "status": "SUCCESS", "latency_ms": 350},
        {"timestamp": "2026-03-04T00:00:20Z", "tool": "refund_tool", "status": "FAILED"},
    ]
    summary = module.summarize_tool_health_score_guard(
        rows,
        max_latency_p95_ms=1500.0,
        max_error_ratio=0.2,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["event_total"] == 5
    assert summary["tool_total"] == 2
    assert summary["missing_telemetry_total"] == 1
    assert summary["average_health_score"] > 0.0
    assert abs(summary["stale_minutes"] - (40.0 / 60.0)) < 1e-9

    tools = {row["tool"]: row for row in summary["tool_health"]}
    assert "order_lookup" in tools
    assert "refund_tool" in tools
    assert tools["order_lookup"]["error_ratio"] == 0.5
    assert tools["refund_tool"]["sample_total"] == 3


def test_evaluate_gate_detects_tool_health_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "event_total": 1,
            "tool_total": 1,
            "average_health_score": 0.4,
            "missing_telemetry_total": 3,
            "stale_minutes": 120.0,
            "tool_health": [
                {"tool": "tool_a", "health_score": 0.2},
                {"tool": "tool_b", "health_score": 0.1},
            ],
        },
        min_window=10,
        min_event_total=2,
        min_tool_total=2,
        min_tool_health_score=0.7,
        min_average_health_score=0.8,
        max_unhealthy_tool_total=0,
        max_missing_telemetry_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "tool_total": 0,
            "average_health_score": 1.0,
            "missing_telemetry_total": 0,
            "stale_minutes": 0.0,
            "tool_health": [],
        },
        min_window=0,
        min_event_total=0,
        min_tool_total=0,
        min_tool_health_score=0.0,
        min_average_health_score=0.0,
        max_unhealthy_tool_total=1000000,
        max_missing_telemetry_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
