import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_override_audit_guard.py"
    spec = importlib.util.spec_from_file_location("chat_tool_override_audit_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_tool_override_audit_guard_tracks_audit_and_conflicts():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "tool": "order_lookup",
            "override_type": "FORCE_INCLUDE",
            "override_applied": True,
            "actor_user_id": "op-1",
            "reason": "degrade incident",
            "trace_id": "tr-1",
            "request_id": "rq-1",
            "expires_at": "2026-03-04T01:00:00Z",
            "authz_allowed": True,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "tool": "refund_tool",
            "override_type": "FORCE_EXCLUDE",
            "override_applied": True,
            "actor_user_id": "op-2",
            "reason": "timeout spike",
            "trace_id": "tr-2",
            "request_id": "rq-2",
            "ttl_minutes": 30,
            "authz_allowed": True,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "tool": "payment_tool",
            "override_type": "FORCE_EXCLUDE",
            "override_applied": True,
            "actor_user_id": "",
            "reason": "",
            "trace_id": "",
            "request_id": "",
            "authz_allowed": True,
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "tool": "order_lookup",
            "override_type": "FORCE_EXCLUDE",
            "override_applied": True,
            "actor_user_id": "op-3",
            "reason": "policy enforcement",
            "trace_id": "tr-3",
            "request_id": "rq-3",
            "expires_at": "2026-03-04T00:40:00Z",
            "authz_allowed": True,
        },
        {
            "timestamp": "2026-03-04T00:00:40Z",
            "tool": "shipping_tool",
            "override_type": "FORCE_INCLUDE",
            "override_applied": True,
            "actor_user_id": "op-4",
            "reason": "manual reroute",
            "trace_id": "tr-4",
            "request_id": "rq-4",
            "expires_at": "2026-03-04T00:50:00Z",
            "authz_allowed": False,
        },
    ]
    summary = module.summarize_tool_override_audit_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["override_event_total"] == 5
    assert summary["override_applied_total"] == 5
    assert summary["force_include_total"] == 2
    assert summary["force_exclude_total"] == 3
    assert summary["missing_actor_total"] == 1
    assert summary["missing_reason_total"] == 1
    assert summary["missing_audit_context_total"] == 1
    assert summary["missing_expiry_total"] == 1
    assert summary["unauthorized_override_total"] == 1
    assert summary["conflicting_override_total"] == 1
    assert abs(summary["stale_minutes"] - (20.0 / 60.0)) < 1e-9


def test_evaluate_gate_detects_tool_override_audit_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 3,
            "override_event_total": 1,
            "missing_actor_total": 2,
            "missing_reason_total": 2,
            "missing_audit_context_total": 2,
            "missing_expiry_total": 2,
            "unauthorized_override_total": 1,
            "conflicting_override_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_override_event_total=2,
        max_missing_actor_total=0,
        max_missing_reason_total=0,
        max_missing_audit_context_total=0,
        max_missing_expiry_total=0,
        max_unauthorized_override_total=0,
        max_conflicting_override_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "override_event_total": 0,
            "missing_actor_total": 0,
            "missing_reason_total": 0,
            "missing_audit_context_total": 0,
            "missing_expiry_total": 0,
            "unauthorized_override_total": 0,
            "conflicting_override_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_override_event_total=0,
        max_missing_actor_total=1000000,
        max_missing_reason_total=1000000,
        max_missing_audit_context_total=1000000,
        max_missing_expiry_total=1000000,
        max_unauthorized_override_total=1000000,
        max_conflicting_override_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
