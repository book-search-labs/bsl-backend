import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_claim_action_consistency_guard.py"
    spec = importlib.util.spec_from_file_location("chat_claim_action_consistency_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_claim_action_consistency_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "proposed_action": "REFUND_REQUEST",
            "tool_allowed": True,
            "policy_allowed": True,
            "executed_action": "REFUND_REQUEST",
            "mismatch_detected": False,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "proposed_action": "REFUND_REQUEST",
            "tool_allowed": True,
            "policy_allowed": True,
            "executed_action": "OPEN_SUPPORT_TICKET",
            "mismatch_detected": True,
            "warning_emitted": False,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "proposed_action": "CANCEL_ORDER",
            "tool_allowed": False,
            "policy_allowed": False,
            "blocked_action_removed": True,
            "final_action": "OPEN_SUPPORT_TICKET",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "proposed_action": "ADDRESS_CHANGE",
            "tool_allowed": False,
            "policy_allowed": False,
            "blocked_action_removed": False,
            "final_action": "ADDRESS_CHANGE",
        },
        {
            "timestamp": "2026-03-04T00:00:40Z",
            "action_event": False,
        },
    ]
    summary = module.summarize_claim_action_consistency_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 5
    assert summary["event_total"] == 5
    assert summary["action_event_total"] == 4
    assert summary["consistency_pass_total"] == 1
    assert abs(summary["consistency_pass_ratio"] - 0.25) < 1e-9
    assert summary["mismatch_total"] == 1
    assert summary["mismatch_warning_missing_total"] == 1
    assert abs(summary["mismatch_warning_coverage_ratio"] - 0.0) < 1e-9
    assert summary["infeasible_action_total"] == 2
    assert summary["infeasible_action_removed_total"] == 1
    assert summary["infeasible_action_removal_missing_total"] == 1
    assert abs(summary["infeasible_action_removal_ratio"] - 0.5) < 1e-9
    assert abs(summary["stale_minutes"] - (1.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_claim_action_consistency_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "consistency_pass_ratio": 0.2,
            "mismatch_warning_coverage_ratio": 0.3,
            "infeasible_action_removal_ratio": 0.4,
            "mismatch_total": 3,
            "mismatch_warning_missing_total": 2,
            "infeasible_action_removal_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_consistency_pass_ratio=0.9,
        min_mismatch_warning_coverage_ratio=1.0,
        min_infeasible_action_removal_ratio=1.0,
        max_mismatch_total=0,
        max_mismatch_warning_missing_total=0,
        max_infeasible_action_removal_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "consistency_pass_ratio": 1.0,
            "mismatch_warning_coverage_ratio": 1.0,
            "infeasible_action_removal_ratio": 1.0,
            "mismatch_total": 0,
            "mismatch_warning_missing_total": 0,
            "infeasible_action_removal_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_consistency_pass_ratio=0.0,
        min_mismatch_warning_coverage_ratio=0.0,
        min_infeasible_action_removal_ratio=0.0,
        max_mismatch_total=1000000,
        max_mismatch_warning_missing_total=1000000,
        max_infeasible_action_removal_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
