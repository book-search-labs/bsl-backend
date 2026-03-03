import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_config_safety_guard.py"
    spec = importlib.util.spec_from_file_location("chat_config_safety_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_safety_guard_tracks_mitigation():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "anomaly_detected": True,
            "auto_stop": True,
            "detection_lag_sec": 30,
            "killswitch_activated": False,
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "slo_breach": True,
            "auto_rollback": False,
            "kill_switch": False,
            "detection_lag_sec": 90,
        },
    ]
    summary = module.summarize_safety_guard(
        rows,
        forbidden_killswitch_scopes={"GLOBAL_ALL_SERVICES"},
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )
    assert summary["window_size"] == 2
    assert summary["anomaly_total"] == 2
    assert summary["unhandled_anomaly_total"] == 1
    assert summary["mitigation_ratio"] == 0.5


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "unhandled_anomaly_total": 2,
            "mitigation_ratio": 0.6,
            "detection_lag_p95_sec": 300.0,
            "forbidden_killswitch_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_unhandled_anomaly_total=0,
        min_mitigation_ratio=0.95,
        max_detection_lag_p95_sec=120.0,
        max_forbidden_killswitch_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_passes_when_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "unhandled_anomaly_total": 0,
            "mitigation_ratio": 1.0,
            "detection_lag_p95_sec": 30.0,
            "forbidden_killswitch_total": 0,
            "stale_minutes": 5.0,
        },
        min_window=1,
        max_unhandled_anomaly_total=0,
        min_mitigation_ratio=0.95,
        max_detection_lag_p95_sec=120.0,
        max_forbidden_killswitch_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "unhandled_anomaly_total": 0,
            "mitigation_ratio": 0.0,
            "detection_lag_p95_sec": 0.0,
            "forbidden_killswitch_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_unhandled_anomaly_total=0,
        min_mitigation_ratio=0.95,
        max_detection_lag_p95_sec=120.0,
        max_forbidden_killswitch_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_safety_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "unhandled_anomaly_total": 0,
                "mitigation_ratio": 0.98,
                "detection_lag_p95_sec": 40.0,
                "forbidden_killswitch_total": 0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "unhandled_anomaly_total": 2,
            "mitigation_ratio": 0.80,
            "detection_lag_p95_sec": 110.0,
            "forbidden_killswitch_total": 1,
        },
        max_unhandled_anomaly_total_increase=0,
        max_mitigation_ratio_drop=0.05,
        max_detection_lag_p95_sec_increase=30.0,
        max_forbidden_killswitch_total_increase=0,
    )
    assert len(failures) == 4
