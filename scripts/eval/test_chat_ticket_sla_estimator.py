import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_sla_estimator.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_sla_estimator", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_sla_estimator_tracks_alert_coverage_and_error():
    module = _load_module()
    estimate_rows = [
        {
            "ticket_id": "t1",
            "timestamp": "2026-03-03T00:00:00Z",
            "predicted_response_minutes": 30,
            "breach_risk_score": 0.95,
            "alert_route": "SLA_ALERT",
            "features_snapshot": {"category": "REFUND"},
            "model_version": "sla-v1",
        },
        {
            "ticket_id": "t2",
            "timestamp": "2026-03-03T00:01:00Z",
            "predicted_response_minutes": 10,
            "breach_risk_score": 0.81,
            "alert_sent": False,
            "features_snapshot": {},
            "model_version": "",
        },
        {
            "ticket_id": "t3",
            "timestamp": "2026-03-03T00:02:00Z",
            "predicted_response_minutes": -1,
            "breach_risk_score": 0.20,
            "features_snapshot": {"category": "ORDER"},
            "model_version": "sla-v1",
        },
    ]
    outcome_rows = [
        {"ticket_id": "t1", "actual_response_minutes": 40, "sla_target_minutes": 20},
        {"ticket_id": "t2", "actual_response_minutes": 5, "sla_target_minutes": 20},
        {"ticket_id": "t3", "actual_response_minutes": 20, "sla_target_minutes": 15},
    ]
    summary = module.summarize_sla_estimator(
        estimate_rows,
        outcome_rows,
        breach_risk_threshold=0.7,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["estimate_total"] == 3
    assert summary["high_risk_total"] == 2
    assert summary["high_risk_alerted_total"] == 1
    assert summary["high_risk_unalerted_total"] == 1
    assert summary["missing_features_snapshot_total"] == 1
    assert summary["missing_model_version_total"] == 1
    assert summary["predicted_minutes_invalid_total"] == 1
    assert summary["actual_linked_total"] == 2
    assert summary["mae_minutes"] == 7.5
    assert summary["actual_breach_total"] == 2
    assert summary["detected_breach_total"] == 1
    assert summary["breach_recall"] == 0.5
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_sla_estimator_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "high_risk_unalerted_total": 3,
            "missing_features_snapshot_total": 2,
            "missing_model_version_total": 2,
            "predicted_minutes_invalid_total": 2,
            "mae_minutes": 90.0,
            "breach_recall": 0.1,
            "stale_minutes": 300.0,
        },
        min_window=20,
        max_high_risk_unalerted_total=0,
        max_missing_features_snapshot_total=0,
        max_missing_model_version_total=0,
        max_predicted_minutes_invalid_total=0,
        max_mae_minutes=30.0,
        min_breach_recall=0.7,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "high_risk_unalerted_total": 0,
            "missing_features_snapshot_total": 0,
            "missing_model_version_total": 0,
            "predicted_minutes_invalid_total": 0,
            "mae_minutes": 0.0,
            "breach_recall": 1.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_high_risk_unalerted_total=1000000,
        max_missing_features_snapshot_total=1000000,
        max_missing_model_version_total=1000000,
        max_predicted_minutes_invalid_total=1000000,
        max_mae_minutes=1000000.0,
        min_breach_recall=0.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
