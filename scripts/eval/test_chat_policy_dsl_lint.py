import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_policy_dsl_lint.py"
    spec = importlib.util.spec_from_file_location("chat_policy_dsl_lint", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_policy_dsl_flags_lint_issues():
    module = _load_module()
    bundle = {
        "policy_version": "policy-v1",
        "updated_at": "2026-03-03T00:00:00Z",
        "rules": [
            {
                "rule_id": "r1",
                "priority": "high",
                "condition": {
                    "intent": "ORDER_STATUS",
                    "risk_level": "CRITICAL",
                    "foo": "bar",
                    "locale": "ko-KR",
                },
                "action": {"type": "allow"},
            },
            {
                "rule_id": "r1",
                "priority": 10,
                "condition": {},
                "action": {"type": "UNKNOWN_ACTION"},
            },
            {
                "priority": 20,
                "condition": {"reliability_level": "MAYBE", "locale": "english"},
                "action": {"type": "deny"},
                "effective_from": "2026-03-03T01:00:00Z",
                "effective_to": "2026-03-03T00:00:00Z",
            },
        ],
    }
    summary = module.summarize_policy_dsl(bundle, now=datetime(2026, 3, 3, 2, 0, tzinfo=timezone.utc))
    assert summary["rule_total"] == 3
    assert summary["duplicate_rule_id_total"] == 1
    assert summary["missing_rule_id_total"] == 1
    assert summary["invalid_priority_total"] == 1
    assert summary["invalid_action_total"] == 1
    assert summary["empty_condition_total"] == 1
    assert summary["unknown_condition_key_total"] == 1
    assert summary["invalid_risk_level_total"] == 1
    assert summary["invalid_reliability_level_total"] == 1
    assert summary["invalid_locale_total"] == 1
    assert summary["invalid_effective_window_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "policy_version": "",
            "rule_total": 10,
            "missing_rule_id_total": 1,
            "duplicate_rule_id_total": 1,
            "invalid_priority_total": 1,
            "invalid_action_total": 1,
            "empty_condition_total": 1,
            "unknown_condition_key_total": 1,
            "invalid_risk_level_total": 1,
            "invalid_reliability_level_total": 1,
            "invalid_locale_total": 1,
            "invalid_effective_window_total": 1,
            "stale_minutes": 120.0,
        },
        min_rule_total=1,
        require_policy_version=True,
        max_missing_rule_id_total=0,
        max_duplicate_rule_id_total=0,
        max_invalid_priority_total=0,
        max_invalid_action_total=0,
        max_empty_condition_total=0,
        max_unknown_condition_key_total=0,
        max_invalid_risk_level_total=0,
        max_invalid_reliability_level_total=0,
        max_invalid_locale_total=0,
        max_invalid_effective_window_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 12


def test_evaluate_gate_passes_clean_summary():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "policy_version": "policy-v1",
            "rule_total": 2,
            "missing_rule_id_total": 0,
            "duplicate_rule_id_total": 0,
            "invalid_priority_total": 0,
            "invalid_action_total": 0,
            "empty_condition_total": 0,
            "unknown_condition_key_total": 0,
            "invalid_risk_level_total": 0,
            "invalid_reliability_level_total": 0,
            "invalid_locale_total": 0,
            "invalid_effective_window_total": 0,
            "stale_minutes": 5.0,
        },
        min_rule_total=1,
        require_policy_version=True,
        max_missing_rule_id_total=0,
        max_duplicate_rule_id_total=0,
        max_invalid_priority_total=0,
        max_invalid_action_total=0,
        max_empty_condition_total=0,
        max_unknown_condition_key_total=0,
        max_invalid_risk_level_total=0,
        max_invalid_reliability_level_total=0,
        max_invalid_locale_total=0,
        max_invalid_effective_window_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_dsl_lint_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "missing_rule_id_total": 0,
                "duplicate_rule_id_total": 0,
                "invalid_priority_total": 0,
                "invalid_action_total": 0,
                "empty_condition_total": 0,
                "unknown_condition_key_total": 0,
                "invalid_risk_level_total": 0,
                "invalid_reliability_level_total": 0,
                "invalid_locale_total": 0,
                "invalid_effective_window_total": 0,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "missing_rule_id_total": 1,
            "duplicate_rule_id_total": 1,
            "invalid_priority_total": 1,
            "invalid_action_total": 1,
            "empty_condition_total": 1,
            "unknown_condition_key_total": 1,
            "invalid_risk_level_total": 1,
            "invalid_reliability_level_total": 1,
            "invalid_locale_total": 1,
            "invalid_effective_window_total": 1,
            "stale_minutes": 40.0,
        },
        max_missing_rule_id_total_increase=0,
        max_duplicate_rule_id_total_increase=0,
        max_invalid_priority_total_increase=0,
        max_invalid_action_total_increase=0,
        max_empty_condition_total_increase=0,
        max_unknown_condition_key_total_increase=0,
        max_invalid_risk_level_total_increase=0,
        max_invalid_reliability_level_total_increase=0,
        max_invalid_locale_total_increase=0,
        max_invalid_effective_window_total_increase=0,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 11
