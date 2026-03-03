import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_low_reliability_guardrail.py"
    spec = importlib.util.spec_from_file_location("chat_low_reliability_guardrail", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_guardrail_tracks_low_sensitive_execute():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "intent": "REFUND_REQUEST",
            "risk_level": "WRITE_SENSITIVE",
            "reliability_level": "LOW",
            "decision": "EXECUTE",
            "policy_version": "v1",
            "reason_code": "ROUTE:EXECUTE",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "intent": "REFUND_REQUEST",
            "risk_level": "WRITE_SENSITIVE",
            "reliability_level": "LOW",
            "decision": "BLOCK",
            "policy_version": "v1",
            "reason_code": "GUARD:LOW_RELIABILITY",
        },
    ]
    summary = module.summarize_guardrail(
        rows,
        sensitive_intents={"REFUND_REQUEST"},
        now=datetime(2026, 3, 3, 0, 10, tzinfo=timezone.utc),
    )
    assert summary["low_sensitive_total"] == 2
    assert summary["low_sensitive_execute_total"] == 1
    assert summary["low_sensitive_block_total"] == 1
    assert summary["low_sensitive_guardrail_ratio"] == 0.5


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "low_sensitive_execute_total": 1,
            "low_sensitive_guardrail_ratio": 0.5,
            "invalid_decision_total": 1,
            "missing_policy_version_total": 2,
            "missing_reason_code_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_low_sensitive_execute_total=0,
        min_low_sensitive_guardrail_ratio=1.0,
        max_invalid_decision_total=0,
        max_missing_policy_version_total=0,
        max_missing_reason_code_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "low_sensitive_execute_total": 0,
            "low_sensitive_guardrail_ratio": 1.0,
            "invalid_decision_total": 0,
            "missing_policy_version_total": 0,
            "missing_reason_code_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_low_sensitive_execute_total=0,
        min_low_sensitive_guardrail_ratio=1.0,
        max_invalid_decision_total=0,
        max_missing_policy_version_total=0,
        max_missing_reason_code_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_low_guardrail_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "low_sensitive_execute_total": 0,
                "low_sensitive_guardrail_ratio": 1.0,
                "invalid_decision_total": 0,
                "missing_policy_version_total": 0,
                "missing_reason_code_total": 0,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "low_sensitive_execute_total": 2,
            "low_sensitive_guardrail_ratio": 0.5,
            "invalid_decision_total": 1,
            "missing_policy_version_total": 1,
            "missing_reason_code_total": 1,
            "stale_minutes": 40.0,
        },
        max_low_sensitive_execute_total_increase=0,
        max_low_sensitive_guardrail_ratio_drop=0.05,
        max_invalid_decision_total_increase=0,
        max_missing_policy_version_total_increase=0,
        max_missing_reason_code_total_increase=0,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 6
