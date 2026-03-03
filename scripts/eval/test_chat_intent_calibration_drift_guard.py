import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_intent_calibration_drift_guard.py"
    spec = importlib.util.spec_from_file_location("chat_intent_calibration_drift_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_intent_calibration_drift_guard_tracks_worst_deltas():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-02T00:00:00Z",
            "intent": "ORDER_STATUS",
            "calibrated_ece": 0.05,
            "calibrated_brier_score": 0.08,
            "overconfidence_rate": 0.10,
            "underconfidence_rate": 0.05,
        },
        {
            "timestamp": "2026-03-03T18:00:00Z",
            "intent": "ORDER_STATUS",
            "calibrated_ece": 0.12,
            "calibrated_brier_score": 0.15,
            "overconfidence_rate": 0.18,
            "underconfidence_rate": 0.08,
        },
        {
            "timestamp": "2026-03-02T00:00:00Z",
            "intent": "REFUND_REQUEST",
            "calibrated_ece": 0.07,
            "calibrated_brier_score": 0.10,
            "overconfidence_rate": 0.11,
            "underconfidence_rate": 0.06,
        },
        {
            "timestamp": "2026-03-03T18:00:00Z",
            "intent": "REFUND_REQUEST",
            "calibrated_ece": 0.08,
            "calibrated_brier_score": 0.11,
            "overconfidence_rate": 0.12,
            "underconfidence_rate": 0.07,
        },
    ]
    summary = module.summarize_intent_calibration_drift_guard(
        rows,
        required_intents={"ORDER_STATUS", "REFUND_REQUEST"},
        recent_hours=24,
        min_baseline_samples=1,
        min_recent_samples=1,
        drift_ece_delta=0.03,
        drift_brier_delta=0.03,
        drift_overconfidence_delta=0.03,
        drift_underconfidence_delta=0.03,
        now=datetime(2026, 3, 4, 0, 0, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["intent_total"] == 2
    assert summary["comparable_intent_total"] == 2
    assert summary["drifted_intent_total"] == 1
    assert abs(summary["drifted_intent_ratio"] - 0.5) < 1e-9
    assert summary["missing_required_intent_total"] == 0
    assert abs(summary["worst_ece_delta"] - 0.07) < 1e-9
    assert abs(summary["worst_brier_delta"] - 0.07) < 1e-9
    assert abs(summary["worst_overconfidence_rate_delta"] - 0.08) < 1e-9
    assert abs(summary["worst_underconfidence_rate_delta"] - 0.03) < 1e-9


def test_evaluate_gate_detects_intent_calibration_drift_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "intent_total": 1,
            "comparable_intent_total": 1,
            "drifted_intent_total": 2,
            "worst_ece_delta": 0.12,
            "worst_brier_delta": 0.13,
            "worst_overconfidence_rate_delta": 0.11,
            "worst_underconfidence_rate_delta": 0.10,
            "missing_required_intent_total": 3,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_intent_total=2,
        min_comparable_intent_total=2,
        max_drifted_intent_total=0,
        max_worst_ece_delta=0.05,
        max_worst_brier_delta=0.05,
        max_worst_overconfidence_rate_delta=0.05,
        max_worst_underconfidence_rate_delta=0.05,
        max_missing_required_intent_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "intent_total": 0,
            "comparable_intent_total": 0,
            "drifted_intent_total": 0,
            "worst_ece_delta": 0.0,
            "worst_brier_delta": 0.0,
            "worst_overconfidence_rate_delta": 0.0,
            "worst_underconfidence_rate_delta": 0.0,
            "missing_required_intent_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_intent_total=0,
        min_comparable_intent_total=0,
        max_drifted_intent_total=1000000,
        max_worst_ece_delta=1000000.0,
        max_worst_brier_delta=1000000.0,
        max_worst_overconfidence_rate_delta=1000000.0,
        max_worst_underconfidence_rate_delta=1000000.0,
        max_missing_required_intent_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
