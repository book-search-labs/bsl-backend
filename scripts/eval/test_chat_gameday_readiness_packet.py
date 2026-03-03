import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_gameday_readiness_packet.py"
    spec = importlib.util.spec_from_file_location("chat_gameday_readiness_packet", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_evaluate_packet_ready_when_all_signals_healthy():
    module = _load_module()
    decision = module.evaluate_packet(
        readiness_score=92.0,
        readiness_gate_pass=True,
        readiness_tier="READY",
        trend_week_avg=90.0,
        trend_gate_pass=True,
        dr_open_total=0,
        min_readiness_score=80.0,
        min_week_avg=80.0,
    )
    assert decision["status"] == "READY"
    assert decision["recommended_action"] == "promote"
    assert not decision["blockers"]


def test_evaluate_packet_hold_when_blockers_exist():
    module = _load_module()
    decision = module.evaluate_packet(
        readiness_score=70.0,
        readiness_gate_pass=False,
        readiness_tier="HOLD",
        trend_week_avg=60.0,
        trend_gate_pass=False,
        dr_open_total=1,
        min_readiness_score=80.0,
        min_week_avg=80.0,
    )
    assert decision["status"] == "HOLD"
    assert decision["recommended_action"] == "hold"
    assert len(decision["blockers"]) >= 2


def test_evaluate_packet_watch_on_warning_only():
    module = _load_module()
    decision = module.evaluate_packet(
        readiness_score=85.0,
        readiness_gate_pass=True,
        readiness_tier="WATCH",
        trend_week_avg=75.0,
        trend_gate_pass=False,
        dr_open_total=0,
        min_readiness_score=80.0,
        min_week_avg=80.0,
    )
    assert decision["status"] == "WATCH"
    assert decision["recommended_action"] == "hold"
    assert not decision["blockers"]
    assert decision["warnings"]


def test_compare_with_baseline_detects_status_and_signal_regression():
    module = _load_module()
    baseline = {
        "decision": {"status": "READY"},
        "signals": {
            "readiness_score": 95.0,
            "dr_open_total": 0,
        },
        "missing_reports": [],
    }
    current = {
        "decision": {"status": "HOLD"},
        "signals": {
            "readiness_score": 70.0,
            "dr_open_total": 2,
        },
        "missing_reports": ["trend", "feedback"],
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_status_step_increase=0,
        max_readiness_score_drop=2.0,
        max_dr_open_increase=0,
        max_missing_report_increase=0,
    )
    assert any("status regression" in item for item in failures)
    assert any("readiness score regression" in item for item in failures)
    assert any("dr open regression" in item for item in failures)
    assert any("missing report regression" in item for item in failures)
