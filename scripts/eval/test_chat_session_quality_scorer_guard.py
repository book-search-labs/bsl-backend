import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_session_quality_scorer_guard.py"
    spec = importlib.util.spec_from_file_location("chat_session_quality_scorer_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_session_quality_scorer_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intent_group": "commerce",
            "evidence_coverage_ratio": 0.95,
            "reask_rate": 0.05,
            "error_rate": 0.02,
            "completed": True,
            "session_quality_score": 0.93,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intent_group": "general",
            "evidence_coverage_ratio": 0.2,
            "reask_rate": 0.7,
            "error_rate": 0.5,
            "completed": False,
            "session_quality_score": 0.9,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "intent_group": "general",
            "evidence_coverage_ratio": 0.6,
            "reask_rate": 0.3,
            "error_rate": 0.2,
            "completion_ratio": 0.8,
        },
    ]
    summary = module.summarize_session_quality_scorer_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
        model_drift_tolerance=0.05,
    )
    assert summary["window_size"] == 3
    assert summary["event_total"] == 3
    assert summary["scored_total"] == 3
    assert summary["commerce_scored_total"] == 1
    assert summary["general_scored_total"] == 2
    assert summary["low_quality_total"] == 1
    assert summary["model_drift_total"] == 1
    assert summary["mean_quality_score"] > 0.0
    assert abs(summary["stale_minutes"] - (2.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_session_quality_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "mean_quality_score": 0.2,
            "low_quality_total": 3,
            "model_drift_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_mean_quality_score=0.8,
        max_low_quality_total=0,
        max_model_drift_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "mean_quality_score": 1.0,
            "low_quality_total": 0,
            "model_drift_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_mean_quality_score=0.0,
        max_low_quality_total=1000000,
        max_model_drift_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
