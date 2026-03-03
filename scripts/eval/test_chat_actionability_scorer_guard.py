import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_actionability_scorer_guard.py"
    spec = importlib.util.spec_from_file_location("chat_actionability_scorer_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_actionability_scorer_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intent": "ORDER_STATUS",
            "has_current_state": True,
            "next_action": "STATUS_CHECK",
            "expected_outcome": "현재 배송 상태를 확인할 수 있습니다.",
            "fallback_action": "OPEN_SUPPORT_TICKET",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intent": "REFUND_REQUEST",
            "has_current_state": True,
            "next_action": "SUBMIT_REFUND",
            "expected_outcome": "",
            "fallback_action": "",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "intent": "FAQ",
            "actionability_score": 82,
            "has_current_state": True,
            "next_action": "READ_POLICY",
            "expected_outcome": "환불 정책을 확인합니다.",
            "has_fallback_alternative": True,
        },
    ]
    summary = module.summarize_actionability_scorer_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 3
    assert summary["event_total"] == 3
    assert summary["scored_total"] == 3
    assert abs(summary["average_actionability_score"] - 0.7733333333) < 1e-9
    assert summary["low_actionability_total"] == 1
    assert abs(summary["low_actionability_ratio"] - (1.0 / 3.0)) < 1e-9
    assert summary["missing_expected_outcome_total"] == 1
    assert summary["missing_fallback_alternative_total"] == 1
    assert summary["score_hist"]["80_100"] == 2
    assert summary["score_hist"]["60_79"] == 0
    assert abs(summary["stale_minutes"] - (2.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_actionability_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "average_actionability_score": 0.55,
            "low_actionability_ratio": 0.8,
            "low_actionability_total": 3,
            "missing_current_state_ratio": 0.7,
            "missing_next_action_ratio": 0.6,
            "missing_expected_outcome_ratio": 0.9,
            "missing_fallback_alternative_ratio": 1.0,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_average_actionability_score=0.8,
        max_low_actionability_ratio=0.2,
        max_low_actionability_total=0,
        max_missing_current_state_ratio=0.1,
        max_missing_next_action_ratio=0.1,
        max_missing_expected_outcome_ratio=0.1,
        max_missing_fallback_alternative_ratio=0.1,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "average_actionability_score": 0.0,
            "low_actionability_ratio": 0.0,
            "low_actionability_total": 0,
            "missing_current_state_ratio": 0.0,
            "missing_next_action_ratio": 0.0,
            "missing_expected_outcome_ratio": 0.0,
            "missing_fallback_alternative_ratio": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_average_actionability_score=0.0,
        max_low_actionability_ratio=1.0,
        max_low_actionability_total=1000000,
        max_missing_current_state_ratio=1.0,
        max_missing_next_action_ratio=1.0,
        max_missing_expected_outcome_ratio=1.0,
        max_missing_fallback_alternative_ratio=1.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
