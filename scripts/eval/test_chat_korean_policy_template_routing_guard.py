import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_korean_policy_template_routing_guard.py"
    spec = importlib.util.spec_from_file_location("chat_korean_policy_template_routing_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_korean_policy_template_routing_guard_tracks_quality():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "locale": "ko-KR",
            "reason_code": "POLICY:REFUND",
            "template_required": True,
            "template_key": "ko_refund_policy_v1",
            "expected_template_key": "ko_refund_policy_v1",
            "required_slots": ["order_id", "amount"],
            "rendered_slots": {"order_id": "O1", "amount": "1000"},
            "template_language": "ko",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "locale": "ko-KR",
            "reason_code": "POLICY:SHIPPING",
            "template_required": True,
            "template_key": "",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "locale": "ko-KR",
            "reason_code": "POLICY:RETURN",
            "template_required": True,
            "template_key": "ko_shipping_policy_v1",
            "expected_template_key": "ko_return_policy_v1",
            "required_slots": ["order_id", "status"],
            "rendered_slots": {"order_id": "O2"},
            "template_language": "en",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "locale": "en-US",
            "reason_code": "",
            "template_required": False,
            "template_key": "",
        },
    ]
    summary = module.summarize_korean_policy_template_routing_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["korean_event_total"] == 3
    assert summary["template_required_total"] == 3
    assert summary["routed_total"] == 2
    assert abs(summary["routing_coverage_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["missing_template_total"] == 1
    assert summary["wrong_template_total"] == 1
    assert summary["missing_slot_injection_total"] == 1
    assert summary["non_korean_template_total"] == 1
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_korean_policy_template_routing_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "routing_coverage_ratio": 0.2,
            "missing_template_total": 2,
            "wrong_template_total": 1,
            "missing_slot_injection_total": 1,
            "non_korean_template_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_routing_coverage_ratio=0.95,
        max_missing_template_total=0,
        max_wrong_template_total=0,
        max_missing_slot_injection_total=0,
        max_non_korean_template_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "routing_coverage_ratio": 1.0,
            "missing_template_total": 0,
            "wrong_template_total": 0,
            "missing_slot_injection_total": 0,
            "non_korean_template_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_routing_coverage_ratio=0.0,
        max_missing_template_total=1000000,
        max_wrong_template_total=1000000,
        max_missing_slot_injection_total=1000000,
        max_non_korean_template_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
