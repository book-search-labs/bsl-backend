import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_creation_integration.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_creation_integration", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_ticket_creation_flags_payload_and_response_missing():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "ticket_create_requested",
            "summary": "환불 문의",
            "order_id": "",
            "error_code": "",
        },
        {
            "timestamp": "2026-03-03T00:00:01Z",
            "event_type": "ticket_created",
            "ticket_no": "",
            "eta_minutes": "",
        },
    ]
    summary = module.summarize_ticket_creation(rows, now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc))
    assert summary["create_requested_total"] == 1
    assert summary["create_success_total"] == 1
    assert summary["payload_missing_fields_total"] == 2
    assert summary["missing_ticket_no_total"] == 1
    assert summary["missing_eta_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "create_success_ratio": 0.5,
            "payload_missing_fields_total": 3,
            "missing_ticket_no_total": 1,
            "missing_eta_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        min_create_success_ratio=0.95,
        max_payload_missing_fields_total=0,
        max_missing_ticket_no_total=0,
        max_missing_eta_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "create_success_ratio": 1.0,
            "payload_missing_fields_total": 0,
            "missing_ticket_no_total": 0,
            "missing_eta_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_create_success_ratio=0.95,
        max_payload_missing_fields_total=0,
        max_missing_ticket_no_total=0,
        max_missing_eta_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []
