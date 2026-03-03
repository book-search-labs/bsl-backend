import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_config_ops_runbook_integration.py"
    spec = importlib.util.spec_from_file_location("chat_config_ops_runbook_integration", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_ops_integration_counts_missing_payload_fields():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "incident_type": "SLO_BREACH",
            "alert_sent": True,
            "runbook_link": "https://runbook/1",
            "recommended_action": "rollback",
            "bundle_version": "v2",
            "impacted_services": ["query-service"],
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "incident_type": "COST_SPIKE",
            "alert_sent": True,
            "runbook_link": "",
            "recommended_action": "",
            "bundle_version": "",
            "impacted_services": [],
        },
    ]
    summary = module.summarize_ops_integration(
        rows,
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 2
    assert summary["payload_complete_total"] == 1
    assert summary["missing_runbook_total"] == 1
    assert summary["missing_recommended_action_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "payload_complete_ratio": 0.5,
            "missing_runbook_total": 2,
            "missing_recommended_action_total": 1,
            "missing_bundle_version_total": 1,
            "missing_impacted_services_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        min_payload_complete_ratio=0.95,
        max_missing_runbook_total=0,
        max_missing_recommended_action_total=0,
        max_missing_bundle_version_total=0,
        max_missing_impacted_services_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_passes_healthy_summary():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "payload_complete_ratio": 1.0,
            "missing_runbook_total": 0,
            "missing_recommended_action_total": 0,
            "missing_bundle_version_total": 0,
            "missing_impacted_services_total": 0,
            "stale_minutes": 5.0,
        },
        min_window=1,
        min_payload_complete_ratio=0.95,
        max_missing_runbook_total=0,
        max_missing_recommended_action_total=0,
        max_missing_bundle_version_total=0,
        max_missing_impacted_services_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_evaluate_gate_allows_empty_window_when_min_window_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "payload_complete_ratio": 0.0,
            "missing_runbook_total": 0,
            "missing_recommended_action_total": 0,
            "missing_bundle_version_total": 0,
            "missing_impacted_services_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_payload_complete_ratio=0.95,
        max_missing_runbook_total=0,
        max_missing_recommended_action_total=0,
        max_missing_bundle_version_total=0,
        max_missing_impacted_services_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []
