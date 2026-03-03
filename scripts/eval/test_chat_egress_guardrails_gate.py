import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_egress_guardrails_gate.py"
    spec = importlib.util.spec_from_file_location("chat_egress_guardrails_gate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_egress_detects_violations_and_unknown_destinations():
    module = _load_module()
    now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": "2026-03-03T11:58:00Z",
            "destination": "llm_provider",
            "status": "allowed",
            "sensitive_field_total": 1,
            "masked": True,
            "trace_id": "t1",
            "request_id": "r1",
        },
        {
            "timestamp": "2026-03-03T11:57:00Z",
            "destination": "rogue_api",
            "status": "allowed",
            "sensitive_field_total": 2,
            "masked": False,
            "trace_id": "",
            "request_id": "",
            "alert_sent": True,
        },
    ]

    summary = module.summarize_egress(rows, allow_destinations={"llm_provider"}, now=now)
    assert summary["window_size"] == 2
    assert summary["violation_total"] == 1
    assert summary["unknown_destination_total"] == 1
    assert summary["unmasked_sensitive_total"] == 1
    assert summary["missing_trace_total"] == 1
    assert summary["alert_coverage_ratio"] == 1.0


def test_evaluate_gate_detects_multiple_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "violation_total": 2,
            "unmasked_sensitive_total": 1,
            "unknown_destination_total": 1,
            "error_ratio": 0.2,
            "missing_trace_total": 1,
            "alert_coverage_ratio": 0.5,
            "stale_minutes": 10.0,
        },
        min_window=1,
        max_violation_total=0,
        max_unmasked_sensitive_total=0,
        max_unknown_destination_total=0,
        max_error_ratio=0.05,
        max_missing_trace_total=0,
        min_alert_coverage_ratio=1.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) >= 5
    assert any("egress violations exceeded" in item for item in failures)
    assert any("alert coverage below threshold" in item for item in failures)


def test_evaluate_gate_passes_when_signals_are_clean():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 3,
            "violation_total": 0,
            "unmasked_sensitive_total": 0,
            "unknown_destination_total": 0,
            "error_ratio": 0.0,
            "missing_trace_total": 0,
            "alert_coverage_ratio": 1.0,
            "stale_minutes": 5.0,
        },
        min_window=1,
        max_violation_total=0,
        max_unmasked_sensitive_total=0,
        max_unknown_destination_total=0,
        max_error_ratio=0.05,
        max_missing_trace_total=0,
        min_alert_coverage_ratio=1.0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_violation_unmasked_unknown_regression():
    module = _load_module()
    baseline = {
        "summary": {
            "violation_total": 0,
            "unmasked_sensitive_total": 0,
            "unknown_destination_total": 0,
            "error_ratio": 0.0,
            "alert_coverage_ratio": 1.0,
        }
    }
    current = {
        "violation_total": 5,
        "unmasked_sensitive_total": 3,
        "unknown_destination_total": 2,
        "error_ratio": 0.4,
        "alert_coverage_ratio": 0.2,
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_violation_total_increase=0,
        max_unmasked_sensitive_increase=0,
        max_unknown_destination_increase=0,
        max_error_ratio_increase=0.0,
        max_alert_coverage_ratio_drop=0.0,
    )
    assert any("violation regression" in item for item in failures)
    assert any("unmasked sensitive regression" in item for item in failures)
    assert any("unknown destination regression" in item for item in failures)
    assert any("error ratio regression" in item for item in failures)
    assert any("alert coverage regression" in item for item in failures)
