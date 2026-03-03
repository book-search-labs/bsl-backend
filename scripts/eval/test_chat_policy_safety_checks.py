import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_policy_safety_checks.py"
    spec = importlib.util.spec_from_file_location("chat_policy_safety_checks", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_policy_safety_flags_risks():
    module = _load_module()
    bundle = {
        "policy_version": "policy-v1",
        "updated_at": "2026-03-03T00:00:00Z",
        "rules": [
            {
                "rule_id": "r1",
                "priority": 100,
                "enabled": True,
                "condition": {"intent": ["REFUND_REQUEST"], "risk_level": ["HIGH"]},
                "action": {"type": "ALLOW"},
            },
            {
                "rule_id": "r2",
                "priority": 100,
                "enabled": True,
                "condition": {"intent": ["REFUND_REQUEST"], "risk_level": ["HIGH"]},
                "action": {"type": "DENY", "reason_code": "SAFE_BLOCK"},
            },
            {
                "rule_id": "r3",
                "priority": 100,
                "enabled": True,
                "condition": {"intent": ["REFUND_REQUEST"], "risk_level": ["HIGH"]},
                "action": {"type": "DENY", "reason_code": "SAFE_BLOCK"},
            },
        ],
    }
    summary = module.summarize_policy_safety(
        bundle,
        sensitive_intents={"REFUND_REQUEST", "CANCEL_ORDER"},
        guard_actions={"DENY", "REQUIRE_CONFIRMATION", "HANDOFF"},
        now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
    )
    assert summary["rule_total"] == 3
    assert summary["contradictory_rule_pair_total"] == 1
    assert summary["duplicate_condition_total"] == 1
    assert summary["missing_sensitive_guard_intent_total"] == 1
    assert summary["unsafe_high_risk_allow_total"] == 2
    assert summary["missing_reason_code_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "rule_total": 10,
            "contradictory_rule_pair_total": 1,
            "duplicate_condition_total": 1,
            "missing_sensitive_guard_intent_total": 1,
            "unsafe_high_risk_allow_total": 1,
            "missing_reason_code_total": 1,
            "stale_minutes": 120.0,
        },
        min_rule_total=1,
        max_contradictory_rule_pair_total=0,
        max_duplicate_condition_total=0,
        max_missing_sensitive_guard_intent_total=0,
        max_unsafe_high_risk_allow_total=0,
        max_missing_reason_code_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "rule_total": 0,
            "contradictory_rule_pair_total": 0,
            "duplicate_condition_total": 0,
            "missing_sensitive_guard_intent_total": 0,
            "unsafe_high_risk_allow_total": 0,
            "missing_reason_code_total": 0,
            "stale_minutes": 0.0,
        },
        min_rule_total=0,
        max_contradictory_rule_pair_total=0,
        max_duplicate_condition_total=0,
        max_missing_sensitive_guard_intent_total=0,
        max_unsafe_high_risk_allow_total=0,
        max_missing_reason_code_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []
