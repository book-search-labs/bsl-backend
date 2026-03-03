import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_tool_cache_strategy.py"
    spec = importlib.util.spec_from_file_location("chat_tool_cache_strategy", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_cache_strategy_flags_key_and_ttl_issues():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "event_type": "cache_hit",
            "user_id": "u1",
            "tool": "ORDER_STATUS",
            "params_hash": "abc",
            "ttl_class": "short",
            "ttl_seconds": 10,
        },
        {
            "timestamp": "2026-03-03T00:00:01Z",
            "event_type": "cache_miss",
            "user_id": "",
            "tool": "",
            "params_hash": "",
            "ttl_class": "UNKNOWN",
            "ttl_seconds": 100,
        },
        {
            "timestamp": "2026-03-03T00:00:02Z",
            "event_type": "cache_bypass",
        },
    ]
    summary = module.summarize_cache_strategy(rows, now=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc))
    assert summary["lookup_total"] == 3
    assert summary["cache_hit_total"] == 1
    assert summary["cache_miss_total"] == 1
    assert summary["cache_bypass_total"] == 1
    assert summary["key_missing_field_total"] == 3
    assert summary["ttl_class_unknown_total"] == 1
    assert summary["ttl_out_of_policy_total"] == 1


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "lookup_total": 10,
            "hit_ratio": 0.1,
            "bypass_ratio": 0.9,
            "key_missing_field_total": 1,
            "ttl_class_unknown_total": 1,
            "ttl_out_of_policy_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=1,
        min_hit_ratio=0.5,
        max_bypass_ratio=0.3,
        max_key_missing_field_total=0,
        max_ttl_class_unknown_total=0,
        max_ttl_out_of_policy_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 6


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "lookup_total": 0,
            "hit_ratio": 1.0,
            "bypass_ratio": 0.0,
            "key_missing_field_total": 0,
            "ttl_class_unknown_total": 0,
            "ttl_out_of_policy_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_hit_ratio=0.5,
        max_bypass_ratio=0.3,
        max_key_missing_field_total=0,
        max_ttl_class_unknown_total=0,
        max_ttl_out_of_policy_total=0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_cache_strategy_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "hit_ratio": 0.90,
                "bypass_ratio": 0.10,
                "key_missing_field_total": 0,
                "ttl_class_unknown_total": 0,
                "ttl_out_of_policy_total": 0,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "hit_ratio": 0.60,
            "bypass_ratio": 0.35,
            "key_missing_field_total": 2,
            "ttl_class_unknown_total": 1,
            "ttl_out_of_policy_total": 3,
            "stale_minutes": 40.0,
        },
        max_hit_ratio_drop=0.05,
        max_bypass_ratio_increase=0.05,
        max_key_missing_field_total_increase=0,
        max_ttl_class_unknown_total_increase=0,
        max_ttl_out_of_policy_total_increase=0,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 6
