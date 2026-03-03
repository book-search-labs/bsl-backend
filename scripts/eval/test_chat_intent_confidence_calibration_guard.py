import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_intent_confidence_calibration_guard.py"
    spec = importlib.util.spec_from_file_location("chat_intent_confidence_calibration_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_intent_confidence_calibration_guard_tracks_calibration_quality():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intent": "ORDER_STATUS",
            "domain": "ORDER",
            "raw_confidence": 0.92,
            "calibrated_confidence": 0.72,
            "is_correct": False,
        },
        {
            "timestamp": "2026-03-04T00:00:05Z",
            "intent": "REFUND_REQUEST",
            "domain": "REFUND",
            "raw_confidence": 0.45,
            "calibrated_confidence": 0.62,
            "is_correct": True,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intent": "DELIVERY_TRACKING",
            "domain": "SHIPPING",
            "raw_confidence": 0.88,
            "calibrated_confidence": 0.82,
            "is_correct": True,
        },
        {
            "timestamp": "2026-03-04T00:00:15Z",
            "intent": "POLICY_QA",
            "domain": "POLICY",
            "raw_confidence": 0.15,
            "calibrated_confidence": 0.34,
            "is_correct": True,
        },
    ]
    summary = module.summarize_intent_confidence_calibration_guard(
        rows,
        required_domains={"ORDER", "SHIPPING", "REFUND", "POLICY"},
        overconfidence_threshold=0.85,
        underconfidence_threshold=0.35,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["prediction_total"] == 4
    assert summary["domain_coverage_ratio"] == 1.0
    assert summary["overconfidence_total"] == 0
    assert summary["underconfidence_total"] == 1
    assert summary["calibrated_ece"] < summary["raw_ece"]
    assert summary["calibrated_brier_score"] < summary["raw_brier_score"]
    assert summary["ece_gain"] > 0.0
    assert summary["brier_gain"] > 0.0
    assert summary["stale_minutes"] == 0.75


def test_evaluate_gate_detects_intent_calibration_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "prediction_total": 1,
            "domain_coverage_ratio": 0.2,
            "calibrated_ece": 0.35,
            "calibrated_brier_score": 0.31,
            "ece_gain": -0.03,
            "brier_gain": -0.04,
            "overconfidence_total": 3,
            "underconfidence_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_prediction_total=2,
        min_domain_coverage_ratio=1.0,
        max_calibrated_ece=0.2,
        max_calibrated_brier_score=0.2,
        min_ece_gain=0.0,
        min_brier_gain=0.0,
        max_overconfidence_total=0,
        max_underconfidence_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "prediction_total": 0,
            "domain_coverage_ratio": 1.0,
            "calibrated_ece": 0.0,
            "calibrated_brier_score": 0.0,
            "ece_gain": 0.0,
            "brier_gain": 0.0,
            "overconfidence_total": 0,
            "underconfidence_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_prediction_total=0,
        min_domain_coverage_ratio=0.0,
        max_calibrated_ece=1000000.0,
        max_calibrated_brier_score=1000000.0,
        min_ece_gain=-1000000.0,
        min_brier_gain=-1000000.0,
        max_overconfidence_total=1000000,
        max_underconfidence_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
