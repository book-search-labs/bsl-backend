import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_capacity_forecast.py"
    spec = importlib.util.spec_from_file_location("chat_capacity_forecast", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_compute_forecast_derives_requests_tokens_and_resources():
    module = _load_module()
    summary = module.compute_forecast(
        load_summary={
            "window_size": 1680,
            "profiles": {
                "NORMAL": {
                    "avg_tokens": 120.0,
                    "tool_calls_per_request": 0.5,
                }
            },
            "hourly_profile": [
                {"hour_utc": 1, "request_total": 20},
                {"hour_utc": 2, "request_total": 35},
            ],
        },
        baseline_window_hours=168.0,
        weekly_growth_factor=1.1,
        monthly_growth_factor=1.3,
        promo_surge_factor=1.5,
        cpu_rps_per_core=3.0,
        gpu_tokens_per_sec=800.0,
        base_memory_gb=2.0,
        memory_per_core_gb=0.5,
        cost_per_1k_tokens=0.002,
    )

    assert summary["baseline"]["window_size"] == 1680
    assert summary["forecast"]["week_requests"] > 0
    assert summary["forecast"]["month_tokens"] > 0
    assert summary["resources"]["cpu_cores_required"] >= 1


def test_evaluate_gate_detects_resource_and_budget_exceedance():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "baseline": {"window_size": 10},
            "forecast": {"peak_rps": 80.0, "monthly_cost_usd": 20000.0},
            "resources": {"cpu_cores_required": 90, "gpu_required": 12},
        },
        min_window=1,
        max_peak_rps=50.0,
        max_monthly_cost_usd=15000.0,
        max_cpu_cores=64,
        max_gpu_required=8,
    )
    assert len(failures) == 4


def test_evaluate_gate_passes_when_forecast_within_thresholds():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "baseline": {"window_size": 100},
            "forecast": {"peak_rps": 10.0, "monthly_cost_usd": 5000.0},
            "resources": {"cpu_cores_required": 8, "gpu_required": 2},
        },
        min_window=1,
        max_peak_rps=50.0,
        max_monthly_cost_usd=15000.0,
        max_cpu_cores=64,
        max_gpu_required=8,
    )
    assert failures == []


def test_compare_with_baseline_detects_peak_cost_cpu_gpu_regression():
    module = _load_module()
    baseline = {
        "summary": {
            "forecast": {"peak_rps": 10.0, "monthly_cost_usd": 5000.0},
            "resources": {"cpu_cores_required": 8, "gpu_required": 2},
        }
    }
    current = {
        "forecast": {"peak_rps": 40.0, "monthly_cost_usd": 15000.0},
        "resources": {"cpu_cores_required": 32, "gpu_required": 6},
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_peak_rps_increase=0.0,
        max_monthly_cost_usd_increase=0.0,
        max_cpu_cores_increase=0,
        max_gpu_required_increase=0,
    )
    assert any("peak_rps regression" in item for item in failures)
    assert any("monthly cost regression" in item for item in failures)
    assert any("cpu cores regression" in item for item in failures)
    assert any("gpu requirement regression" in item for item in failures)
