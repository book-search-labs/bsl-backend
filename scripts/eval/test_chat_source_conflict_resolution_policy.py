import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_source_conflict_resolution_policy.py"
    spec = importlib.util.spec_from_file_location("chat_source_conflict_resolution_policy", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_resolution_policy_tracks_official_preference_and_safety():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "is_conflict": True,
            "conflict_severity": "HIGH",
            "resolution_strategy": "OFFICIAL_LATEST",
            "decision": "ABSTAIN",
            "official_source_available": True,
            "official_source_selected": True,
            "resolved": True,
            "policy_version": "v1",
            "reason_code": "CONFLICT_HIGH",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "is_conflict": True,
            "conflict_severity": "HIGH",
            "resolution_strategy": "BAD",
            "decision": "ANSWER",
            "official_source_available": True,
            "official_source_selected": False,
            "resolved": False,
            "policy_version": "",
            "reason_code": "",
        },
    ]
    summary = module.summarize_resolution_policy(
        rows,
        now=datetime(2026, 3, 3, 0, 2, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 2
    assert summary["conflict_total"] == 2
    assert summary["high_conflict_total"] == 2
    assert summary["high_conflict_safe_total"] == 1
    assert summary["high_conflict_unsafe_total"] == 1
    assert summary["official_available_total"] == 2
    assert summary["official_preferred_total"] == 1
    assert summary["official_preference_ratio"] == 0.5
    assert summary["resolved_total"] == 1
    assert summary["resolution_rate"] == 0.5
    assert summary["invalid_strategy_total"] == 1
    assert summary["missing_policy_version_total"] == 1
    assert summary["missing_reason_code_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_resolution_policy_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "conflict_total": 2,
            "high_conflict_unsafe_total": 1,
            "official_preference_ratio": 0.3,
            "resolution_rate": 0.2,
            "invalid_strategy_total": 1,
            "missing_policy_version_total": 1,
            "missing_reason_code_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_conflict_total=3,
        max_high_conflict_unsafe_total=0,
        min_official_preference_ratio=0.8,
        min_resolution_rate=0.7,
        max_invalid_strategy_total=0,
        max_missing_policy_version_total=0,
        max_missing_reason_code_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 9


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "conflict_total": 0,
            "high_conflict_unsafe_total": 0,
            "official_preference_ratio": 1.0,
            "resolution_rate": 1.0,
            "invalid_strategy_total": 0,
            "missing_policy_version_total": 0,
            "missing_reason_code_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_conflict_total=0,
        max_high_conflict_unsafe_total=1000000,
        min_official_preference_ratio=0.0,
        min_resolution_rate=0.0,
        max_invalid_strategy_total=1000000,
        max_missing_policy_version_total=1000000,
        max_missing_reason_code_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_source_conflict_resolution_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "conflict_total": 20,
            "high_conflict_total": 10,
            "high_conflict_unsafe_total": 0,
            "official_preference_ratio": 0.9,
            "resolution_rate": 0.9,
            "invalid_strategy_total": 0,
            "missing_policy_version_total": 0,
            "missing_reason_code_total": 0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "conflict_total": 1,
            "high_conflict_total": 1,
            "high_conflict_unsafe_total": 1,
            "official_preference_ratio": 0.1,
            "resolution_rate": 0.2,
            "invalid_strategy_total": 1,
            "missing_policy_version_total": 1,
            "missing_reason_code_total": 1,
            "stale_minutes": 80.0,
        },
        max_conflict_total_drop=1,
        max_high_conflict_total_drop=1,
        max_high_conflict_unsafe_total_increase=0,
        max_official_preference_ratio_drop=0.05,
        max_resolution_rate_drop=0.05,
        max_invalid_strategy_total_increase=0,
        max_missing_policy_version_total_increase=0,
        max_missing_reason_code_total_increase=0,
        max_stale_minutes_increase=30.0,
    )
    assert any("conflict_total regression" in item for item in failures)
    assert any("high_conflict_total regression" in item for item in failures)
    assert any("high_conflict_unsafe_total regression" in item for item in failures)
    assert any("official_preference_ratio regression" in item for item in failures)
    assert any("resolution_rate regression" in item for item in failures)
    assert any("invalid_strategy_total regression" in item for item in failures)
    assert any("missing_policy_version_total regression" in item for item in failures)
    assert any("missing_reason_code_total regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
