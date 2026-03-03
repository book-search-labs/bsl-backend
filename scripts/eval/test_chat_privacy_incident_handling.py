import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_privacy_incident_handling.py"
    spec = importlib.util.spec_from_file_location("chat_privacy_incident_handling", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_incident_handling_tracks_alert_queue_and_resolution():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "severity": "HIGH",
            "alert_sent": True,
            "operator_queued": True,
            "ack_latency_minutes": 5,
            "status": "RESOLVED",
            "runbook_link": "https://internal/runbook",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "severity": "CRITICAL",
            "alert_sent": False,
            "operator_queued": False,
            "ack_latency_minutes": 30,
            "status": "OPEN",
            "runbook_link": "",
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "severity": "LOW",
            "alert_sent": True,
            "operator_queued": False,
            "ack_latency_minutes": 10,
            "status": "DONE",
            "runbook_link": "https://internal/runbook2",
        },
    ]
    summary = module.summarize_incident_handling(
        rows,
        now=datetime(2026, 3, 3, 0, 3, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["incident_total"] == 3
    assert summary["high_severity_total"] == 2
    assert summary["alert_sent_total"] == 2
    assert summary["alert_miss_total"] == 1
    assert summary["queued_total"] == 1
    assert summary["high_unqueued_total"] == 1
    assert summary["high_queue_coverage_ratio"] == 0.5
    assert summary["acked_total"] == 3
    assert summary["p95_ack_latency_minutes"] == 30
    assert summary["resolved_total"] == 2
    assert summary["resolved_ratio"] == (2.0 / 3.0)
    assert summary["missing_runbook_link_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_incident_handling_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "incident_total": 1,
            "high_queue_coverage_ratio": 0.2,
            "resolved_ratio": 0.3,
            "alert_miss_total": 2,
            "high_unqueued_total": 2,
            "p95_ack_latency_minutes": 45.0,
            "missing_runbook_link_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_incident_total=2,
        min_high_queue_coverage_ratio=0.9,
        min_resolved_ratio=0.8,
        max_alert_miss_total=0,
        max_high_unqueued_total=0,
        max_p95_ack_latency_minutes=15.0,
        max_missing_runbook_link_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "incident_total": 0,
            "high_queue_coverage_ratio": 1.0,
            "resolved_ratio": 1.0,
            "alert_miss_total": 0,
            "high_unqueued_total": 0,
            "p95_ack_latency_minutes": 0.0,
            "missing_runbook_link_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_incident_total=0,
        min_high_queue_coverage_ratio=0.0,
        min_resolved_ratio=0.0,
        max_alert_miss_total=1000000,
        max_high_unqueued_total=1000000,
        max_p95_ack_latency_minutes=1000000.0,
        max_missing_runbook_link_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
