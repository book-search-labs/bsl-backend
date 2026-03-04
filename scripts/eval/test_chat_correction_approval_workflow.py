import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_correction_approval_workflow.py"
    spec = importlib.util.spec_from_file_location("chat_correction_approval_workflow", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_correction_approval_workflow_tracks_transitions_and_latency():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "correction_id": "c1",
            "event_type": "SUBMITTED",
            "actor_id": "op1",
        },
        {
            "timestamp": "2026-03-03T00:10:00Z",
            "correction_id": "c1",
            "event_type": "APPROVED",
            "reviewer_id": "rv1",
            "actor_id": "rv1",
        },
        {
            "timestamp": "2026-03-03T00:20:00Z",
            "correction_id": "c1",
            "event_type": "ACTIVATED",
            "actor_id": "op1",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "correction_id": "c2",
            "event_type": "APPROVED",
            "reviewer_id": "",
            "actor_id": "",
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "correction_id": "c2",
            "event_type": "ACTIVATED",
            "actor_id": "op2",
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "correction_id": "c3",
            "event_type": "BROKEN",
            "actor_id": "op3",
        },
    ]
    summary = module.summarize_correction_approval_workflow(
        rows,
        now=datetime(2026, 3, 3, 0, 21, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 6
    assert summary["event_total"] == 6
    assert summary["correction_total"] == 3
    assert summary["submitted_total"] == 1
    assert summary["approved_total"] == 2
    assert summary["activated_total"] == 2
    assert summary["invalid_event_type_total"] == 1
    assert summary["invalid_transition_total"] == 1
    assert summary["missing_actor_total"] == 1
    assert summary["missing_reviewer_total"] == 1
    assert summary["p95_approval_latency_minutes"] == 10.0
    assert summary["p95_activation_latency_minutes"] == 10.0
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_correction_approval_workflow_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "correction_total": 1,
            "submitted_total": 0,
            "invalid_event_type_total": 2,
            "invalid_transition_total": 3,
            "missing_actor_total": 1,
            "missing_reviewer_total": 1,
            "p95_approval_latency_minutes": 100.0,
            "p95_activation_latency_minutes": 120.0,
            "stale_minutes": 180.0,
        },
        min_window=10,
        min_correction_total=2,
        min_submitted_total=1,
        max_invalid_event_type_total=0,
        max_invalid_transition_total=0,
        max_missing_actor_total=0,
        max_missing_reviewer_total=0,
        max_p95_approval_latency_minutes=30.0,
        max_p95_activation_latency_minutes=30.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "correction_total": 0,
            "submitted_total": 0,
            "invalid_event_type_total": 0,
            "invalid_transition_total": 0,
            "missing_actor_total": 0,
            "missing_reviewer_total": 0,
            "p95_approval_latency_minutes": 0.0,
            "p95_activation_latency_minutes": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_correction_total=0,
        min_submitted_total=0,
        max_invalid_event_type_total=1000000,
        max_invalid_transition_total=1000000,
        max_missing_actor_total=1000000,
        max_missing_reviewer_total=1000000,
        max_p95_approval_latency_minutes=1000000.0,
        max_p95_activation_latency_minutes=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_correction_approval_workflow_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "correction_total": 20,
            "submitted_total": 20,
            "approved_total": 20,
            "activated_total": 18,
            "invalid_event_type_total": 0,
            "invalid_transition_total": 0,
            "missing_actor_total": 0,
            "missing_reviewer_total": 0,
            "p95_approval_latency_minutes": 10.0,
            "p95_activation_latency_minutes": 10.0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "correction_total": 1,
            "submitted_total": 1,
            "approved_total": 1,
            "activated_total": 1,
            "invalid_event_type_total": 2,
            "invalid_transition_total": 2,
            "missing_actor_total": 1,
            "missing_reviewer_total": 1,
            "p95_approval_latency_minutes": 120.0,
            "p95_activation_latency_minutes": 180.0,
            "stale_minutes": 90.0,
        },
        max_correction_total_drop=1,
        max_submitted_total_drop=1,
        max_approved_total_drop=1,
        max_activated_total_drop=1,
        max_invalid_event_type_total_increase=0,
        max_invalid_transition_total_increase=0,
        max_missing_actor_total_increase=0,
        max_missing_reviewer_total_increase=0,
        max_p95_approval_latency_minutes_increase=30.0,
        max_p95_activation_latency_minutes_increase=30.0,
        max_stale_minutes_increase=30.0,
    )
    assert any("correction_total regression" in item for item in failures)
    assert any("submitted_total regression" in item for item in failures)
    assert any("approved_total regression" in item for item in failures)
    assert any("activated_total regression" in item for item in failures)
    assert any("invalid_event_type_total regression" in item for item in failures)
    assert any("invalid_transition_total regression" in item for item in failures)
    assert any("missing_actor_total regression" in item for item in failures)
    assert any("missing_reviewer_total regression" in item for item in failures)
    assert any("p95_approval_latency_minutes regression" in item for item in failures)
    assert any("p95_activation_latency_minutes regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
