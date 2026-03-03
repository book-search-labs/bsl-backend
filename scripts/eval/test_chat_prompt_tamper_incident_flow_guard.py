import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_prompt_tamper_incident_flow_guard.py"
    spec = importlib.util.spec_from_file_location("chat_prompt_tamper_incident_flow_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_prompt_tamper_incident_flow_guard_tracks_quarantine_and_alerts():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "tamper_suspected": True,
            "alert_emitted": True,
            "incident_created": True,
            "triage_started": True,
            "quarantine_applied": True,
            "alert_latency_sec": 2.0,
            "reason_code": "PROMPT_TAMPER_CONTAINED",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "tamper_suspected": True,
            "alert_emitted": True,
            "incident_created": False,
            "triage_started": False,
            "quarantine_applied": False,
            "alert_latency_sec": 10.0,
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "tamper_suspected": True,
            "alert_emitted": False,
            "incident_created": False,
            "quarantine_applied": False,
            "reason_code": "",
        },
    ]

    summary = module.summarize_prompt_tamper_incident_flow_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["tamper_event_total"] == 3
    assert summary["alert_emitted_total"] == 2
    assert abs(summary["alert_coverage_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["incident_created_total"] == 1
    assert abs(summary["incident_coverage_ratio"] - (1.0 / 3.0)) < 1e-9
    assert summary["triage_started_total"] == 1
    assert summary["quarantine_applied_total"] == 1
    assert abs(summary["quarantine_coverage_ratio"] - (1.0 / 3.0)) < 1e-9
    assert summary["uncontained_tamper_total"] == 2
    assert summary["reason_code_missing_total"] == 2
    assert summary["alert_latency_p95_sec"] == 10.0
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_prompt_tamper_incident_flow_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "tamper_event_total": 1,
            "alert_coverage_ratio": 0.2,
            "incident_coverage_ratio": 0.1,
            "quarantine_coverage_ratio": 0.1,
            "alert_latency_p95_sec": 120.0,
            "uncontained_tamper_total": 2,
            "reason_code_missing_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_tamper_event_total=2,
        min_alert_coverage_ratio=1.0,
        min_incident_coverage_ratio=1.0,
        min_quarantine_coverage_ratio=1.0,
        max_alert_latency_p95_sec=30.0,
        max_uncontained_tamper_total=0,
        max_reason_code_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "tamper_event_total": 0,
            "alert_coverage_ratio": 1.0,
            "incident_coverage_ratio": 1.0,
            "quarantine_coverage_ratio": 1.0,
            "alert_latency_p95_sec": 0.0,
            "uncontained_tamper_total": 0,
            "reason_code_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_tamper_event_total=0,
        min_alert_coverage_ratio=0.0,
        min_incident_coverage_ratio=0.0,
        min_quarantine_coverage_ratio=0.0,
        max_alert_latency_p95_sec=1000000.0,
        max_uncontained_tamper_total=1000000,
        max_reason_code_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
