import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_prompt_runtime_integrity_fallback_guard.py"
    spec = importlib.util.spec_from_file_location("chat_prompt_runtime_integrity_fallback_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_prompt_runtime_integrity_fallback_guard_tracks_unsafe_loads():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "runtime_load_id": "l1",
            "integrity_checked": True,
            "integrity_mismatch": False,
            "load_decision": "LOAD",
            "trusted_version_loaded": True,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "runtime_load_id": "l2",
            "integrity_checked": True,
            "integrity_mismatch": True,
            "fallback_applied": True,
            "fallback_success": True,
            "trusted_version_loaded": True,
            "reason_code": "PROMPT_INTEGRITY_MISMATCH_FALLBACK",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "runtime_load_id": "l3",
            "integrity_checked": True,
            "integrity_mismatch": True,
            "fallback_applied": False,
            "load_decision": "ALLOW",
            "trusted_version_loaded": False,
            "reason_code": "",
        },
    ]

    summary = module.summarize_prompt_runtime_integrity_fallback_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["runtime_load_total"] == 3
    assert summary["integrity_checked_total"] == 3
    assert summary["integrity_checked_ratio"] == 1.0
    assert summary["integrity_mismatch_total"] == 2
    assert summary["fallback_applied_total"] == 1
    assert summary["fallback_success_total"] == 1
    assert summary["fallback_coverage_ratio"] == 0.5
    assert summary["fallback_success_ratio"] == 1.0
    assert summary["fallback_missing_total"] == 1
    assert summary["trusted_version_loaded_total"] == 2
    assert summary["unsafe_load_total"] == 1
    assert summary["reason_code_missing_total"] == 1
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_prompt_runtime_integrity_fallback_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "runtime_load_total": 1,
            "integrity_checked_ratio": 0.2,
            "fallback_coverage_ratio": 0.1,
            "fallback_success_ratio": 0.2,
            "fallback_missing_total": 2,
            "unsafe_load_total": 1,
            "reason_code_missing_total": 3,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_runtime_load_total=2,
        min_integrity_checked_ratio=0.99,
        min_fallback_coverage_ratio=1.0,
        min_fallback_success_ratio=1.0,
        max_fallback_missing_total=0,
        max_unsafe_load_total=0,
        max_reason_code_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "runtime_load_total": 0,
            "integrity_checked_ratio": 1.0,
            "fallback_coverage_ratio": 1.0,
            "fallback_success_ratio": 1.0,
            "fallback_missing_total": 0,
            "unsafe_load_total": 0,
            "reason_code_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_runtime_load_total=0,
        min_integrity_checked_ratio=0.0,
        min_fallback_coverage_ratio=0.0,
        min_fallback_success_ratio=0.0,
        max_fallback_missing_total=1000000,
        max_unsafe_load_total=1000000,
        max_reason_code_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
