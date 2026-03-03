import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_korean_runtime_normalization_guard.py"
    spec = importlib.util.spec_from_file_location("chat_korean_runtime_normalization_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_korean_runtime_normalization_guard_tracks_fallback_and_drift():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "normalization_checked": True,
            "term_normalization_applied": True,
            "original_text": "주문 배송 확인 합니다",
            "normalized_text": "주문 배송 확인합니다.",
            "edit_ratio": 0.10,
            "meaning_preserved": True,
            "reason_code": "TERM_NORMALIZED",
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "normalization_checked": True,
            "style_normalization_applied": True,
            "original_text": "환불 불가 합니다 문의바람",
            "normalized_text": "환불은 현재 불가합니다.",
            "edit_ratio": 0.72,
            "excessive_edit_detected": True,
            "fallback_applied": False,
            "meaning_preserved": False,
            "reason_code": "",
        },
        {
            "timestamp": "2026-03-03T00:00:30Z",
            "normalization_checked": False,
            "original_text": "ok",
            "normalized_text": "ok",
            "edit_ratio": 0.0,
        },
    ]

    summary = module.summarize_korean_runtime_normalization_guard(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["response_total"] == 3
    assert summary["normalization_checked_total"] == 2
    assert abs(summary["normalization_checked_ratio"] - (2.0 / 3.0)) < 1e-9
    assert summary["normalization_bypass_total"] == 1
    assert summary["term_normalization_applied_total"] == 1
    assert summary["style_normalization_applied_total"] == 1
    assert summary["normalization_applied_total"] == 2
    assert summary["excessive_edit_total"] == 1
    assert summary["excessive_edit_without_fallback_total"] == 1
    assert summary["meaning_drift_total"] == 1
    assert summary["fallback_applied_total"] == 0
    assert summary["fallback_coverage_ratio"] == 0.0
    assert summary["reason_code_missing_total"] == 1
    assert summary["p95_edit_ratio"] == 0.72
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_korean_runtime_normalization_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "response_total": 1,
            "normalization_checked_ratio": 0.4,
            "fallback_coverage_ratio": 0.2,
            "normalization_bypass_total": 3,
            "meaning_drift_total": 2,
            "excessive_edit_without_fallback_total": 1,
            "reason_code_missing_total": 1,
            "p95_edit_ratio": 0.8,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_response_total=2,
        min_normalization_checked_ratio=0.95,
        min_fallback_coverage_ratio=1.0,
        max_normalization_bypass_total=0,
        max_meaning_drift_total=0,
        max_excessive_edit_without_fallback_total=0,
        max_reason_code_missing_total=0,
        max_p95_edit_ratio=0.3,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "response_total": 0,
            "normalization_checked_ratio": 1.0,
            "fallback_coverage_ratio": 1.0,
            "normalization_bypass_total": 0,
            "meaning_drift_total": 0,
            "excessive_edit_without_fallback_total": 0,
            "reason_code_missing_total": 0,
            "p95_edit_ratio": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_response_total=0,
        min_normalization_checked_ratio=0.0,
        min_fallback_coverage_ratio=0.0,
        max_normalization_bypass_total=1000000,
        max_meaning_drift_total=1000000,
        max_excessive_edit_without_fallback_total=1000000,
        max_reason_code_missing_total=1000000,
        max_p95_edit_ratio=1.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
