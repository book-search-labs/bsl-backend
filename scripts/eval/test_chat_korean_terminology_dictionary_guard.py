import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_korean_terminology_dictionary_guard.py"
    spec = importlib.util.spec_from_file_location("chat_korean_terminology_dictionary_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_korean_terminology_dictionary_guard_tracks_dictionary_and_term_violations():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "terminology_dictionary_version": "dict-v3",
            "term_normalization_applied": True,
            "synonym_normalization_applied": True,
            "banned_term_hits": [],
            "preferred_term_misses": [],
        },
        {
            "timestamp": "2026-03-03T00:00:20Z",
            "terminology_dictionary_version": "",
            "term_replacements": ["배송비->배송 비용"],
            "banned_term_hits": ["무료배송보장"],
            "preferred_term_misses": ["전자책"],
            "term_conflicts": ["환불/교환"],
        },
    ]

    summary = module.summarize_korean_terminology_dictionary_guard(
        rows,
        now=datetime(2026, 3, 3, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 2
    assert summary["response_total"] == 2
    assert summary["dictionary_version_missing_total"] == 1
    assert summary["dictionary_version_presence_ratio"] == 0.5
    assert summary["banned_term_violation_total"] == 1
    assert summary["preferred_term_miss_total"] == 1
    assert summary["synonym_normalization_applied_total"] == 1
    assert summary["terminology_normalization_applied_total"] == 2
    assert summary["normalization_ratio"] == 1.0
    assert summary["conflict_term_total"] == 1
    assert abs(summary["stale_minutes"] - (2.0 / 3.0)) < 1e-9


def test_evaluate_gate_detects_korean_terminology_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "response_total": 1,
            "dictionary_version_presence_ratio": 0.4,
            "normalization_ratio": 0.2,
            "banned_term_violation_total": 3,
            "preferred_term_miss_total": 2,
            "conflict_term_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_response_total=2,
        min_dictionary_version_presence_ratio=0.95,
        min_normalization_ratio=0.9,
        max_banned_term_violation_total=0,
        max_preferred_term_miss_total=0,
        max_conflict_term_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 8


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "response_total": 0,
            "dictionary_version_presence_ratio": 1.0,
            "normalization_ratio": 1.0,
            "banned_term_violation_total": 0,
            "preferred_term_miss_total": 0,
            "conflict_term_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_response_total=0,
        min_dictionary_version_presence_ratio=0.0,
        min_normalization_ratio=0.0,
        max_banned_term_violation_total=1000000,
        max_preferred_term_miss_total=1000000,
        max_conflict_term_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
