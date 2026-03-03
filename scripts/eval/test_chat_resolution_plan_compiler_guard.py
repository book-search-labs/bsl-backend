import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_resolution_plan_compiler_guard.py"
    spec = importlib.util.spec_from_file_location("chat_resolution_plan_compiler_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_resolution_plan_compiler_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "reason_code": "REFUND_REQUEST",
            "required_checks": ["order_id", "received", "request_date"],
            "provided_checks": ["order_id", "received", "request_date"],
            "plan_created": True,
            "plan_deterministic": True,
            "plan_executable": True,
            "insufficient_evidence_count": 0,
            "followup_question_asked": False,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "reason_code": "SHIPPING_CHANGE",
            "required_checks": ["order_id", "shipping_option"],
            "provided_checks": ["shipping_option"],
            "plan_created": True,
            "plan_deterministic": True,
            "plan_executable": True,
            "insufficient_evidence_count": 0,
            "followup_question_asked": False,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "reason_code": "REFUND_REQUEST",
            "required_checks": ["order_id", "received", "request_date"],
            "provided_checks": ["order_id", "received", "request_date"],
            "plan_created": True,
            "plan_deterministic": False,
            "plan_executable": False,
            "insufficient_evidence_items": ["carrier_status"],
            "followup_question_asked": True,
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "reason_code": "",
            "plan_created": False,
        },
    ]
    summary = module.summarize_resolution_plan_compiler_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["plan_created_total"] == 3
    assert abs(summary["plan_creation_rate"] - 0.75) < 1e-9
    assert summary["deterministic_plan_total"] == 2
    assert abs(summary["deterministic_plan_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["missing_required_check_total"] == 1
    assert summary["missing_required_block_violation_total"] == 1
    assert summary["insufficient_evidence_total"] == 1
    assert summary["insufficient_evidence_reroute_missing_total"] == 0
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_resolution_plan_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "plan_creation_rate": 0.1,
            "deterministic_plan_ratio": 0.2,
            "missing_required_block_violation_total": 2,
            "insufficient_evidence_reroute_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_plan_creation_rate=0.7,
        min_deterministic_plan_ratio=0.9,
        max_missing_required_block_violation_total=0,
        max_insufficient_evidence_reroute_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "plan_creation_rate": 0.0,
            "deterministic_plan_ratio": 1.0,
            "missing_required_block_violation_total": 0,
            "insufficient_evidence_reroute_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_plan_creation_rate=0.0,
        min_deterministic_plan_ratio=0.0,
        max_missing_required_block_violation_total=1000000,
        max_insufficient_evidence_reroute_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
