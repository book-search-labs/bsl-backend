import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_plan_persistence_resume_guard.py"
    spec = importlib.util.spec_from_file_location("chat_plan_persistence_resume_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_plan_persistence_resume_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "resume_attempt": True,
            "plan_id": "p1",
            "plan_state_restored": True,
            "checkpoint_index": 2,
            "failed_step_index": 2,
            "resumed_from_step_index": 2,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "session_reentered": True,
            "plan_id": "",
            "plan_state_loaded": False,
            "failed_step_index": 3,
            "resumed_from_step_index": 1,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "resume_attempt": False,
            "next_action": "OPEN_SUPPORT_TICKET",
            "handoff_summary": "",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "resume_attempt": True,
            "plan_id": "p2",
            "plan_state_restored": True,
            "checkpoint_id": "ck-2",
            "ticket_handoff": True,
            "handoff_summary_present": True,
        },
    ]
    summary = module.summarize_plan_persistence_resume_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["resume_attempt_total"] == 3
    assert summary["resume_state_restored_total"] == 2
    assert abs(summary["resume_success_rate"] - (2.0 / 3.0)) < 1e-9
    assert summary["checkpoint_missing_total"] == 1
    assert summary["plan_persistence_missing_total"] == 1
    assert summary["resume_from_failed_step_required_total"] == 2
    assert summary["resume_from_failed_step_missing_total"] == 1
    assert summary["ticket_handoff_total"] == 2
    assert summary["ticket_handoff_summary_missing_total"] == 1
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_plan_persistence_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "resume_success_rate": 0.2,
            "checkpoint_missing_total": 2,
            "plan_persistence_missing_total": 1,
            "resume_from_failed_step_missing_total": 1,
            "ticket_handoff_summary_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_resume_success_rate=0.95,
        max_checkpoint_missing_total=0,
        max_plan_persistence_missing_total=0,
        max_resume_from_failed_step_missing_total=0,
        max_ticket_handoff_summary_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "resume_success_rate": 1.0,
            "checkpoint_missing_total": 0,
            "plan_persistence_missing_total": 0,
            "resume_from_failed_step_missing_total": 0,
            "ticket_handoff_summary_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_resume_success_rate=0.0,
        max_checkpoint_missing_total=1000000,
        max_plan_persistence_missing_total=1000000,
        max_resume_from_failed_step_missing_total=1000000,
        max_ticket_handoff_summary_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
