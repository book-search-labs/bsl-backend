import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_sensitive_action_undo_audit.py"
    spec = importlib.util.spec_from_file_location("chat_sensitive_action_undo_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_undo_audit_flags_window_violation_and_missing_audit():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "action_id": "a1",
            "event_type": "request",
            "actor_id": "u1",
            "target_id": "o1",
            "reason_code": "REQ",
            "trace_id": "t1",
            "request_id": "r1",
        },
        {
            "timestamp": "2026-03-03T00:00:01Z",
            "action_id": "a1",
            "event_type": "confirm",
            "actor_id": "u1",
            "target_id": "o1",
            "reason_code": "CONF",
            "trace_id": "t1",
            "request_id": "r1",
        },
        {
            "timestamp": "2026-03-03T00:00:02Z",
            "action_id": "a1",
            "event_type": "execute",
            "undo_supported": True,
            "undo_window_sec": 5,
            "actor_id": "u1",
            "target_id": "o1",
            "reason_code": "EXEC",
            "trace_id": "t1",
            "request_id": "r1",
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "action_id": "a1",
            "event_type": "undo_request",
            "actor_id": "u1",
            "target_id": "o1",
            "reason_code": "UNDO",
            "trace_id": "t1",
            "request_id": "r1",
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "action_id": "a2",
            "event_type": "execute",
            "undo_supported": True,
            "undo_window_sec": 10,
            "actor_id": "",
            "target_id": "",
            "reason_code": "",
            "trace_id": "",
            "request_id": "",
        },
    ]
    summary = module.summarize_undo_audit(rows, now=datetime(2026, 3, 3, 0, 30, tzinfo=timezone.utc))
    assert summary["execute_without_request_total"] == 1
    assert summary["undo_after_window_total"] == 1
    assert summary["missing_audit_fields_total"] >= 5


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "execute_without_request_total": 1,
            "undo_after_window_total": 1,
            "undo_success_ratio": 0.5,
            "audit_trail_incomplete_total": 1,
            "missing_audit_fields_total": 5,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_execute_without_request_total=0,
        max_undo_after_window_total=0,
        min_undo_success_ratio=0.8,
        max_audit_trail_incomplete_total=0,
        max_missing_audit_fields_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "execute_without_request_total": 0,
            "undo_after_window_total": 0,
            "undo_success_ratio": 1.0,
            "audit_trail_incomplete_total": 0,
            "missing_audit_fields_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_execute_without_request_total=0,
        max_undo_after_window_total=0,
        min_undo_success_ratio=0.8,
        max_audit_trail_incomplete_total=0,
        max_missing_audit_fields_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_undo_audit_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "execute_without_request_total": 0,
                "undo_after_window_total": 0,
                "undo_success_ratio": 1.0,
                "audit_trail_incomplete_total": 0,
                "missing_audit_fields_total": 0,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "execute_without_request_total": 1,
            "undo_after_window_total": 1,
            "undo_success_ratio": 0.6,
            "audit_trail_incomplete_total": 1,
            "missing_audit_fields_total": 5,
            "stale_minutes": 40.0,
        },
        max_execute_without_request_total_increase=0,
        max_undo_after_window_total_increase=0,
        max_undo_success_ratio_drop=0.05,
        max_audit_trail_incomplete_total_increase=0,
        max_missing_audit_fields_total_increase=0,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 6
