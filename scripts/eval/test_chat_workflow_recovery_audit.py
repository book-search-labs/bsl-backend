import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_workflow_recovery_audit.py"
    spec = importlib.util.spec_from_file_location("chat_workflow_recovery_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_recovery_audit_tracks_recovery_and_audit_fields():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-03T00:00:00Z", "workflow_id": "w1", "event_type": "interrupted"},
        {"timestamp": "2026-03-03T00:00:30Z", "workflow_id": "w1", "event_type": "recovered"},
        {
            "timestamp": "2026-03-03T00:00:40Z",
            "workflow_id": "w1",
            "event_type": "step",
            "step": "validate",
            "reason_code": "OK",
            "tool_name": "validate_tool",
            "action_type": "WRITE",
            "idempotency_key": "k1",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "workflow_id": "w2",
            "event_type": "step",
            "step": "",
            "reason_code": "",
            "tool_name": "",
            "action_type": "WRITE",
            "idempotency_key": "",
        },
    ]
    summary = module.summarize_recovery_audit(
        rows,
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )
    assert summary["interrupted_workflow_total"] == 1
    assert summary["recovered_workflow_total"] == 1
    assert summary["recovery_success_ratio"] == 1.0
    assert summary["audit_missing_fields_total"] == 1
    assert summary["audit_write_without_idempotency_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "recovery_success_ratio": 0.5,
            "recovery_latency_p95_sec": 1000.0,
            "audit_missing_fields_total": 2,
            "audit_write_without_idempotency_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        min_recovery_success_ratio=0.95,
        max_recovery_latency_p95_sec=600.0,
        max_audit_missing_fields_total=0,
        max_write_without_idempotency_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_passes_when_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "recovery_success_ratio": 1.0,
            "recovery_latency_p95_sec": 30.0,
            "audit_missing_fields_total": 0,
            "audit_write_without_idempotency_total": 0,
            "stale_minutes": 5.0,
        },
        min_window=1,
        min_recovery_success_ratio=0.95,
        max_recovery_latency_p95_sec=600.0,
        max_audit_missing_fields_total=0,
        max_write_without_idempotency_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "recovery_success_ratio": 0.0,
            "recovery_latency_p95_sec": 0.0,
            "audit_missing_fields_total": 0,
            "audit_write_without_idempotency_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_recovery_success_ratio=0.95,
        max_recovery_latency_p95_sec=600.0,
        max_audit_missing_fields_total=0,
        max_write_without_idempotency_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []
