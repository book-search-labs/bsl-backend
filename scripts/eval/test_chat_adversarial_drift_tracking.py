import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_adversarial_drift_tracking.py"
    spec = importlib.util.spec_from_file_location("chat_adversarial_drift_tracking", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_drift_tracking_counts_versions_refresh_and_linkage():
    module = _load_module()
    dataset_rows = [
        {"case_id": "c1", "timestamp": "2026-03-01T00:00:00Z", "dataset_version": "v3"},
        {"case_id": "c2", "timestamp": "2026-02-01T00:00:00Z", "dataset_version": "v2"},
        {"case_id": "c3", "timestamp": "2025-12-15T00:00:00Z", "dataset_version": "v1"},
    ]
    incident_rows = [
        {"incident_id": "i1", "timestamp": "2026-03-02T00:00:00Z", "linked_case_id": "c1"},
        {"incident_id": "i2", "timestamp": "2026-03-02T01:00:00Z", "linked_case_id": ""},
    ]
    summary = module.summarize_drift_tracking(
        dataset_rows,
        incident_rows,
        window_days=90,
        now=datetime(2026, 3, 3, 0, 0, tzinfo=timezone.utc),
    )

    assert summary["dataset_case_total"] == 3
    assert summary["dataset_version_total"] == 3
    assert summary["incident_total"] == 2
    assert summary["incident_linked_total"] == 1
    assert summary["incident_unlinked_total"] == 1
    assert abs(summary["incident_link_ratio"] - 0.5) < 1e-9
    assert summary["missing_monthly_refresh_total"] == 1
    assert summary["refresh_age_days"] <= 2.1


def test_evaluate_gate_detects_drift_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "dataset_case_total": 10,
            "dataset_version_total": 1,
            "refresh_age_days": 40.0,
            "missing_monthly_refresh_total": 3,
            "incident_total": 2,
            "incident_link_ratio": 0.1,
            "incident_unlinked_total": 2,
            "stale_minutes": 120.0,
        },
        min_dataset_case_total=20,
        min_dataset_version_total=2,
        max_refresh_age_days=30.0,
        max_missing_monthly_refresh_total=0,
        min_incident_total=3,
        min_incident_link_ratio=0.7,
        max_unlinked_incident_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_thresholds_open():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "dataset_case_total": 0,
            "dataset_version_total": 0,
            "refresh_age_days": 0.0,
            "missing_monthly_refresh_total": 0,
            "incident_total": 0,
            "incident_link_ratio": 1.0,
            "incident_unlinked_total": 0,
            "stale_minutes": 0.0,
        },
        min_dataset_case_total=0,
        min_dataset_version_total=0,
        max_refresh_age_days=999999.0,
        max_missing_monthly_refresh_total=1000000,
        min_incident_total=0,
        min_incident_link_ratio=0.0,
        max_unlinked_incident_total=1000000,
        max_stale_minutes=999999.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_drift_tracking_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "dataset_case_total": 500,
                "dataset_version_total": 8,
                "refresh_age_days": 3.0,
                "missing_monthly_refresh_total": 0,
                "incident_total": 40,
                "incident_link_ratio": 0.90,
                "incident_unlinked_total": 2,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "dataset_case_total": 300,
            "dataset_version_total": 5,
            "refresh_age_days": 20.0,
            "missing_monthly_refresh_total": 3,
            "incident_total": 20,
            "incident_link_ratio": 0.60,
            "incident_unlinked_total": 8,
            "stale_minutes": 50.0,
        },
        max_dataset_case_total_drop=10,
        max_dataset_version_total_drop=1,
        max_refresh_age_days_increase=7.0,
        max_missing_monthly_refresh_total_increase=1,
        max_incident_total_drop=5,
        max_incident_link_ratio_drop=0.05,
        max_unlinked_incident_total_increase=2,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 8
