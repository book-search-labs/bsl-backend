import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_source_conflict_operator_feedback.py"
    spec = importlib.util.spec_from_file_location("chat_source_conflict_operator_feedback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_operator_feedback_tracks_queue_coverage_and_latency():
    module = _load_module()
    rows = [
        {
            "conflict_id": "c1",
            "timestamp": "2026-03-03T00:00:00Z",
            "conflict_severity": "HIGH",
            "queue_status": "RESOLVED",
            "queued_at": "2026-03-03T00:00:00Z",
            "acknowledged_at": "2026-03-03T00:05:00Z",
            "resolved_at": "2026-03-03T00:20:00Z",
            "operator_note": "공식 공지 기준으로 정리",
        },
        {
            "conflict_id": "c2",
            "timestamp": "2026-03-03T00:01:00Z",
            "conflict_severity": "HIGH",
            "queue_status": "UNQUEUED",
        },
        {
            "conflict_id": "c3",
            "timestamp": "2026-03-03T00:02:00Z",
            "conflict_severity": "MEDIUM",
            "queue_status": "ACKED",
            "queued_at": "2026-03-03T00:02:00Z",
            "acknowledged_at": "2026-03-03T00:03:00Z",
        },
    ]
    summary = module.summarize_operator_feedback(
        rows,
        now=datetime(2026, 3, 3, 0, 30, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["conflict_total"] == 3
    assert summary["queued_total"] == 2
    assert summary["acknowledged_total"] == 2
    assert summary["resolved_total"] == 1
    assert summary["high_conflict_total"] == 2
    assert summary["high_conflict_queued_total"] == 1
    assert summary["high_conflict_unqueued_total"] == 1
    assert summary["queue_coverage_ratio"] == (2.0 / 3.0)
    assert summary["high_queue_coverage_ratio"] == 0.5
    assert summary["resolved_ratio"] == (1.0 / 3.0)
    assert summary["p95_ack_latency_minutes"] == 5.0
    assert summary["p95_resolution_latency_minutes"] == 20.0
    assert summary["missing_operator_note_total"] == 0
    assert summary["stale_minutes"] == 28.0


def test_evaluate_gate_detects_operator_feedback_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "high_conflict_unqueued_total": 2,
            "high_queue_coverage_ratio": 0.2,
            "resolved_ratio": 0.2,
            "p95_ack_latency_minutes": 120.0,
            "missing_operator_note_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        max_high_conflict_unqueued_total=0,
        min_high_queue_coverage_ratio=0.9,
        min_resolved_ratio=0.8,
        max_p95_ack_latency_minutes=30.0,
        max_missing_operator_note_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "high_conflict_unqueued_total": 0,
            "high_queue_coverage_ratio": 1.0,
            "resolved_ratio": 1.0,
            "p95_ack_latency_minutes": 0.0,
            "missing_operator_note_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_high_conflict_unqueued_total=1000000,
        min_high_queue_coverage_ratio=0.0,
        min_resolved_ratio=0.0,
        max_p95_ack_latency_minutes=1000000.0,
        max_missing_operator_note_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_source_conflict_operator_feedback_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "conflict_total": 20,
            "high_conflict_total": 10,
            "high_conflict_unqueued_total": 0,
            "high_queue_coverage_ratio": 1.0,
            "resolved_ratio": 0.9,
            "p95_ack_latency_minutes": 10.0,
            "missing_operator_note_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "conflict_total": 1,
            "high_conflict_total": 1,
            "high_conflict_unqueued_total": 2,
            "high_queue_coverage_ratio": 0.2,
            "resolved_ratio": 0.3,
            "p95_ack_latency_minutes": 80.0,
            "missing_operator_note_total": 2,
            "stale_minutes": 80.0,
        },
        max_conflict_total_drop=1,
        max_high_conflict_total_drop=1,
        max_high_conflict_unqueued_total_increase=0,
        max_high_queue_coverage_ratio_drop=0.05,
        max_resolved_ratio_drop=0.05,
        max_p95_ack_latency_minutes_increase=30.0,
        max_missing_operator_note_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("conflict_total regression" in item for item in failures)
    assert any("high_conflict_total regression" in item for item in failures)
    assert any("high_conflict_unqueued_total regression" in item for item in failures)
    assert any("high_queue_coverage_ratio regression" in item for item in failures)
    assert any("resolved_ratio regression" in item for item in failures)
    assert any("p95_ack_latency_minutes regression" in item for item in failures)
    assert any("missing_operator_note_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
