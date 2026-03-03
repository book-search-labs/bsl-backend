import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_korean_governance_loop_guard.py"
    spec = importlib.util.spec_from_file_location("chat_korean_governance_loop_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_korean_governance_loop_guard_tracks_approval_and_feedback():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "dictionary_update_proposed",
            "proposal_id": "pr-1",
            "status": "pending",
            "reason_code": "DICT_UPDATE_REQUESTED",
        },
        {
            "timestamp": "2026-03-03T01:00:00Z",
            "event_type": "dictionary_update_deployed",
            "proposal_id": "pr-2",
            "approved": True,
            "approved_by": "ops-1",
            "approved_at": "2026-03-03T00:55:00Z",
            "reason_code": "DICT_UPDATE_APPROVED",
        },
        {
            "timestamp": "2026-03-03T02:00:00Z",
            "event_type": "style_policy_update_deployed",
            "proposal_id": "pr-3",
            "approved": False,
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-03T02:30:00Z",
            "event_type": "style_feedback_resolved",
            "feedback_id": "fb-1",
            "triaged": True,
            "resolved": True,
            "reason_code": "STYLE_PATCHED",
        },
        {
            "timestamp": "2026-03-03T03:00:00Z",
            "event_type": "style_feedback_submitted",
            "feedback_id": "fb-2",
            "triaged": False,
        },
    ]

    summary = module.summarize_korean_governance_loop_guard(
        rows,
        pending_sla_hours=2.0,
        now=datetime(2026, 3, 3, 5, 0, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["update_event_total"] == 3
    assert summary["update_deployed_total"] == 2
    assert summary["approved_update_total"] == 1
    assert summary["approval_evidence_missing_total"] == 0
    assert summary["unaudited_deploy_total"] == 1
    assert summary["pending_update_total"] == 1
    assert summary["pending_update_sla_breach_total"] == 1
    assert summary["feedback_event_total"] == 2
    assert summary["feedback_triaged_total"] == 1
    assert summary["feedback_closed_total"] == 1
    assert summary["feedback_triage_ratio"] == 0.5
    assert summary["feedback_closure_ratio"] == 1.0
    assert summary["reason_code_missing_total"] == 1
    assert summary["stale_minutes"] == 120.0


def test_evaluate_gate_detects_korean_governance_loop_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "update_event_total": 1,
            "feedback_event_total": 1,
            "feedback_triage_ratio": 0.2,
            "feedback_closure_ratio": 0.5,
            "unaudited_deploy_total": 2,
            "approval_evidence_missing_total": 1,
            "pending_update_sla_breach_total": 3,
            "reason_code_missing_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_update_event_total=2,
        min_feedback_event_total=2,
        min_feedback_triage_ratio=0.95,
        min_feedback_closure_ratio=0.95,
        max_unaudited_deploy_total=0,
        max_approval_evidence_missing_total=0,
        max_pending_update_sla_breach_total=0,
        max_reason_code_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "update_event_total": 0,
            "feedback_event_total": 0,
            "feedback_triage_ratio": 1.0,
            "feedback_closure_ratio": 1.0,
            "unaudited_deploy_total": 0,
            "approval_evidence_missing_total": 0,
            "pending_update_sla_breach_total": 0,
            "reason_code_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_update_event_total=0,
        min_feedback_event_total=0,
        min_feedback_triage_ratio=0.0,
        min_feedback_closure_ratio=0.0,
        max_unaudited_deploy_total=1000000,
        max_approval_evidence_missing_total=1000000,
        max_pending_update_sla_breach_total=1000000,
        max_reason_code_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
