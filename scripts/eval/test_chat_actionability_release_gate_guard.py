import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_actionability_release_gate_guard.py"
    spec = importlib.util.spec_from_file_location("chat_actionability_release_gate_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_actionability_release_gate_guard_tracks_metrics():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "intent_bucket": "ORDER",
            "low_actionability_ratio": 0.30,
            "sample_count": 50,
            "release_decision": "ALLOW",
            "partial_isolation_applied": False,
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "intent_bucket": "REFUND",
            "low_actionability_ratio": 0.20,
            "sample_count": 40,
            "release_decision": "PARTIAL_ROLLBACK",
            "partial_isolation_applied": True,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "intent_bucket": "GENERAL",
            "low_actionability_ratio": 0.10,
            "sample_count": 40,
            "release_decision": "BLOCK",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "intent_bucket": "SHIPPING",
            "low_actionability_ratio": 0.10,
            "sample_count": 40,
            "release_decision": "ALLOW",
        },
    ]
    summary = module.summarize_actionability_release_gate_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
        min_samples_per_bucket=20,
    )
    assert summary["window_size"] == 4
    assert summary["event_total"] == 4
    assert summary["over_threshold_total"] == 2
    assert summary["blocked_promotion_total"] == 1
    assert summary["missed_block_total"] == 1
    assert abs(summary["block_coverage_ratio"] - 0.5) < 1e-9
    assert summary["partial_isolation_applied_total"] == 1
    assert summary["partial_isolation_missing_total"] == 1
    assert abs(summary["partial_isolation_ratio"] - 0.5) < 1e-9
    assert summary["false_block_total"] == 1
    assert abs(summary["false_block_ratio"] - 0.5) < 1e-9
    assert abs(summary["stale_minutes"] - 0.5) < 1e-9


def test_evaluate_gate_detects_actionability_release_gate_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 4,
            "event_total": 1,
            "block_coverage_ratio": 0.3,
            "partial_isolation_ratio": 0.2,
            "missed_block_total": 2,
            "partial_isolation_missing_total": 3,
            "false_block_ratio": 0.5,
            "stale_minutes": 120.0,
        },
        min_window=5,
        min_event_total=2,
        min_block_coverage_ratio=1.0,
        min_partial_isolation_ratio=1.0,
        max_missed_block_total=0,
        max_partial_isolation_missing_total=0,
        max_false_block_ratio=0.1,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "event_total": 0,
            "block_coverage_ratio": 1.0,
            "partial_isolation_ratio": 1.0,
            "missed_block_total": 0,
            "partial_isolation_missing_total": 0,
            "false_block_ratio": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_event_total=0,
        min_block_coverage_ratio=0.0,
        min_partial_isolation_ratio=0.0,
        max_missed_block_total=1000000,
        max_partial_isolation_missing_total=1000000,
        max_false_block_ratio=1.0,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
