import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_config_distribution_rollout.py"
    spec = importlib.util.spec_from_file_location("chat_config_distribution_rollout", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_distribution_tracks_stage_and_drift():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "bundle_id": "b1",
            "stage": "1",
            "result": "success",
            "signature_valid": True,
            "desired_version": "v2",
            "applied_version": "v2",
            "service": "query",
        },
        {
            "timestamp": "2026-03-03T00:05:00Z",
            "bundle_id": "b1",
            "stage": "10",
            "result": "success",
            "signature_valid": True,
            "desired_version": "v2",
            "applied_version": "v1",
            "service": "query",
        },
    ]
    summary = module.summarize_distribution(
        rows,
        required_stages=[1, 10, 50, 100],
        now=datetime(2026, 3, 3, 0, 10, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 2
    assert summary["drift_total"] == 1
    assert summary["success_ratio"] == 1.0
    assert len(summary["missing_stage_bundles"]) == 1


def test_evaluate_gate_detects_distribution_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "success_ratio": 0.6,
            "drift_ratio": 0.3,
            "signature_invalid_total": 2,
            "stage_regression_total": 1,
            "stale_minutes": 120.0,
            "missing_stage_bundles": [{"bundle_id": "b1", "missing_stages": [50, 100]}],
        },
        min_window=1,
        min_success_ratio=0.95,
        max_drift_ratio=0.02,
        max_signature_invalid_total=0,
        max_stage_regression_total=0,
        max_stale_minutes=60.0,
        require_stages=True,
    )
    assert len(failures) == 6


def test_evaluate_gate_passes_when_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 20,
            "success_ratio": 0.99,
            "drift_ratio": 0.0,
            "signature_invalid_total": 0,
            "stage_regression_total": 0,
            "stale_minutes": 5.0,
            "missing_stage_bundles": [],
        },
        min_window=1,
        min_success_ratio=0.95,
        max_drift_ratio=0.02,
        max_signature_invalid_total=0,
        max_stage_regression_total=0,
        max_stale_minutes=60.0,
        require_stages=True,
    )
    assert failures == []


def test_evaluate_gate_allows_empty_window_when_min_window_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "success_ratio": 0.0,
            "drift_ratio": 0.0,
            "signature_invalid_total": 0,
            "stage_regression_total": 0,
            "stale_minutes": 0.0,
            "missing_stage_bundles": [],
        },
        min_window=0,
        min_success_ratio=0.95,
        max_drift_ratio=0.02,
        max_signature_invalid_total=0,
        max_stage_regression_total=0,
        max_stale_minutes=60.0,
        require_stages=False,
    )
    assert failures == []


def test_compare_with_baseline_detects_rollout_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "success_ratio": 0.99,
                "drift_ratio": 0.01,
                "signature_invalid_total": 0,
                "stage_regression_total": 0,
                "missing_stage_bundles": [],
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "success_ratio": 0.92,
            "drift_ratio": 0.06,
            "signature_invalid_total": 2,
            "stage_regression_total": 1,
            "missing_stage_bundles": [{"bundle_id": "b1", "missing_stages": [50]}],
        },
        max_success_ratio_drop=0.02,
        max_drift_ratio_increase=0.02,
        max_signature_invalid_total_increase=0,
        max_stage_regression_total_increase=0,
        max_missing_stage_bundle_increase=0,
    )
    assert len(failures) == 5
