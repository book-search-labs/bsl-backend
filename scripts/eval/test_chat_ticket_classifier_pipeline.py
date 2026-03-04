import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_classifier_pipeline.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_classifier_pipeline", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_classifier_pipeline_tracks_low_confidence_manual_review():
    module = _load_module()
    rows = [
        {
            "ticket_id": "t1",
            "timestamp": "2026-03-03T00:00:00Z",
            "predicted_category": "REFUND",
            "predicted_severity": "S2",
            "confidence": 0.92,
            "model_version": "triage-v1",
            "reason_code": "TOOL_FAIL",
        },
        {
            "ticket_id": "t2",
            "timestamp": "2026-03-03T00:01:00Z",
            "predicted_category": "UNKNOWN_CAT",
            "predicted_severity": "S9",
            "confidence": 0.4,
            "manual_review": True,
            "model_version": "",
            "conversation_summary": "",
            "tool_failures": 0,
        },
        {
            "ticket_id": "t3",
            "timestamp": "2026-03-03T00:02:00Z",
            "predicted_category": "PAYMENT",
            "predicted_severity": "S1",
            "confidence": 0.2,
            "manual_review": False,
            "model_version": "triage-v1",
            "reason_code": "",
            "conversation_summary": "",
        },
    ]
    summary = module.summarize_classifier_pipeline(
        rows,
        low_confidence_threshold=0.7,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )
    assert summary["prediction_total"] == 3
    assert summary["low_confidence_total"] == 2
    assert summary["low_confidence_manual_review_total"] == 1
    assert summary["low_confidence_unrouted_total"] == 1
    assert summary["unknown_category_total"] == 1
    assert summary["unknown_severity_total"] == 1
    assert summary["missing_model_version_total"] == 1
    assert summary["missing_signal_total"] >= 1


def test_evaluate_gate_detects_classifier_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "low_confidence_unrouted_total": 3,
            "manual_review_coverage_ratio": 0.2,
            "unknown_category_total": 1,
            "unknown_severity_total": 1,
            "missing_model_version_total": 2,
            "missing_signal_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=20,
        max_low_confidence_unrouted_total=0,
        min_manual_review_coverage_ratio=0.8,
        max_unknown_category_total=0,
        max_unknown_severity_total=0,
        max_missing_model_version_total=0,
        max_missing_signal_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "low_confidence_unrouted_total": 0,
            "manual_review_coverage_ratio": 1.0,
            "unknown_category_total": 0,
            "unknown_severity_total": 0,
            "missing_model_version_total": 0,
            "missing_signal_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_low_confidence_unrouted_total=1000000,
        min_manual_review_coverage_ratio=0.0,
        max_unknown_category_total=1000000,
        max_unknown_severity_total=1000000,
        max_missing_model_version_total=1000000,
        max_missing_signal_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_classifier_pipeline_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "prediction_total": 100,
            "low_confidence_unrouted_total": 0,
            "manual_review_coverage_ratio": 1.0,
            "unknown_category_total": 0,
            "unknown_severity_total": 0,
            "missing_model_version_total": 0,
            "missing_signal_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "prediction_total": 70,
            "low_confidence_unrouted_total": 3,
            "manual_review_coverage_ratio": 0.4,
            "unknown_category_total": 2,
            "unknown_severity_total": 2,
            "missing_model_version_total": 4,
            "missing_signal_total": 5,
            "stale_minutes": 90.0,
        },
        max_prediction_total_drop=5,
        max_low_confidence_unrouted_total_increase=0,
        max_manual_review_coverage_ratio_drop=0.05,
        max_unknown_category_total_increase=0,
        max_unknown_severity_total_increase=0,
        max_missing_model_version_total_increase=0,
        max_missing_signal_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("prediction_total regression" in item for item in failures)
    assert any("low_confidence_unrouted_total regression" in item for item in failures)
    assert any("manual_review_coverage_ratio regression" in item for item in failures)
    assert any("unknown_category_total regression" in item for item in failures)
    assert any("unknown_severity_total regression" in item for item in failures)
    assert any("missing_model_version_total regression" in item for item in failures)
    assert any("missing_signal_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
