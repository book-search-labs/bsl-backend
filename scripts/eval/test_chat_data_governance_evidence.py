import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_data_governance_evidence.py"
    spec = importlib.util.spec_from_file_location("chat_data_governance_evidence", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_evaluate_evidence_ready_when_signals_are_clean():
    module = _load_module()
    decision = module.evaluate_evidence(
        retention_gate_pass=True,
        egress_gate_pass=True,
        retention_event_total=120,
        egress_event_total=180,
        retention_overdue_total=0,
        retention_unapproved_exception_total=0,
        egress_violation_total=0,
        egress_unmasked_sensitive_total=0,
        retention_trace_coverage_ratio=1.0,
        egress_trace_coverage_ratio=1.0,
        egress_alert_coverage_ratio=1.0,
        min_trace_coverage_ratio=1.0,
        min_lifecycle_score=80.0,
        require_events=True,
        missing_reports=[],
        require_reports=True,
    )
    assert decision["status"] == "READY"
    assert decision["recommended_action"] == "promote"
    assert not decision["blockers"]


def test_evaluate_evidence_hold_when_blockers_exist():
    module = _load_module()
    decision = module.evaluate_evidence(
        retention_gate_pass=False,
        egress_gate_pass=True,
        retention_event_total=0,
        egress_event_total=5,
        retention_overdue_total=3,
        retention_unapproved_exception_total=1,
        egress_violation_total=2,
        egress_unmasked_sensitive_total=1,
        retention_trace_coverage_ratio=0.8,
        egress_trace_coverage_ratio=0.9,
        egress_alert_coverage_ratio=0.5,
        min_trace_coverage_ratio=1.0,
        min_lifecycle_score=80.0,
        require_events=True,
        missing_reports=["retention"],
        require_reports=True,
    )
    assert decision["status"] == "HOLD"
    assert decision["recommended_action"] == "hold"
    assert len(decision["blockers"]) >= 4


def test_evaluate_evidence_watch_when_warnings_only():
    module = _load_module()
    decision = module.evaluate_evidence(
        retention_gate_pass=True,
        egress_gate_pass=True,
        retention_event_total=5,
        egress_event_total=8,
        retention_overdue_total=0,
        retention_unapproved_exception_total=0,
        egress_violation_total=0,
        egress_unmasked_sensitive_total=0,
        retention_trace_coverage_ratio=1.0,
        egress_trace_coverage_ratio=1.0,
        egress_alert_coverage_ratio=1.0,
        min_trace_coverage_ratio=1.0,
        min_lifecycle_score=80.0,
        require_events=False,
        missing_reports=[],
        require_reports=False,
    )
    assert decision["status"] == "WATCH"
    assert decision["recommended_action"] == "hold"
    assert not decision["blockers"]
    assert decision["warnings"]
