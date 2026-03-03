import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_session_resilience_drill_report.py"
    spec = importlib.util.spec_from_file_location("chat_session_resilience_drill_report", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_drills_tracks_rto_loss_and_missing_required():
    module = _load_module()
    now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    rows = [
        {
            "started_at": "2026-03-02T10:00:00Z",
            "scenario": "connection_storm",
            "completed": True,
            "passed": True,
            "rto_sec": 400,
            "sent_total": 1000,
            "message_loss_total": 1,
        },
        {
            "started_at": "2026-03-02T11:00:00Z",
            "scenario": "broker_delay",
            "completed": False,
            "passed": False,
            "sent_total": 500,
            "message_loss_total": 0,
        },
    ]

    summary = module.summarize_drills(rows, required_scenarios={"CONNECTION_STORM", "PARTIAL_REGION_FAIL", "BROKER_DELAY"}, now=now)
    assert summary["window_size"] == 2
    assert summary["open_drill_total"] == 1
    assert summary["avg_rto_sec"] == 400
    assert "PARTIAL_REGION_FAIL" in summary["missing_required_scenarios"]


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 2,
            "open_drill_total": 1,
            "avg_rto_sec": 1200,
            "message_loss_ratio": 0.01,
            "missing_required_scenarios": ["BROKER_DELAY"],
            "stale_days": 60,
        },
        min_window=1,
        max_open_drill_total=0,
        max_avg_rto_sec=900,
        max_message_loss_ratio=0.001,
        require_scenarios=True,
        max_stale_days=35,
    )
    assert len(failures) == 5


def test_evaluate_gate_passes_when_healthy():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "open_drill_total": 0,
            "avg_rto_sec": 300,
            "message_loss_ratio": 0.0,
            "missing_required_scenarios": [],
            "stale_days": 5,
        },
        min_window=1,
        max_open_drill_total=0,
        max_avg_rto_sec=900,
        max_message_loss_ratio=0.001,
        require_scenarios=True,
        max_stale_days=35,
    )
    assert failures == []


def test_compare_with_baseline_detects_open_rto_loss_and_coverage_regression():
    module = _load_module()
    baseline = {
        "summary": {
            "open_drill_total": 0,
            "avg_rto_sec": 300.0,
            "message_loss_ratio": 0.0,
            "missing_required_scenarios": [],
        }
    }
    current = {
        "open_drill_total": 2,
        "avg_rto_sec": 1800.0,
        "message_loss_ratio": 0.02,
        "missing_required_scenarios": ["BROKER_DELAY", "PARTIAL_REGION_FAIL"],
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_open_drill_total_increase=0,
        max_avg_rto_sec_increase=0.0,
        max_message_loss_ratio_increase=0.0,
        max_missing_required_scenario_increase=0,
    )
    assert any("open drill regression" in item for item in failures)
    assert any("average rto regression" in item for item in failures)
    assert any("message loss regression" in item for item in failures)
    assert any("required scenario coverage regression" in item for item in failures)
