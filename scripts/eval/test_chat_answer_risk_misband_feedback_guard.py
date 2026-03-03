import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_answer_risk_misband_feedback_guard.py"
    spec = importlib.util.spec_from_file_location("chat_answer_risk_misband_feedback_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_answer_risk_misband_feedback_guard_tracks_feedback_loop():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "risk_band": "R2",
            "reason_code": "RISK:EVIDENCE_LOW",
            "trace_id": "tr-1",
            "request_id": "rq-1",
        },
        {
            "timestamp": "2026-03-04T00:10:00Z",
            "feedback_id": "fb-1",
            "feedback_type": "MISBAND",
            "risk_band": "R2",
            "adjudicated_band": "R3",
            "response_id": "resp-1",
            "feedback_created_at": "2026-03-04T00:00:00Z",
            "feedback_resolved_at": "2026-03-04T00:10:00Z",
            "feedback_status": "RESOLVED",
            "reason_code": "RISK:UPBAND",
            "trace_id": "tr-2",
            "request_id": "rq-2",
        },
        {
            "timestamp": "2026-03-04T00:10:00Z",
            "feedback_id": "fb-2",
            "feedback_type": "MISBAND",
            "risk_band": "R2",
            "adjudicated_band": "R1",
            "response_id": "resp-2",
            "feedback_created_at": "2026-03-04T00:05:00Z",
            "feedback_status": "OPEN",
            "reason_code": "",
            "trace_id": "",
            "request_id": "",
        },
        {
            "timestamp": "2026-03-04T00:08:00Z",
            "feedback_id": "fb-3",
            "feedback_type": "FEEDBACK",
            "risk_band": "R1",
            "adjudicated_band": "R1",
            "feedback_created_at": "2026-03-04T00:03:00Z",
            "feedback_resolved_at": "2026-03-04T00:08:00Z",
            "feedback_status": "RESOLVED",
            "reason_code": "ACK",
            "trace_id": "tr-4",
            "request_id": "rq-4",
        },
    ]
    summary = module.summarize_answer_risk_misband_feedback_guard(
        rows,
        unresolved_sla_minutes=60.0,
        now=datetime(2026, 3, 4, 1, 10, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["feedback_total"] == 3
    assert summary["misband_total"] == 2
    assert summary["resolved_misband_total"] == 1
    assert abs(summary["misband_resolution_ratio"] - 0.5) < 1e-9
    assert summary["feedback_linked_total"] == 2
    assert abs(summary["feedback_linkage_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["reason_missing_total"] == 1
    assert summary["audit_context_missing_total"] == 1
    assert summary["unresolved_feedback_total"] == 1
    assert abs(summary["p95_feedback_latency_minutes"] - 10.0) < 1e-9
    assert abs(summary["stale_minutes"] - 60.0) < 1e-9


def test_evaluate_gate_detects_answer_risk_misband_feedback_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "feedback_total": 1,
            "feedback_linkage_ratio": 0.2,
            "misband_resolution_ratio": 0.2,
            "reason_missing_total": 2,
            "audit_context_missing_total": 2,
            "unresolved_feedback_total": 2,
            "p95_feedback_latency_minutes": 120.0,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_feedback_total=2,
        min_feedback_linkage_ratio=0.95,
        min_misband_resolution_ratio=0.95,
        max_reason_missing_total=0,
        max_audit_context_missing_total=0,
        max_unresolved_feedback_total=0,
        max_p95_feedback_latency_minutes=60.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "feedback_total": 0,
            "feedback_linkage_ratio": 1.0,
            "misband_resolution_ratio": 1.0,
            "reason_missing_total": 0,
            "audit_context_missing_total": 0,
            "unresolved_feedback_total": 0,
            "p95_feedback_latency_minutes": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_feedback_total=0,
        min_feedback_linkage_ratio=0.0,
        min_misband_resolution_ratio=0.0,
        max_reason_missing_total=1000000,
        max_audit_context_missing_total=1000000,
        max_unresolved_feedback_total=1000000,
        max_p95_feedback_latency_minutes=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
