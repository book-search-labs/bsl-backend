import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_reasoning_budget_model.py"
    spec = importlib.util.spec_from_file_location("chat_reasoning_budget_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_budget_model_detects_duplicates_and_missing_sensitive():
    module = _load_module()
    payload = {
        "version": "v1",
        "updated_at": "2026-03-03T00:00:00Z",
        "defaults": {"token_budget": 3000, "step_budget": 8, "tool_call_budget": 3},
        "policies": [
            {"tenant_id": "default", "intent": "REFUND_REQUEST", "token_budget": 2000, "step_budget": 6, "tool_call_budget": 2},
            {"tenant_id": "default", "intent": "REFUND_REQUEST", "token_budget": -1, "step_budget": 4, "tool_call_budget": 1},
            {"tenant_id": "default", "intent": "CANCEL_ORDER", "token_budget": 1200, "step_budget": 4},
        ],
    }
    summary = module.summarize_budget_model(
        payload,
        required_sensitive_intents={"CANCEL_ORDER", "REFUND_REQUEST", "ADDRESS_CHANGE", "PAYMENT_CHANGE"},
        now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
    )

    assert summary["policy_total"] == 4
    assert summary["duplicate_scope_total"] == 1
    assert summary["invalid_limit_total"] >= 1
    assert summary["missing_budget_field_total"] >= 1
    assert summary["missing_sensitive_intent_total"] == 2
    assert summary["version_missing"] is False


def test_evaluate_gate_detects_budget_model_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "policy_total": 0,
            "version_missing": True,
            "missing_budget_field_total": 3,
            "invalid_limit_total": 2,
            "duplicate_scope_total": 1,
            "missing_sensitive_intent_total": 4,
            "stale_minutes": 120.0,
        },
        min_policy_total=1,
        require_policy_version=True,
        max_missing_budget_field_total=0,
        max_invalid_limit_total=0,
        max_duplicate_scope_total=0,
        max_missing_sensitive_intent_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_open_thresholds():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "policy_total": 0,
            "version_missing": True,
            "missing_budget_field_total": 0,
            "invalid_limit_total": 0,
            "duplicate_scope_total": 0,
            "missing_sensitive_intent_total": 0,
            "stale_minutes": 0.0,
        },
        min_policy_total=0,
        require_policy_version=False,
        max_missing_budget_field_total=1000000,
        max_invalid_limit_total=1000000,
        max_duplicate_scope_total=1000000,
        max_missing_sensitive_intent_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_budget_model_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "policy_total": 10,
            "version_missing": False,
            "missing_budget_field_total": 0,
            "invalid_limit_total": 0,
            "duplicate_scope_total": 0,
            "missing_sensitive_intent_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "policy_total": 2,
            "version_missing": True,
            "missing_budget_field_total": 3,
            "invalid_limit_total": 2,
            "duplicate_scope_total": 1,
            "missing_sensitive_intent_total": 4,
            "stale_minutes": 80.0,
        },
        max_policy_total_drop=1,
        max_version_missing_total_increase=0,
        max_missing_budget_field_total_increase=0,
        max_invalid_limit_total_increase=0,
        max_duplicate_scope_total_increase=0,
        max_missing_sensitive_intent_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("policy_total regression" in item for item in failures)
    assert any("version_missing regression" in item for item in failures)
    assert any("missing_budget_field_total regression" in item for item in failures)
    assert any("invalid_limit_total regression" in item for item in failures)
    assert any("duplicate_scope_total regression" in item for item in failures)
    assert any("missing_sensitive_intent_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
