import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_intent_confidence_routing_guard.py"
    spec = importlib.util.spec_from_file_location("chat_intent_confidence_routing_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_intent_confidence_routing_guard_tracks_mismatch_and_handoff():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intent": "ORDER_STATUS",
            "calibrated_confidence": 0.91,
            "route": "EXECUTE_TOOL",
        },
        {
            "timestamp": "2026-03-04T00:00:05Z",
            "intent": "POLICY_QA",
            "calibrated_confidence": 0.62,
            "route": "CLARIFY",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intent": "REFUND_REQUEST",
            "calibrated_confidence": 0.22,
            "route": "CLARIFY",
        },
        {
            "timestamp": "2026-03-04T00:00:15Z",
            "intent": "REFUND_REQUEST",
            "calibrated_confidence": 0.18,
            "route": "HANDOFF",
            "low_confidence_repeat_count": 3,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "intent": "REFUND_REQUEST",
            "calibrated_confidence": 0.19,
            "route": "CLARIFY",
            "low_confidence_repeat_count": 4,
        },
    ]
    summary = module.summarize_intent_confidence_routing_guard(
        rows,
        tool_route_threshold=0.75,
        clarify_route_threshold=0.45,
        repeat_low_confidence_threshold=3,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["decision_total"] == 5
    assert summary["routing_mismatch_total"] == 2
    assert abs(summary["routing_mismatch_ratio"] - 0.4) < 1e-9
    assert summary["unsafe_tool_route_total"] == 0
    assert summary["low_confidence_total"] == 3
    assert summary["low_confidence_clarification_total"] == 2
    assert abs(summary["low_confidence_clarification_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["repeat_low_confidence_total"] == 2
    assert summary["repeat_low_confidence_handoff_total"] == 1
    assert summary["repeat_low_confidence_unescalated_total"] == 1
    assert abs(summary["repeat_low_confidence_handoff_ratio"] - 0.5) < 1e-9
    assert abs(summary["stale_minutes"] - (40.0 / 60.0)) < 1e-9


def test_evaluate_gate_detects_intent_confidence_routing_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "decision_total": 2,
            "routing_mismatch_ratio": 0.45,
            "unsafe_tool_route_total": 2,
            "low_confidence_clarification_ratio": 0.2,
            "repeat_low_confidence_handoff_ratio": 0.3,
            "repeat_low_confidence_unescalated_total": 4,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_decision_total=3,
        max_routing_mismatch_ratio=0.1,
        max_unsafe_tool_route_total=0,
        min_low_confidence_clarification_ratio=0.8,
        min_repeat_low_confidence_handoff_ratio=0.9,
        max_repeat_low_confidence_unescalated_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "decision_total": 0,
            "routing_mismatch_ratio": 0.0,
            "unsafe_tool_route_total": 0,
            "low_confidence_clarification_ratio": 1.0,
            "repeat_low_confidence_handoff_ratio": 1.0,
            "repeat_low_confidence_unescalated_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_decision_total=0,
        max_routing_mismatch_ratio=1000000.0,
        max_unsafe_tool_route_total=1000000,
        min_low_confidence_clarification_ratio=0.0,
        min_repeat_low_confidence_handoff_ratio=0.0,
        max_repeat_low_confidence_unescalated_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
