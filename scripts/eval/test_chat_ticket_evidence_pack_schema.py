import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_evidence_pack_schema.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_evidence_pack_schema", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_evidence_pack_schema_tracks_required_fields_and_pii():
    module = _load_module()
    rows = [
        {
            "ticket_id": "t1",
            "timestamp": "2026-03-03T00:00:00Z",
            "summary": "주문번호 O-1 상태 확인",
            "intent": "ORDER_STATUS",
            "executed_tools": [{"name": "order.lookup", "version": "1.2.0"}],
            "error_codes": [],
            "order_id": "O-1",
            "policy_version": "policy-v1",
        },
        {
            "ticket_id": "t2",
            "timestamp": "2026-03-03T00:01:00Z",
            "summary": "연락처는 01012345678 입니다.",
            "intent": "",
            "executed_tools": [],
            "policy_version": "",
        },
        {
            "ticket_id": "t2",
            "timestamp": "2026-03-03T00:02:00Z",
            "summary": "",
            "intent": "REFUND",
            "executed_tools": [{"name": "refund.check"}],
            "error_codes": ["E100"],
            "shipment_id": "S-1",
            "policy_version": "policy-v1",
        },
    ]
    summary = module.summarize_evidence_pack_schema(
        rows,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["pack_total"] == 3
    assert summary["duplicate_ticket_total"] == 1
    assert summary["missing_summary_total"] == 1
    assert summary["missing_intent_total"] == 1
    assert summary["missing_tool_trace_total"] == 1
    assert summary["missing_error_code_total"] == 1
    assert summary["missing_reference_total"] == 1
    assert summary["missing_policy_version_total"] == 1
    assert summary["missing_tool_version_total"] == 2
    assert summary["unmasked_pii_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_evidence_pack_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "duplicate_ticket_total": 2,
            "missing_summary_total": 1,
            "missing_intent_total": 1,
            "missing_tool_trace_total": 1,
            "missing_error_code_total": 1,
            "missing_reference_total": 1,
            "missing_policy_version_total": 1,
            "missing_tool_version_total": 1,
            "unmasked_pii_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        max_duplicate_ticket_total=0,
        max_missing_summary_total=0,
        max_missing_intent_total=0,
        max_missing_tool_trace_total=0,
        max_missing_error_code_total=0,
        max_missing_reference_total=0,
        max_missing_policy_version_total=0,
        max_missing_tool_version_total=0,
        max_unmasked_pii_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 11


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "duplicate_ticket_total": 0,
            "missing_summary_total": 0,
            "missing_intent_total": 0,
            "missing_tool_trace_total": 0,
            "missing_error_code_total": 0,
            "missing_reference_total": 0,
            "missing_policy_version_total": 0,
            "missing_tool_version_total": 0,
            "unmasked_pii_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_duplicate_ticket_total=1000000,
        max_missing_summary_total=1000000,
        max_missing_intent_total=1000000,
        max_missing_tool_trace_total=1000000,
        max_missing_error_code_total=1000000,
        max_missing_reference_total=1000000,
        max_missing_policy_version_total=1000000,
        max_missing_tool_version_total=1000000,
        max_unmasked_pii_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_evidence_pack_schema_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "pack_total": 10,
            "duplicate_ticket_total": 0,
            "missing_summary_total": 0,
            "missing_intent_total": 0,
            "missing_tool_trace_total": 0,
            "missing_error_code_total": 0,
            "missing_reference_total": 0,
            "missing_policy_version_total": 0,
            "missing_tool_version_total": 0,
            "unmasked_pii_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "pack_total": 1,
            "duplicate_ticket_total": 1,
            "missing_summary_total": 1,
            "missing_intent_total": 1,
            "missing_tool_trace_total": 1,
            "missing_error_code_total": 1,
            "missing_reference_total": 1,
            "missing_policy_version_total": 1,
            "missing_tool_version_total": 1,
            "unmasked_pii_total": 1,
            "stale_minutes": 80.0,
        },
        max_pack_total_drop=1,
        max_duplicate_ticket_total_increase=0,
        max_missing_summary_total_increase=0,
        max_missing_intent_total_increase=0,
        max_missing_tool_trace_total_increase=0,
        max_missing_error_code_total_increase=0,
        max_missing_reference_total_increase=0,
        max_missing_policy_version_total_increase=0,
        max_missing_tool_version_total_increase=0,
        max_unmasked_pii_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("pack_total regression" in item for item in failures)
    assert any("duplicate_ticket_total regression" in item for item in failures)
    assert any("missing_summary_total regression" in item for item in failures)
    assert any("missing_intent_total regression" in item for item in failures)
    assert any("missing_tool_trace_total regression" in item for item in failures)
    assert any("missing_error_code_total regression" in item for item in failures)
    assert any("missing_reference_total regression" in item for item in failures)
    assert any("missing_policy_version_total regression" in item for item in failures)
    assert any("missing_tool_version_total regression" in item for item in failures)
    assert any("unmasked_pii_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
