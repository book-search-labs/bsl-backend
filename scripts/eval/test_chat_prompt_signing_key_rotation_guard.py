import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_prompt_signing_key_rotation_guard.py"
    spec = importlib.util.spec_from_file_location("chat_prompt_signing_key_rotation_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_prompt_signing_key_rotation_guard_tracks_access_and_audit_issues():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "rotation_id": "r1",
            "rotation_success": True,
            "audit_logged": True,
            "reason_code": "KEY_ROTATION_COMPLETED",
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "rotation_id": "r2",
            "rotation_success": False,
            "unauthorized_key_access": True,
            "least_privilege_violation": True,
            "deprecated_key_used_for_signing": True,
            "kms_sync_ok": False,
            "audit_logged": False,
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "event_type": "access_check",
            "access_decision": "allow",
            "audit_logged": False,
        },
    ]

    summary = module.summarize_prompt_signing_key_rotation_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["event_total"] == 3
    assert summary["key_rotation_total"] == 2
    assert summary["key_rotation_success_total"] == 1
    assert summary["key_rotation_failed_total"] == 1
    assert summary["key_rotation_success_ratio"] == 0.5
    assert summary["unauthorized_key_access_total"] == 1
    assert summary["least_privilege_violation_total"] == 1
    assert summary["deprecated_key_sign_total"] == 1
    assert summary["kms_sync_failed_total"] == 1
    assert summary["audit_log_missing_total"] == 2
    assert summary["reason_code_missing_total"] == 1
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_prompt_signing_key_rotation_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "event_total": 1,
            "key_rotation_total": 0,
            "key_rotation_success_ratio": 0.2,
            "key_rotation_failed_total": 2,
            "unauthorized_key_access_total": 1,
            "least_privilege_violation_total": 1,
            "deprecated_key_sign_total": 1,
            "kms_sync_failed_total": 1,
            "audit_log_missing_total": 2,
            "reason_code_missing_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_event_total=2,
        min_key_rotation_total=1,
        min_key_rotation_success_ratio=0.95,
        max_key_rotation_failed_total=0,
        max_unauthorized_key_access_total=0,
        max_least_privilege_violation_total=0,
        max_deprecated_key_sign_total=0,
        max_kms_sync_failed_total=0,
        max_audit_log_missing_total=0,
        max_reason_code_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 12


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "key_rotation_total": 0,
            "key_rotation_success_ratio": 1.0,
            "key_rotation_failed_total": 0,
            "unauthorized_key_access_total": 0,
            "least_privilege_violation_total": 0,
            "deprecated_key_sign_total": 0,
            "kms_sync_failed_total": 0,
            "audit_log_missing_total": 0,
            "reason_code_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_key_rotation_total=0,
        min_key_rotation_success_ratio=0.0,
        max_key_rotation_failed_total=1000000,
        max_unauthorized_key_access_total=1000000,
        max_least_privilege_violation_total=1000000,
        max_deprecated_key_sign_total=1000000,
        max_kms_sync_failed_total=1000000,
        max_audit_log_missing_total=1000000,
        max_reason_code_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
