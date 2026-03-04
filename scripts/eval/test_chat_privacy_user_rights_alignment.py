import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_privacy_user_rights_alignment.py"
    spec = importlib.util.spec_from_file_location("chat_privacy_user_rights_alignment", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_user_rights_alignment_tracks_delete_export_flows():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "request_type": "DELETE",
            "status": "DONE",
            "authorized": True,
            "cascade_verified": True,
            "audit_id": "a-1",
            "reason_code": "USER_DELETE_REQUEST",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "request_type": "DELETE",
            "status": "DONE",
            "authorized": True,
            "cascade_verified": False,
            "audit_id": "",
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "request_type": "EXPORT",
            "status": "DONE",
            "authorized": False,
            "consistency_check": "FAIL",
            "audit_id": "a-3",
            "reason_code": "USER_EXPORT_REQUEST",
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "request_type": "EXPORT",
            "status": "PENDING",
            "authorized": True,
        },
        {
            "timestamp": "2026-03-03T00:04:00Z",
            "request_type": "UNKNOWN_TYPE",
            "status": "DONE",
        },
    ]
    summary = module.summarize_user_rights_alignment(
        rows,
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["delete_request_total"] == 2
    assert summary["export_request_total"] == 2
    assert summary["delete_completed_total"] == 2
    assert summary["export_completed_total"] == 1
    assert summary["delete_completion_ratio"] == 1.0
    assert summary["export_completion_ratio"] == 0.5
    assert summary["delete_cascade_verified_total"] == 1
    assert summary["delete_cascade_miss_total"] == 1
    assert summary["export_consistency_mismatch_total"] == 1
    assert summary["unauthorized_request_total"] == 1
    assert summary["missing_audit_total"] == 1
    assert summary["unknown_request_type_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_user_rights_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "delete_request_total": 1,
            "export_request_total": 1,
            "delete_completion_ratio": 0.5,
            "export_completion_ratio": 0.2,
            "delete_cascade_miss_total": 2,
            "export_consistency_mismatch_total": 1,
            "unauthorized_request_total": 1,
            "missing_audit_total": 1,
            "unknown_request_type_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_delete_request_total=2,
        min_export_request_total=2,
        min_delete_completion_ratio=0.95,
        min_export_completion_ratio=0.95,
        max_delete_cascade_miss_total=0,
        max_export_consistency_mismatch_total=0,
        max_unauthorized_request_total=0,
        max_missing_audit_total=0,
        max_unknown_request_type_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 11


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "delete_request_total": 0,
            "export_request_total": 0,
            "delete_completion_ratio": 1.0,
            "export_completion_ratio": 1.0,
            "delete_cascade_miss_total": 0,
            "export_consistency_mismatch_total": 0,
            "unauthorized_request_total": 0,
            "missing_audit_total": 0,
            "unknown_request_type_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_delete_request_total=0,
        min_export_request_total=0,
        min_delete_completion_ratio=0.0,
        min_export_completion_ratio=0.0,
        max_delete_cascade_miss_total=1000000,
        max_export_consistency_mismatch_total=1000000,
        max_unauthorized_request_total=1000000,
        max_missing_audit_total=1000000,
        max_unknown_request_type_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_user_rights_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "delete_request_total": 30,
            "export_request_total": 30,
            "delete_completed_total": 30,
            "export_completed_total": 30,
            "delete_completion_ratio": 1.0,
            "export_completion_ratio": 1.0,
            "delete_cascade_miss_total": 0,
            "export_consistency_mismatch_total": 0,
            "unauthorized_request_total": 0,
            "missing_audit_total": 0,
            "unknown_request_type_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "delete_request_total": 1,
            "export_request_total": 1,
            "delete_completed_total": 0,
            "export_completed_total": 0,
            "delete_completion_ratio": 0.2,
            "export_completion_ratio": 0.1,
            "delete_cascade_miss_total": 2,
            "export_consistency_mismatch_total": 2,
            "unauthorized_request_total": 1,
            "missing_audit_total": 1,
            "unknown_request_type_total": 1,
            "stale_minutes": 80.0,
        },
        max_delete_request_total_drop=1,
        max_export_request_total_drop=1,
        max_delete_completed_total_drop=1,
        max_export_completed_total_drop=1,
        max_delete_completion_ratio_drop=0.05,
        max_export_completion_ratio_drop=0.05,
        max_delete_cascade_miss_total_increase=0,
        max_export_consistency_mismatch_total_increase=0,
        max_unauthorized_request_total_increase=0,
        max_missing_audit_total_increase=0,
        max_unknown_request_type_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("delete_request_total regression" in item for item in failures)
    assert any("export_request_total regression" in item for item in failures)
    assert any("delete_completed_total regression" in item for item in failures)
    assert any("export_completed_total regression" in item for item in failures)
    assert any("delete_completion_ratio regression" in item for item in failures)
    assert any("export_completion_ratio regression" in item for item in failures)
    assert any("delete_cascade_miss_total regression" in item for item in failures)
    assert any("export_consistency_mismatch_total regression" in item for item in failures)
    assert any("unauthorized_request_total regression" in item for item in failures)
    assert any("missing_audit_total regression" in item for item in failures)
    assert any("unknown_request_type_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
