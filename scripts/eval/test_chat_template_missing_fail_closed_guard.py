import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_template_missing_fail_closed_guard.py"
    spec = importlib.util.spec_from_file_location("chat_template_missing_fail_closed_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_template_missing_fail_closed_guard_tracks_quality():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "template_required": True,
            "template_key": "ko_refund_policy_v1",
            "status": "ok",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "template_required": True,
            "template_missing": True,
            "status": "safe_fallback",
            "next_action": "OPEN_SUPPORT_TICKET",
            "reason_code": "TEMPLATE_MISSING",
            "template_rendered": False,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "template_required": True,
            "template_missing": True,
            "fail_closed_enforced": False,
            "template_rendered": True,
            "reason_code": "POLICY_UNCERTAIN",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "template_required": False,
            "status": "ok",
        },
    ]
    summary = module.summarize_template_missing_fail_closed_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["template_required_total"] == 3
    assert summary["template_missing_total"] == 2
    assert summary["fail_closed_enforced_total"] == 1
    assert summary["fail_open_violation_total"] == 1
    assert summary["unsafe_rendered_when_missing_total"] == 1
    assert summary["template_missing_reason_missing_total"] == 1
    assert abs(summary["fail_closed_enforcement_ratio"] - 0.5) < 1e-9
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_template_missing_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "fail_closed_enforcement_ratio": 0.4,
            "fail_open_violation_total": 2,
            "unsafe_rendered_when_missing_total": 1,
            "template_missing_reason_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_fail_closed_enforcement_ratio=0.95,
        max_fail_open_violation_total=0,
        max_unsafe_rendered_when_missing_total=0,
        max_template_missing_reason_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "fail_closed_enforcement_ratio": 1.0,
            "fail_open_violation_total": 0,
            "unsafe_rendered_when_missing_total": 0,
            "template_missing_reason_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_fail_closed_enforcement_ratio=0.0,
        max_fail_open_violation_total=1000000,
        max_unsafe_rendered_when_missing_total=1000000,
        max_template_missing_reason_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
