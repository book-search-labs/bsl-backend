import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_capability_routing_guard.py"
    spec = importlib.util.spec_from_file_location("chat_tool_capability_routing_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_tool_capability_routing_guard_tracks_miss_and_below_health():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intent": "ORDER_STATUS",
            "selected_tool": "order_lookup",
            "capability_match": True,
            "route_result": "ROUTED",
            "selected_tool_health_score": 0.9,
            "tool_health_threshold": 0.7,
        },
        {
            "timestamp": "2026-03-04T00:00:05Z",
            "intent": "REFUND_REQUEST",
            "selected_tool": "refund_tool",
            "capability_match": False,
            "route_result": "ROUTED",
            "selected_tool_health_score": 0.8,
            "tool_health_threshold": 0.7,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intent": "REFUND_REQUEST",
            "selected_tool": "refund_tool",
            "capability_match": True,
            "route_result": "ROUTED",
            "selected_tool_health_score": 0.4,
            "tool_health_threshold": 0.7,
        },
        {
            "timestamp": "2026-03-04T00:00:15Z",
            "intent": "REFUND_REQUEST",
            "selected_tool": "",
            "route_result": "CAPABILITY_MISS",
            "fallback_applied": True,
        },
    ]
    summary = module.summarize_tool_capability_routing_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["route_event_total"] == 4
    assert summary["routed_total"] == 3
    assert summary["capability_match_total"] == 2
    assert abs(summary["capability_match_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["capability_miss_total"] == 2
    assert summary["below_health_routed_total"] == 1
    assert summary["intent_without_candidate_total"] == 1
    assert summary["fallback_route_total"] == 1
    assert abs(summary["stale_minutes"] - 0.75) < 1e-9


def test_evaluate_gate_detects_tool_capability_routing_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "route_event_total": 1,
            "capability_match_ratio": 0.3,
            "capability_miss_total": 2,
            "below_health_routed_total": 2,
            "intent_without_candidate_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_route_event_total=2,
        min_capability_match_ratio=0.9,
        max_capability_miss_total=0,
        max_below_health_routed_total=0,
        max_intent_without_candidate_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "route_event_total": 0,
            "capability_match_ratio": 1.0,
            "capability_miss_total": 0,
            "below_health_routed_total": 0,
            "intent_without_candidate_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_route_event_total=0,
        min_capability_match_ratio=0.0,
        max_capability_miss_total=1000000,
        max_below_health_routed_total=1000000,
        max_intent_without_candidate_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
