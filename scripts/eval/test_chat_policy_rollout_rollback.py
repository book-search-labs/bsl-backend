import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_policy_rollout_rollback.py"
    spec = importlib.util.spec_from_file_location("chat_policy_rollout_rollback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_policy_rollout_flags_governance_issues():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "policy_publish",
            "policy_version": "policy-v1",
            "checksum": "",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "event_type": "policy_promote",
            "policy_version": "policy-v2",
            "checksum": "abc",
            "approved_by": "",
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "event_type": "policy_rollback",
            "policy_version": "policy-v2",
            "rollback_to_version": "policy-v0",
            "checksum": "",
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "event_type": "policy_activate",
            "policy_version": "",
            "active_versions": ["policy-v1", "policy-v2"],
        },
        {
            "timestamp": "2026-03-03T00:04:00Z",
            "event_type": "policy_rollout_failed",
            "policy_version": "policy-v2",
        },
    ]
    summary = module.summarize_policy_rollout(rows, now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc))
    assert summary["publish_total"] == 1
    assert summary["promote_total"] == 1
    assert summary["rollback_total"] == 1
    assert summary["activate_total"] == 1
    assert summary["rollout_failure_total"] == 1
    assert summary["missing_policy_version_total"] == 1
    assert summary["promote_without_approval_total"] == 1
    assert summary["checksum_missing_total"] == 2
    assert summary["rollback_to_unknown_version_total"] == 1
    assert summary["active_version_conflict_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "missing_policy_version_total": 1,
            "promote_without_approval_total": 1,
            "checksum_missing_total": 1,
            "rollback_to_unknown_version_total": 1,
            "active_version_conflict_total": 1,
            "rollout_failure_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_missing_policy_version_total=0,
        max_promote_without_approval_total=0,
        max_checksum_missing_total=0,
        max_rollback_to_unknown_version_total=0,
        max_active_version_conflict_total=0,
        max_rollout_failure_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "missing_policy_version_total": 0,
            "promote_without_approval_total": 0,
            "checksum_missing_total": 0,
            "rollback_to_unknown_version_total": 0,
            "active_version_conflict_total": 0,
            "rollout_failure_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_missing_policy_version_total=0,
        max_promote_without_approval_total=0,
        max_checksum_missing_total=0,
        max_rollback_to_unknown_version_total=0,
        max_active_version_conflict_total=0,
        max_rollout_failure_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_rollout_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "missing_policy_version_total": 0,
                "promote_without_approval_total": 0,
                "checksum_missing_total": 0,
                "rollback_to_unknown_version_total": 0,
                "active_version_conflict_total": 0,
                "rollout_failure_total": 0,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "missing_policy_version_total": 1,
            "promote_without_approval_total": 1,
            "checksum_missing_total": 1,
            "rollback_to_unknown_version_total": 1,
            "active_version_conflict_total": 1,
            "rollout_failure_total": 1,
            "stale_minutes": 40.0,
        },
        max_missing_policy_version_total_increase=0,
        max_promote_without_approval_total_increase=0,
        max_checksum_missing_total_increase=0,
        max_rollback_to_unknown_version_total_increase=0,
        max_active_version_conflict_total_increase=0,
        max_rollout_failure_total_increase=0,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 7
