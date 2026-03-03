import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_autoscaling_calibration.py"
    spec = importlib.util.spec_from_file_location("chat_autoscaling_calibration", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_calibration_computes_under_over_and_target_factor():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T01:00:00Z",
            "actual_rps": 10.0,
            "allocated_rps": 8.0,
            "predicted_rps": 9.0,
            "release_event": True,
            "canary_pass": True,
            "scale_action": "up",
        },
        {
            "timestamp": "2026-03-03T01:05:00Z",
            "actual_rps": 5.0,
            "allocated_rps": 8.0,
            "predicted_rps": 6.0,
            "release_event": True,
            "canary_pass": False,
            "scale_action": "down",
        },
    ]
    summary = module.summarize_calibration(
        rows,
        forecast_peak_rps=7.0,
        under_tolerance_ratio=0.05,
        over_tolerance_ratio=0.10,
        base_prescale_factor=1.2,
        calibration_step=0.05,
    )
    assert summary["window_size"] == 2
    assert summary["under_total"] >= 1
    assert summary["over_total"] >= 1
    assert summary["canary_failure_total"] == 1
    assert summary["target_prescale_factor"] >= 1.0


def test_evaluate_gate_detects_under_ratio_and_canary_failure():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "under_ratio": 0.3,
            "over_ratio": 0.1,
            "prediction_mape": 0.5,
            "canary_failure_total": 2,
            "release_event_total": 2,
        },
        min_window=1,
        max_under_ratio=0.1,
        max_over_ratio=0.35,
        max_prediction_mape=0.4,
        max_canary_failure_total=0,
        require_release_canary=True,
    )
    assert len(failures) == 3


def test_evaluate_gate_passes_when_within_thresholds():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 20,
            "under_ratio": 0.05,
            "over_ratio": 0.10,
            "prediction_mape": 0.20,
            "canary_failure_total": 0,
            "release_event_total": 5,
        },
        min_window=1,
        max_under_ratio=0.1,
        max_over_ratio=0.35,
        max_prediction_mape=0.4,
        max_canary_failure_total=0,
        require_release_canary=True,
    )
    assert failures == []


def test_compare_with_baseline_detects_under_over_mape_canary_regression():
    module = _load_module()
    baseline = {
        "summary": {
            "under_ratio": 0.05,
            "over_ratio": 0.08,
            "prediction_mape": 0.15,
            "canary_failure_total": 0,
        }
    }
    current = {
        "under_ratio": 0.30,
        "over_ratio": 0.40,
        "prediction_mape": 0.55,
        "canary_failure_total": 3,
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_under_ratio_increase=0.0,
        max_over_ratio_increase=0.0,
        max_prediction_mape_increase=0.0,
        max_canary_failure_total_increase=0,
    )
    assert any("under ratio regression" in item for item in failures)
    assert any("over ratio regression" in item for item in failures)
    assert any("prediction mape regression" in item for item in failures)
    assert any("canary failure count regression" in item for item in failures)
