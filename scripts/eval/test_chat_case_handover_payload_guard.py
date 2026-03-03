import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_case_handover_payload_guard.py"
    spec = importlib.util.spec_from_file_location("chat_case_handover_payload_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_case_handover_payload_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "escalated": True,
            "handover_payload": {
                "summary": "주문 취소 요청 이력 요약",
                "executed_actions": ["ORDER_LOOKUP", "CANCEL_SIMULATION"],
                "policy_evidence": ["CANCEL_WINDOW_VALID"],
                "customer_email": "u***@example.com",
            },
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "escalated": True,
            "handover_payload_present": False,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "escalated": True,
            "handover_payload": {
                "summary": "환불 문의",
                "executed_actions": [],
                "policy_evidence": [],
                "customer_email": "user@example.com",
            },
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "escalated": False,
        },
    ]
    summary = module.summarize_case_handover_payload_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["escalation_total"] == 3
    assert summary["payload_present_total"] == 2
    assert summary["payload_missing_total"] == 1
    assert summary["summary_missing_total"] == 1
    assert summary["actions_missing_total"] == 2
    assert summary["policy_evidence_missing_total"] == 2
    assert summary["masking_violation_total"] == 1
    assert summary["complete_payload_total"] == 1
    assert abs(summary["payload_completeness_ratio"] - (1.0 / 3.0)) < 1e-9
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_case_handover_payload_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "payload_completeness_ratio": 0.3,
            "payload_missing_total": 2,
            "summary_missing_total": 1,
            "actions_missing_total": 3,
            "policy_evidence_missing_total": 2,
            "masking_violation_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_payload_completeness_ratio=0.95,
        max_payload_missing_total=0,
        max_summary_missing_total=0,
        max_actions_missing_total=0,
        max_policy_evidence_missing_total=0,
        max_masking_violation_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "payload_completeness_ratio": 1.0,
            "payload_missing_total": 0,
            "summary_missing_total": 0,
            "actions_missing_total": 0,
            "policy_evidence_missing_total": 0,
            "masking_violation_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_payload_completeness_ratio=0.0,
        max_payload_missing_total=1000000,
        max_summary_missing_total=1000000,
        max_actions_missing_total=1000000,
        max_policy_evidence_missing_total=1000000,
        max_masking_violation_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
