import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_followup_prompt.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_followup_prompt", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_followup_prompt_detects_missing_prompt_and_reminder():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "ticket_no": "T-1",
            "event_type": "status_transition",
            "to_status": "WAITING_USER",
            "waiting_hours": 30,
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "ticket_no": "T-2",
            "event_type": "status_transition",
            "to_status": "WAITING_USER",
            "waiting_hours": 30,
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "ticket_no": "T-2",
            "event_type": "followup_prompt",
            "status": "WAITING_USER",
            "guidance_text": "자료를 추가로 올려주세요.",
            "recommended_action": "UPLOAD_DOC",
        },
        {
            "timestamp": "2026-03-03T00:00:21Z",
            "ticket_no": "T-2",
            "event_type": "reminder_sent",
        },
        {
            "timestamp": "2026-03-03T00:00:30Z",
            "ticket_no": "T-3",
            "event_type": "followup_prompt",
            "status": "IN_PROGRESS",
            "guidance_text": "",
            "recommended_action": "",
        },
    ]
    summary = module.summarize_followup_prompt(
        rows,
        reminder_threshold_hours=24.0,
        now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
    )
    assert summary["waiting_user_transition_total"] == 2
    assert summary["waiting_user_prompt_covered_total"] == 1
    assert summary["reminder_due_total"] == 2
    assert summary["reminder_sent_on_due_total"] == 1
    assert summary["prompt_missing_action_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "prompt_missing_action_total": 1,
            "waiting_user_prompt_coverage_ratio": 0.5,
            "reminder_due_coverage_ratio": 0.5,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_prompt_missing_action_total=0,
        min_waiting_user_prompt_coverage_ratio=0.95,
        min_reminder_due_coverage_ratio=0.90,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 4


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "prompt_missing_action_total": 0,
            "waiting_user_prompt_coverage_ratio": 1.0,
            "reminder_due_coverage_ratio": 1.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_prompt_missing_action_total=0,
        min_waiting_user_prompt_coverage_ratio=0.95,
        min_reminder_due_coverage_ratio=0.90,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_followup_prompt_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "prompt_missing_action_total": 0,
                "waiting_user_prompt_coverage_ratio": 1.0,
                "reminder_due_coverage_ratio": 1.0,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "prompt_missing_action_total": 1,
            "waiting_user_prompt_coverage_ratio": 0.6,
            "reminder_due_coverage_ratio": 0.6,
            "stale_minutes": 40.0,
        },
        max_prompt_missing_action_total_increase=0,
        max_waiting_user_prompt_coverage_ratio_drop=0.05,
        max_reminder_due_coverage_ratio_drop=0.05,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 4
