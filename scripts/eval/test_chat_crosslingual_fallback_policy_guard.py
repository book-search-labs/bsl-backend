import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_crosslingual_fallback_policy_guard.py"
    spec = importlib.util.spec_from_file_location("chat_crosslingual_fallback_policy_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_crosslingual_fallback_policy_guard_tracks_low_confidence_safety():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intent": "REFUND_REQUEST",
            "bridge_confidence": 0.30,
            "fallback_triggered": True,
            "fallback_reason": "LOW_CONFIDENCE_REWRITE",
            "source_based_response": True,
            "clarification_asked": True,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intent": "BOOK_SEARCH",
            "bridge_confidence": 0.40,
            "fallback_triggered": False,
            "response_mode": "DIRECT",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "intent": "REFUND_REQUEST",
            "bridge_confidence": 0.35,
            "fallback_triggered": False,
            "response_mode": "DIRECT",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "intent": "POLICY_QA",
            "bridge_confidence": 0.20,
            "fallback_triggered": True,
            "fallback_reason": "",
            "source_based_response": False,
            "clarification_asked": False,
        },
        {
            "timestamp": "2026-03-04T00:00:40Z",
            "intent": "BOOK_SEARCH",
            "bridge_confidence": 0.95,
            "fallback_triggered": False,
        },
    ]
    summary = module.summarize_crosslingual_fallback_policy_guard(
        rows,
        low_confidence_threshold=0.6,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["event_total"] == 5
    assert summary["low_confidence_total"] == 4
    assert summary["fallback_triggered_total"] == 2
    assert summary["fallback_coverage_ratio"] == 0.5
    assert summary["source_based_response_total"] == 1
    assert summary["source_based_response_ratio"] == 0.5
    assert summary["clarification_asked_total"] == 1
    assert summary["clarification_ratio"] == 0.5
    assert summary["unsafe_high_risk_no_fallback_total"] == 1
    assert summary["direct_answer_without_fallback_total"] == 2
    assert summary["reason_missing_total"] == 1
    assert abs(summary["stale_minutes"] - (20.0 / 60.0)) < 1e-9


def test_evaluate_gate_detects_crosslingual_fallback_policy_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "event_total": 1,
            "fallback_coverage_ratio": 0.4,
            "source_based_response_ratio": 0.3,
            "clarification_ratio": 0.2,
            "unsafe_high_risk_no_fallback_total": 3,
            "direct_answer_without_fallback_total": 2,
            "reason_missing_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_event_total=2,
        min_fallback_coverage_ratio=0.9,
        min_source_based_response_ratio=0.9,
        min_clarification_ratio=0.9,
        max_unsafe_high_risk_no_fallback_total=0,
        max_direct_answer_without_fallback_total=0,
        max_reason_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "fallback_coverage_ratio": 1.0,
            "source_based_response_ratio": 1.0,
            "clarification_ratio": 1.0,
            "unsafe_high_risk_no_fallback_total": 0,
            "direct_answer_without_fallback_total": 0,
            "reason_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_fallback_coverage_ratio=0.0,
        min_source_based_response_ratio=0.0,
        min_clarification_ratio=0.0,
        max_unsafe_high_risk_no_fallback_total=1000000,
        max_direct_answer_without_fallback_total=1000000,
        max_reason_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
