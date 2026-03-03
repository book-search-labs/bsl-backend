import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_source_trust_registry.py"
    spec = importlib.util.spec_from_file_location("chat_source_trust_registry", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_registry_tracks_coverage_and_staleness():
    module = _load_module()
    rows = [
        {
            "source_type": "OFFICIAL_POLICY",
            "trust_weight": 1.0,
            "freshness_ttl": 86400,
            "version": "v1",
            "updated_at": "2026-03-02T00:00:00Z",
        },
        {
            "source_type": "EVENT_NOTICE",
            "trust_weight": 0.8,
            "freshness_ttl": 3600,
            "version": "v1",
            "updated_at": "2026-03-03T00:00:00Z",
        },
        {
            "source_type": "ANNOUNCEMENT",
            "trust_weight": 0.7,
            "freshness_ttl": 7200,
            "version": "v2",
            "updated_at": "2026-03-03T00:00:00Z",
        },
        {
            "source_type": "USER_GENERATED",
            "trust_weight": 0.4,
            "freshness_ttl": 1800,
            "version": "v5",
            "updated_at": "2026-03-03T00:00:00Z",
        },
    ]
    summary = module.summarize_registry(
        rows,
        max_policy_age_days=7.0,
        now=datetime(2026, 3, 3, 0, 10, tzinfo=timezone.utc),
    )
    assert summary["policy_total"] == 4
    assert summary["coverage_ratio"] == 1.0
    assert summary["missing_source_types"] == []
    assert summary["invalid_weight_total"] == 0
    assert summary["invalid_ttl_total"] == 0
    assert summary["missing_version_total"] == 0
    assert summary["stale_policy_total"] == 0


def test_evaluate_gate_detects_policy_violations():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "policy_total": 2,
            "coverage_ratio": 0.5,
            "invalid_weight_total": 1,
            "invalid_ttl_total": 1,
            "missing_version_total": 1,
            "stale_ratio": 0.5,
            "stale_minutes": 120.0,
        },
        min_policy_total=3,
        min_coverage_ratio=1.0,
        max_invalid_weight_total=0,
        max_invalid_ttl_total=0,
        max_missing_version_total=0,
        max_stale_ratio=0.1,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "policy_total": 0,
            "coverage_ratio": 0.0,
            "invalid_weight_total": 0,
            "invalid_ttl_total": 0,
            "missing_version_total": 0,
            "stale_ratio": 0.0,
            "stale_minutes": 0.0,
        },
        min_policy_total=0,
        min_coverage_ratio=1.0,
        max_invalid_weight_total=0,
        max_invalid_ttl_total=0,
        max_missing_version_total=0,
        max_stale_ratio=0.1,
        max_stale_minutes=60.0,
    )
    assert failures == []
