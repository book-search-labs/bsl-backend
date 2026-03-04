import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_reasoning_budget_audit_explainability.py"
    spec = importlib.util.spec_from_file_location("chat_reasoning_budget_audit_explainability", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_audit_explainability_counts_missing_fields():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "BUDGET_EXCEEDED",
            "reason_code": "BUDGET_TOKEN_EXCEEDED",
            "trace_id": "t1",
            "request_id": "r1",
            "budget_type": "token",
            "user_message": "budget exceeded",
            "intent": "REFUND_REQUEST",
            "tenant_id": "default",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "event_type": "BUDGET_ABORT",
            "reason_code": "",
            "trace_id": "",
            "request_id": "",
            "budget_type": "",
            "intent": "",
            "tenant_id": "",
        },
    ]
    summary = module.summarize_audit_explainability(
        rows,
        now=datetime(2026, 3, 3, 0, 2, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 2
    assert summary["critical_event_total"] == 2
    assert summary["missing_reason_code_total"] == 1
    assert summary["missing_trace_id_total"] == 1
    assert summary["missing_request_id_total"] == 1
    assert summary["missing_budget_type_total"] == 1
    assert summary["explainability_missing_total"] == 1
    assert summary["dashboard_tag_missing_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "missing_reason_code_total": 2,
            "unknown_reason_code_total": 1,
            "missing_trace_id_total": 2,
            "missing_request_id_total": 2,
            "missing_budget_type_total": 3,
            "explainability_missing_total": 4,
            "dashboard_tag_missing_total": 5,
            "stale_minutes": 120.0,
        },
        min_window=20,
        max_missing_reason_code_total=0,
        max_unknown_reason_code_total=0,
        max_missing_trace_id_total=0,
        max_missing_request_id_total=0,
        max_missing_budget_type_total=0,
        max_explainability_missing_total=0,
        max_dashboard_tag_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_window_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "missing_reason_code_total": 0,
            "unknown_reason_code_total": 0,
            "missing_trace_id_total": 0,
            "missing_request_id_total": 0,
            "missing_budget_type_total": 0,
            "explainability_missing_total": 0,
            "dashboard_tag_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_missing_reason_code_total=1000000,
        max_unknown_reason_code_total=1000000,
        max_missing_trace_id_total=1000000,
        max_missing_request_id_total=1000000,
        max_missing_budget_type_total=1000000,
        max_explainability_missing_total=1000000,
        max_dashboard_tag_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_audit_explainability_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "critical_event_total": 10,
            "missing_reason_code_total": 0,
            "unknown_reason_code_total": 0,
            "missing_trace_id_total": 0,
            "missing_request_id_total": 0,
            "missing_budget_type_total": 0,
            "explainability_missing_total": 0,
            "dashboard_tag_missing_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "critical_event_total": 2,
            "missing_reason_code_total": 2,
            "unknown_reason_code_total": 1,
            "missing_trace_id_total": 2,
            "missing_request_id_total": 2,
            "missing_budget_type_total": 2,
            "explainability_missing_total": 3,
            "dashboard_tag_missing_total": 4,
            "stale_minutes": 80.0,
        },
        max_critical_event_total_drop=1,
        max_missing_reason_code_total_increase=0,
        max_unknown_reason_code_total_increase=0,
        max_missing_trace_id_total_increase=0,
        max_missing_request_id_total_increase=0,
        max_missing_budget_type_total_increase=0,
        max_explainability_missing_total_increase=0,
        max_dashboard_tag_missing_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("critical_event_total regression" in item for item in failures)
    assert any("missing_reason_code_total regression" in item for item in failures)
    assert any("unknown_reason_code_total regression" in item for item in failures)
    assert any("missing_trace_id_total regression" in item for item in failures)
    assert any("missing_request_id_total regression" in item for item in failures)
    assert any("missing_budget_type_total regression" in item for item in failures)
    assert any("explainability_missing_total regression" in item for item in failures)
    assert any("dashboard_tag_missing_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
