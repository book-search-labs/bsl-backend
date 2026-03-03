import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_cache_staleness_guard.py"
    spec = importlib.util.spec_from_file_location("chat_tool_cache_staleness_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_staleness_guard_flags_leak_and_missing_stamp():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "cache_hit",
            "cache_age_seconds": 600,
            "stale_threshold_seconds": 300,
            "stale_blocked": True,
            "served_from_cache": False,
            "freshness_stamp": "2026-03-03T00:00:00Z",
            "forced_origin_fetch": True,
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "event_type": "cache_response",
            "cache_age_seconds": 700,
            "stale_threshold_seconds": 300,
            "stale_blocked": False,
            "served_from_cache": True,
            "freshness_stamp": "",
            "forced_origin_fetch": False,
        },
    ]
    summary = module.summarize_staleness_guard(
        rows,
        stale_threshold_seconds=300,
        now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
    )
    assert summary["stale_response_total"] == 2
    assert summary["stale_block_total"] == 1
    assert summary["stale_leak_total"] == 1
    assert summary["freshness_stamp_missing_total"] == 1
    assert summary["forced_origin_fetch_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "stale_response_total": 10,
            "stale_leak_total": 1,
            "stale_block_ratio": 0.5,
            "freshness_stamp_missing_total": 1,
            "forced_origin_fetch_total": 0,
            "stale_minutes": 120.0,
        },
        min_window=1,
        max_stale_leak_total=0,
        min_stale_block_ratio=0.95,
        max_freshness_stamp_missing_total=0,
        min_forced_origin_fetch_total=1,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "stale_response_total": 0,
            "stale_leak_total": 0,
            "stale_block_ratio": 1.0,
            "freshness_stamp_missing_total": 0,
            "forced_origin_fetch_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        max_stale_leak_total=0,
        min_stale_block_ratio=0.95,
        max_freshness_stamp_missing_total=0,
        min_forced_origin_fetch_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []
