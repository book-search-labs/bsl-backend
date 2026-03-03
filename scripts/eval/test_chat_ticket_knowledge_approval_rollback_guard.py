import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_knowledge_approval_rollback_guard.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_knowledge_approval_rollback_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_ticket_knowledge_approval_rollback_guard_tracks_pipeline_integrity():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "proposal_id": "p-1",
            "approved": True,
            "approved_by": "ops-1",
            "approved_at": "2026-03-03T00:30:00Z",
            "indexed": True,
            "indexed_at": "2026-03-03T00:45:00Z",
            "candidate_created_at": "2026-03-03T00:00:00Z",
        },
        {
            "timestamp": "2026-03-03T01:00:00Z",
            "proposal_id": "p-2",
            "approved": False,
            "indexed": True,
            "indexed_at": "2026-03-03T01:10:00Z",
        },
        {
            "timestamp": "2026-03-03T01:30:00Z",
            "proposal_id": "p-3",
            "approval_status": "pending",
            "candidate_created_at": "2026-03-03T00:00:00Z",
        },
        {
            "timestamp": "2026-03-03T02:00:00Z",
            "proposal_id": "p-4",
            "rollback_applied": True,
            "rollback_reason": "",
        },
    ]

    summary = module.summarize_ticket_knowledge_approval_rollback_guard(
        rows,
        pending_sla_hours=2.0,
        now=datetime(2026, 3, 3, 5, 0, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["candidate_total"] == 4
    assert summary["approved_total"] == 1
    assert summary["indexed_total"] == 2
    assert summary["unapproved_index_total"] == 1
    assert summary["approval_evidence_missing_total"] == 0
    assert summary["pending_total"] == 1
    assert summary["pending_sla_breach_total"] == 1
    assert summary["rollback_total"] == 1
    assert summary["rollback_without_reason_total"] == 1
    assert summary["p95_candidate_to_approval_minutes"] == 30.0
    assert summary["p95_approval_to_index_minutes"] == 15.0
    assert summary["stale_minutes"] == 180.0


def test_evaluate_gate_detects_ticket_knowledge_approval_rollback_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "candidate_total": 1,
            "approved_total": 0,
            "indexed_total": 0,
            "unapproved_index_total": 2,
            "approval_evidence_missing_total": 1,
            "pending_sla_breach_total": 3,
            "rollback_without_reason_total": 1,
            "p95_candidate_to_approval_minutes": 500.0,
            "p95_approval_to_index_minutes": 300.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_candidate_total=2,
        min_approved_total=1,
        min_indexed_total=1,
        max_unapproved_index_total=0,
        max_approval_evidence_missing_total=0,
        max_pending_sla_breach_total=0,
        max_rollback_without_reason_total=0,
        max_p95_candidate_to_approval_minutes=120.0,
        max_p95_approval_to_index_minutes=60.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 11


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "candidate_total": 0,
            "approved_total": 0,
            "indexed_total": 0,
            "unapproved_index_total": 0,
            "approval_evidence_missing_total": 0,
            "pending_sla_breach_total": 0,
            "rollback_without_reason_total": 0,
            "p95_candidate_to_approval_minutes": 0.0,
            "p95_approval_to_index_minutes": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_candidate_total=0,
        min_approved_total=0,
        min_indexed_total=0,
        max_unapproved_index_total=1000000,
        max_approval_evidence_missing_total=1000000,
        max_pending_sla_breach_total=1000000,
        max_rollback_without_reason_total=1000000,
        max_p95_candidate_to_approval_minutes=1000000.0,
        max_p95_approval_to_index_minutes=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
