import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_correction_memory_schema.py"
    spec = importlib.util.spec_from_file_location("chat_correction_memory_schema", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_correction_memory_schema_tracks_required_and_active_integrity():
    module = _load_module()
    rows = [
        {
            "updated_at": "2026-03-03T00:00:00Z",
            "correction_id": "c1",
            "domain": "refund",
            "trigger_pattern": "환불 가능",
            "approved_answer": "환불은 주문일 기준 7일 이내 가능",
            "owner": "ops1",
            "locale": "ko-KR",
            "channel": "web",
            "intent": "REFUND_POLICY",
            "approval_state": "ACTIVE",
            "expiry": "2026-03-10T00:00:00Z",
        },
        {
            "updated_at": "2026-03-03T00:01:00Z",
            "correction_id": "c2",
            "domain": "refund",
            "trigger_pattern": "환불 가능",
            "approved_answer": "환불은 주문일 기준 7일 이내 가능",
            "owner": "ops2",
            "locale": "ko-KR",
            "channel": "web",
            "intent": "REFUND_POLICY",
            "is_active": True,
            "approval_state": "DRAFT",
            "expiry": "2026-03-01T00:00:00Z",
        },
        {
            "updated_at": "2026-03-03T00:03:00Z",
            "correction_id": "",
            "domain": "shipping",
            "trigger_pattern": "",
            "approved_answer": "배송은 평균 2일",
            "owner": "",
            "locale": "",
            "channel": "app",
            "intent": "",
            "approval_state": "BROKEN",
            "is_active": False,
        },
    ]
    summary = module.summarize_correction_memory_schema(
        rows,
        now=datetime(2026, 3, 3, 0, 4, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["record_total"] == 3
    assert summary["active_total"] == 2
    assert summary["missing_required_total"] == 1
    assert summary["missing_scope_total"] == 1
    assert summary["invalid_approval_state_total"] == 1
    assert summary["unapproved_active_total"] == 1
    assert summary["expired_active_total"] == 1
    assert summary["duplicate_active_pattern_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_correction_memory_schema_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "record_total": 1,
            "missing_required_total": 2,
            "missing_scope_total": 1,
            "invalid_approval_state_total": 1,
            "unapproved_active_total": 2,
            "expired_active_total": 1,
            "duplicate_active_pattern_total": 3,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_record_total=2,
        max_missing_required_total=0,
        max_missing_scope_total=0,
        max_invalid_approval_state_total=0,
        max_unapproved_active_total=0,
        max_expired_active_total=0,
        max_duplicate_active_pattern_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "record_total": 0,
            "missing_required_total": 0,
            "missing_scope_total": 0,
            "invalid_approval_state_total": 0,
            "unapproved_active_total": 0,
            "expired_active_total": 0,
            "duplicate_active_pattern_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_record_total=0,
        max_missing_required_total=1000000,
        max_missing_scope_total=1000000,
        max_invalid_approval_state_total=1000000,
        max_unapproved_active_total=1000000,
        max_expired_active_total=1000000,
        max_duplicate_active_pattern_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_correction_memory_schema_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "record_total": 20,
            "active_total": 18,
            "missing_required_total": 0,
            "missing_scope_total": 0,
            "invalid_approval_state_total": 0,
            "unapproved_active_total": 0,
            "expired_active_total": 0,
            "duplicate_active_pattern_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "record_total": 1,
            "active_total": 1,
            "missing_required_total": 2,
            "missing_scope_total": 1,
            "invalid_approval_state_total": 1,
            "unapproved_active_total": 1,
            "expired_active_total": 1,
            "duplicate_active_pattern_total": 1,
            "stale_minutes": 90.0,
        },
        max_record_total_drop=1,
        max_active_total_drop=1,
        max_missing_required_total_increase=0,
        max_missing_scope_total_increase=0,
        max_invalid_approval_state_total_increase=0,
        max_unapproved_active_total_increase=0,
        max_expired_active_total_increase=0,
        max_duplicate_active_pattern_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("record_total regression" in item for item in failures)
    assert any("active_total regression" in item for item in failures)
    assert any("missing_required_total regression" in item for item in failures)
    assert any("missing_scope_total regression" in item for item in failures)
    assert any("invalid_approval_state_total regression" in item for item in failures)
    assert any("unapproved_active_total regression" in item for item in failures)
    assert any("expired_active_total regression" in item for item in failures)
    assert any("duplicate_active_pattern_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
