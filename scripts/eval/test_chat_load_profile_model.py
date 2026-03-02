import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_load_profile_model.py"
    spec = importlib.util.spec_from_file_location("chat_load_profile_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_load_profile_summarizes_scenarios_and_hourly_profile():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T01:00:00Z",
            "scenario": "normal",
            "intent": "ORDER_STATUS",
            "status": "ok",
            "latency_ms": 500,
            "queue_depth": 4,
            "tool_calls": 1,
            "tokens": 120,
        },
        {
            "timestamp": "2026-03-03T01:10:00Z",
            "scenario": "promotion",
            "intent": "BOOK_RECOMMEND",
            "status": "ok",
            "latency_ms": 900,
            "queue_depth": 8,
            "tool_calls": 0,
            "tokens": 200,
        },
        {
            "timestamp": "2026-03-03T01:20:00Z",
            "scenario": "incident",
            "intent": "REFUND_REQUEST",
            "status": "error",
            "latency_ms": 4500,
            "queue_depth": 55,
            "tool_calls": 2,
            "tokens": 150,
        },
    ]
    summary = module.build_load_profile(rows)
    assert summary["window_size"] == 3
    assert summary["profiles"]["NORMAL"]["request_total"] == 1
    assert summary["profiles"]["PROMOTION"]["request_total"] == 1
    assert summary["profiles"]["INCIDENT"]["error_ratio"] == 1.0
    assert summary["hourly_profile"]


def test_evaluate_gate_detects_normal_profile_regressions():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "profiles": {
                "NORMAL": {
                    "error_ratio": 0.2,
                    "p95_latency_ms": 5000,
                    "p95_queue_depth": 80,
                }
            },
        },
        min_window=1,
        max_normal_error_ratio=0.05,
        max_normal_p95_latency_ms=3000.0,
        max_normal_p95_queue_depth=50.0,
    )
    assert len(failures) == 3


def test_evaluate_gate_passes_when_normal_profile_is_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 20,
            "profiles": {
                "NORMAL": {
                    "error_ratio": 0.01,
                    "p95_latency_ms": 700,
                    "p95_queue_depth": 10,
                }
            },
        },
        min_window=1,
        max_normal_error_ratio=0.05,
        max_normal_p95_latency_ms=3000.0,
        max_normal_p95_queue_depth=50.0,
    )
    assert failures == []
