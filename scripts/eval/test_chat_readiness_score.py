import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_readiness_score.py"
    spec = importlib.util.spec_from_file_location("chat_readiness_score", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_compute_readiness_promote_when_signals_are_healthy():
    module = _load_module()
    readiness = module.compute_readiness(
        launch_pass=True,
        canary_pass=True,
        insufficient_ratio=0.05,
        reason_invalid_ratio=0.0,
        reason_unknown_ratio=0.01,
        liveops_pass_ratio=1.0,
        rollback_rate=0.0,
        open_incident_total=0,
        mtta_sec=100.0,
        mttr_sec=300.0,
        capacity_mode="NORMAL",
        dr_recovery_ratio=1.0,
        dr_open_total=0,
        dr_drill_total=1,
        target_mtta_sec=600.0,
        target_mttr_sec=7200.0,
    )
    assert readiness["total_score"] >= 85.0
    assert readiness["tier"] == "READY"
    assert readiness["recommended_action"] == "promote"
    assert not readiness["blockers"]


def test_compute_readiness_has_blocker_when_launch_failed():
    module = _load_module()
    readiness = module.compute_readiness(
        launch_pass=False,
        canary_pass=False,
        insufficient_ratio=0.5,
        reason_invalid_ratio=0.1,
        reason_unknown_ratio=0.3,
        liveops_pass_ratio=0.6,
        rollback_rate=0.2,
        open_incident_total=1,
        mtta_sec=900.0,
        mttr_sec=9000.0,
        capacity_mode="FAIL_CLOSED",
        dr_recovery_ratio=0.5,
        dr_open_total=1,
        dr_drill_total=1,
        target_mtta_sec=600.0,
        target_mttr_sec=7200.0,
    )
    assert readiness["recommended_action"] == "hold"
    assert "launch_gate_failed" in readiness["blockers"]
    assert "open_incident_exists" in readiness["blockers"]


def test_compute_readiness_watch_when_non_blocking_degradation():
    module = _load_module()
    readiness = module.compute_readiness(
        launch_pass=True,
        canary_pass=True,
        insufficient_ratio=0.15,
        reason_invalid_ratio=0.0,
        reason_unknown_ratio=0.03,
        liveops_pass_ratio=0.85,
        rollback_rate=0.10,
        open_incident_total=0,
        mtta_sec=500.0,
        mttr_sec=1000.0,
        capacity_mode="DEGRADE_LEVEL_1",
        dr_recovery_ratio=1.0,
        dr_open_total=0,
        dr_drill_total=1,
        target_mtta_sec=600.0,
        target_mttr_sec=7200.0,
    )
    assert 70.0 <= readiness["total_score"] < 85.0
    assert readiness["tier"] == "WATCH"
    assert readiness["recommended_action"] == "hold"
