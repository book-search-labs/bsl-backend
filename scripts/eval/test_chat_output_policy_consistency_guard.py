import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_output_policy_consistency_guard.py"
    spec = importlib.util.spec_from_file_location("chat_output_policy_consistency_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_output_policy_consistency_guard_tracks_mismatch_and_reason_codes():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "policy_decision": "allow",
            "output_decision": "allow",
            "reason_code": "ALLOW_OK",
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "policy_decision": "deny",
            "output_decision": "allow",
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "policy_decision": "clarify",
            "output_decision": "allow",
            "clarification_prompted": False,
            "reason_code": "NEED_CLARIFY",
            "downgraded": True,
        },
        {
            "timestamp": "2026-03-03T00:00:30Z",
            "policy_decision": "allow",
            "output_decision": "deny",
            "policy_consistent": True,
            "reason_code": "",
            "downgraded": True,
        },
    ]

    summary = module.summarize_output_policy_consistency_guard(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["policy_checked_total"] == 4
    assert summary["mismatch_total"] == 2
    assert summary["consistency_ratio"] == 0.5
    assert summary["deny_bypass_total"] == 1
    assert summary["clarify_ignored_total"] == 1
    assert summary["missing_reason_code_total"] == 1
    assert summary["downgrade_without_reason_total"] == 1
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_output_policy_consistency_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "policy_checked_total": 2,
            "consistency_ratio": 0.6,
            "mismatch_total": 3,
            "deny_bypass_total": 1,
            "clarify_ignored_total": 2,
            "missing_reason_code_total": 1,
            "downgrade_without_reason_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_policy_checked_total=3,
        min_consistency_ratio=0.99,
        max_mismatch_total=0,
        max_deny_bypass_total=0,
        max_clarify_ignored_total=0,
        max_missing_reason_code_total=0,
        max_downgrade_without_reason_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "policy_checked_total": 0,
            "consistency_ratio": 1.0,
            "mismatch_total": 0,
            "deny_bypass_total": 0,
            "clarify_ignored_total": 0,
            "missing_reason_code_total": 0,
            "downgrade_without_reason_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_policy_checked_total=0,
        min_consistency_ratio=0.0,
        max_mismatch_total=1000000,
        max_deny_bypass_total=1000000,
        max_clarify_ignored_total=1000000,
        max_missing_reason_code_total=1000000,
        max_downgrade_without_reason_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
