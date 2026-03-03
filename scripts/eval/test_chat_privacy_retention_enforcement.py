import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_privacy_retention_enforcement.py"
    spec = importlib.util.spec_from_file_location("chat_privacy_retention_enforcement", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_retention_enforcement_tracks_purge_and_holds():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "data_type": "session",
            "expired": True,
            "purged": True,
            "audit_id": "a-1",
            "reason_code": "TTL_EXPIRED",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "data_type": "summary",
            "expired": True,
            "purged": False,
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "data_type": "evidence",
            "expired": True,
            "legal_hold": True,
            "purged": True,
            "audit_id": "",
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "data_type": "summary",
            "expired": True,
            "retention_days": 0,
        },
    ]
    summary = module.summarize_retention_enforcement(
        rows,
        now=datetime(2026, 3, 3, 0, 4, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 4
    assert summary["expired_total"] == 4
    assert summary["purge_due_total"] == 3
    assert summary["purged_total"] == 2
    assert summary["purge_miss_total"] == 2
    assert summary["legal_hold_total"] == 1
    assert summary["hold_exempt_total"] == 1
    assert summary["hold_violation_total"] == 1
    assert summary["invalid_retention_policy_total"] == 4
    assert summary["delete_audit_missing_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_retention_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "expired_total": 1,
            "purge_coverage_ratio": 0.4,
            "purge_miss_total": 2,
            "hold_violation_total": 1,
            "invalid_retention_policy_total": 2,
            "delete_audit_missing_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_expired_total=2,
        min_purge_coverage_ratio=0.9,
        max_purge_miss_total=0,
        max_hold_violation_total=0,
        max_invalid_retention_policy_total=0,
        max_delete_audit_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "expired_total": 0,
            "purge_coverage_ratio": 1.0,
            "purge_miss_total": 0,
            "hold_violation_total": 0,
            "invalid_retention_policy_total": 0,
            "delete_audit_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_expired_total=0,
        min_purge_coverage_ratio=0.0,
        max_purge_miss_total=1000000,
        max_hold_violation_total=1000000,
        max_invalid_retention_policy_total=1000000,
        max_delete_audit_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
