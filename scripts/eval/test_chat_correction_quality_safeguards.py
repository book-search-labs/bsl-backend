import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_correction_quality_safeguards.py"
    spec = importlib.util.spec_from_file_location("chat_correction_quality_safeguards", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_correction_quality_safeguards_tracks_overapply_and_rollback_sla():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "correction_applied": True,
            "overapply_detected": True,
            "precision_gate_fail": True,
            "false_positive_reported": True,
            "false_positive_status": "OPEN",
            "report_to_rollback_minutes": 45,
            "actor_id": "",
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "correction_applied": True,
            "false_positive_reported": True,
            "false_positive_status": "RESOLVED",
            "report_to_rollback_minutes": 10,
            "rolled_back": True,
            "actor_id": "ops1",
            "reason_code": "FALSE_POSITIVE_ROLLBACK",
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "correction_applied": False,
            "emergency_blocked": True,
            "actor_id": "ops2",
            "reason_code": "EMERGENCY_BLOCK",
        },
    ]
    summary = module.summarize_correction_quality_safeguards(
        rows,
        now=datetime(2026, 3, 3, 0, 4, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["event_total"] == 3
    assert summary["correction_applied_total"] == 2
    assert summary["overapply_total"] == 1
    assert summary["precision_gate_fail_total"] == 1
    assert summary["false_positive_report_total"] == 2
    assert summary["false_positive_open_total"] == 1
    assert summary["emergency_block_total"] == 1
    assert summary["rollback_total"] == 1
    assert summary["rollback_sla_breach_total"] == 1
    assert summary["missing_audit_total"] == 1
    assert summary["p95_report_to_rollback_minutes"] == 45
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_correction_quality_safeguards_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "event_total": 1,
            "overapply_total": 2,
            "precision_gate_fail_total": 3,
            "false_positive_open_total": 2,
            "rollback_sla_breach_total": 2,
            "missing_audit_total": 1,
            "p95_report_to_rollback_minutes": 90.0,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_event_total=2,
        max_overapply_total=0,
        max_precision_gate_fail_total=0,
        max_false_positive_open_total=0,
        max_rollback_sla_breach_total=0,
        max_missing_audit_total=0,
        max_p95_report_to_rollback_minutes=30.0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "overapply_total": 0,
            "precision_gate_fail_total": 0,
            "false_positive_open_total": 0,
            "rollback_sla_breach_total": 0,
            "missing_audit_total": 0,
            "p95_report_to_rollback_minutes": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        max_overapply_total=1000000,
        max_precision_gate_fail_total=1000000,
        max_false_positive_open_total=1000000,
        max_rollback_sla_breach_total=1000000,
        max_missing_audit_total=1000000,
        max_p95_report_to_rollback_minutes=1000000.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_correction_quality_safeguards_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "event_total": 30,
            "correction_applied_total": 20,
            "overapply_total": 0,
            "precision_gate_fail_total": 0,
            "false_positive_open_total": 0,
            "rollback_sla_breach_total": 0,
            "missing_audit_total": 0,
            "p95_report_to_rollback_minutes": 10.0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "event_total": 1,
            "correction_applied_total": 1,
            "overapply_total": 2,
            "precision_gate_fail_total": 2,
            "false_positive_open_total": 1,
            "rollback_sla_breach_total": 1,
            "missing_audit_total": 1,
            "p95_report_to_rollback_minutes": 90.0,
            "stale_minutes": 90.0,
        },
        max_event_total_drop=1,
        max_correction_applied_total_drop=1,
        max_overapply_total_increase=0,
        max_precision_gate_fail_total_increase=0,
        max_false_positive_open_total_increase=0,
        max_rollback_sla_breach_total_increase=0,
        max_missing_audit_total_increase=0,
        max_p95_report_to_rollback_minutes_increase=30.0,
        max_stale_minutes_increase=30.0,
    )
    assert any("event_total regression" in item for item in failures)
    assert any("correction_applied_total regression" in item for item in failures)
    assert any("overapply_total regression" in item for item in failures)
    assert any("precision_gate_fail_total regression" in item for item in failures)
    assert any("false_positive_open_total regression" in item for item in failures)
    assert any("rollback_sla_breach_total regression" in item for item in failures)
    assert any("missing_audit_total regression" in item for item in failures)
    assert any("p95_report_to_rollback_minutes regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
