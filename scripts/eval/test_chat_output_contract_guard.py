import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_output_contract_guard.py"
    spec = importlib.util.spec_from_file_location("chat_output_contract_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_output_contract_guard_tracks_contract_violations_and_formats():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "contract_checked": True,
            "guard_result": "PASS",
            "amount": "12000",
            "response_date": "2026-03-03",
            "response_status": "COMPLETED",
        },
        {
            "timestamp": "2026-03-03T00:00:10Z",
            "contract_checked": True,
            "guard_result": "FAIL",
            "forbidden_phrase_detected": True,
            "forbidden_action_detected": True,
            "required_fields_missing": ["order_id"],
            "response_amount": "12,000.999",
            "response_date": "03/03/2026",
            "response_status": "done",
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "contract_checked": False,
            "required_fields_missing": 2,
        },
    ]

    summary = module.summarize_output_contract_guard(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["output_total"] == 3
    assert summary["guard_checked_total"] == 2
    assert summary["guard_bypass_total"] == 1
    assert summary["contract_pass_total"] == 1
    assert summary["contract_fail_total"] == 1
    assert summary["guard_coverage_ratio"] == (2.0 / 3.0)
    assert summary["contract_pass_ratio"] == 0.5
    assert summary["forbidden_phrase_total"] == 1
    assert summary["forbidden_action_total"] == 1
    assert summary["required_field_missing_total"] == 3
    assert summary["invalid_amount_format_total"] == 1
    assert summary["invalid_date_format_total"] == 1
    assert summary["invalid_status_format_total"] == 1
    assert abs(summary["stale_minutes"] - (2.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_output_contract_guard_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "output_total": 2,
            "guard_coverage_ratio": 0.4,
            "contract_pass_ratio": 0.5,
            "guard_bypass_total": 2,
            "forbidden_phrase_total": 1,
            "forbidden_action_total": 1,
            "required_field_missing_total": 3,
            "invalid_amount_format_total": 2,
            "invalid_date_format_total": 1,
            "invalid_status_format_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_output_total=3,
        min_guard_coverage_ratio=0.95,
        min_contract_pass_ratio=0.98,
        max_guard_bypass_total=0,
        max_forbidden_phrase_total=0,
        max_forbidden_action_total=0,
        max_required_field_missing_total=0,
        max_invalid_amount_format_total=0,
        max_invalid_date_format_total=0,
        max_invalid_status_format_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 12


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "output_total": 0,
            "guard_coverage_ratio": 1.0,
            "contract_pass_ratio": 1.0,
            "guard_bypass_total": 0,
            "forbidden_phrase_total": 0,
            "forbidden_action_total": 0,
            "required_field_missing_total": 0,
            "invalid_amount_format_total": 0,
            "invalid_date_format_total": 0,
            "invalid_status_format_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_output_total=0,
        min_guard_coverage_ratio=0.0,
        min_contract_pass_ratio=0.0,
        max_guard_bypass_total=1000000,
        max_forbidden_phrase_total=1000000,
        max_forbidden_action_total=1000000,
        max_required_field_missing_total=1000000,
        max_invalid_amount_format_total=1000000,
        max_invalid_date_format_total=1000000,
        max_invalid_status_format_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
