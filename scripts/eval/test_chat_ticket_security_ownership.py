import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_ticket_security_ownership.py"
    spec = importlib.util.spec_from_file_location("chat_ticket_security_ownership", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_security_ownership_flags_violations():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "ticket_status_lookup",
            "result": "ok",
            "owner_match": False,
            "response_text": "문의자 이메일 foo@example.com",
            "attachment_url": "https://files.example.com/private/123",
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "event_type": "ticket_status_lookup",
            "result": "ok",
            "owner_match": None,
            "response_text": "masked",
            "attachment_url": "",
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "event_type": "ticket_status_lookup",
            "result": "forbidden",
        },
    ]
    summary = module.summarize_security_ownership(rows, now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc))
    assert summary["lookup_total"] == 3
    assert summary["authz_denied_total"] == 1
    assert summary["ownership_violation_total"] == 1
    assert summary["missing_owner_check_total"] == 1
    assert summary["pii_unmasked_total"] == 1
    assert summary["attachment_unmasked_link_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "ownership_violation_total": 1,
            "missing_owner_check_total": 1,
            "pii_unmasked_total": 1,
            "attachment_unmasked_link_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_ownership_violation_total=0,
        max_missing_owner_check_total=0,
        max_pii_unmasked_total=0,
        max_attachment_unmasked_link_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "ownership_violation_total": 0,
            "missing_owner_check_total": 0,
            "pii_unmasked_total": 0,
            "attachment_unmasked_link_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_ownership_violation_total=0,
        max_missing_owner_check_total=0,
        max_pii_unmasked_total=0,
        max_attachment_unmasked_link_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []
