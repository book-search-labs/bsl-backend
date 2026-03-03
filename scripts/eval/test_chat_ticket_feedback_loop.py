import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_feedback_loop.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_feedback_loop", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_feedback_loop_tracks_linkage_and_monthly_coverage():
    module = _load_module()
    feedback_rows = [
        {
            "ticket_id": "t1",
            "predicted_category": "REFUND",
            "predicted_severity": "S2",
            "final_category": "REFUND",
            "final_severity": "S1",
            "is_corrected": True,
            "corrected_by": "agent-1",
            "corrected_at": "2026-03-01T00:00:00Z",
            "model_version": "triage-v1",
        },
        {
            "ticket_id": "t2",
            "predicted_category": "SHIPPING",
            "predicted_severity": "S3",
            "final_category": "REFUND",
            "final_severity": "S2",
            "corrected_by": "agent-2",
            "corrected_at": "2026-02-28T00:00:00Z",
            "model_version": "triage-v1",
        },
        {
            "ticket_id": "t3",
            "predicted_category": "ORDER",
            "predicted_severity": "S4",
            "final_category": "ORDER",
            "final_severity": "S4",
            "timestamp": "2026-03-01T00:01:00Z",
            "model_version": "",
        },
        {
            "ticket_id": "t4",
            "predicted_category": "PAYMENT",
            "predicted_severity": "S3",
            "final_category": "ACCOUNT",
            "final_severity": "S2",
            "model_version": "",
        },
    ]
    outcome_rows = [
        {"ticket_id": "t1", "status": "RESOLVED", "timestamp": "2026-03-01T00:01:30Z"},
        {"ticket_id": "t2", "status": "OPEN", "timestamp": "2026-03-01T00:00:30Z"},
    ]

    summary = module.summarize_feedback_loop(
        feedback_rows,
        outcome_rows,
        now=datetime(2026, 3, 1, 0, 2, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["feedback_total"] == 4
    assert summary["corrected_total"] == 3
    assert summary["feedback_linked_total"] == 2
    assert summary["feedback_linkage_ratio"] == (2.0 / 3.0)
    assert summary["missing_actor_total"] == 1
    assert summary["missing_corrected_time_total"] == 1
    assert summary["missing_model_version_total"] == 2
    assert summary["outcome_total"] == 2
    assert summary["closed_outcome_total"] == 1
    assert summary["monthly_bucket_total"] == 2
    assert summary["monthly_min_samples"] == 1
    assert summary["monthly_max_samples"] == 1
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_feedback_loop_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "feedback_total": 2,
            "missing_actor_total": 2,
            "missing_corrected_time_total": 2,
            "missing_model_version_total": 2,
            "feedback_linkage_ratio": 0.2,
            "monthly_bucket_total": 2,
            "monthly_min_samples": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_feedback_total=5,
        max_missing_actor_total=0,
        max_missing_corrected_time_total=0,
        max_missing_model_version_total=0,
        min_feedback_linkage_ratio=0.8,
        min_monthly_bucket_total=3,
        min_monthly_samples_per_bucket=5,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "feedback_total": 0,
            "missing_actor_total": 0,
            "missing_corrected_time_total": 0,
            "missing_model_version_total": 0,
            "feedback_linkage_ratio": 1.0,
            "monthly_bucket_total": 0,
            "monthly_min_samples": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_feedback_total=0,
        max_missing_actor_total=1000000,
        max_missing_corrected_time_total=1000000,
        max_missing_model_version_total=1000000,
        min_feedback_linkage_ratio=0.0,
        min_monthly_bucket_total=0,
        min_monthly_samples_per_bucket=0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
