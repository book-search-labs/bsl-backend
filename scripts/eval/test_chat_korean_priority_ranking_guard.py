import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_korean_priority_ranking_guard.py"
    spec = importlib.util.spec_from_file_location("chat_korean_priority_ranking_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_korean_priority_ranking_guard_tracks_priority_violations():
    module = _load_module()
    rows = [
        {"timestamp": "2026-03-04T00:00:00Z", "query_id": "q1", "rank": 1, "doc_lang": "ko", "korean_priority_boost_applied": True},
        {"timestamp": "2026-03-04T00:00:00Z", "query_id": "q1", "rank": 2, "doc_lang": "en", "korean_priority_boost_applied": False},
        {"timestamp": "2026-03-04T00:00:10Z", "query_id": "q2", "rank": 1, "doc_lang": "en", "korean_priority_boost_applied": False},
        {"timestamp": "2026-03-04T00:00:10Z", "query_id": "q2", "rank": 2, "doc_lang": "ko", "korean_priority_boost_applied": False},
        {"timestamp": "2026-03-04T00:00:20Z", "query_id": "q3", "rank": 1, "doc_lang": "en", "korean_priority_boost_applied": False},
    ]

    summary = module.summarize_korean_priority_ranking_guard(
        rows,
        top_k=3,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["query_total"] == 3
    assert summary["korean_candidate_query_total"] == 2
    assert summary["korean_top1_total"] == 1
    assert summary["korean_top1_ratio"] == 0.5
    assert summary["korean_topk_covered_total"] == 2
    assert summary["korean_topk_coverage_ratio"] == 1.0
    assert summary["priority_boost_applied_total"] == 1
    assert summary["priority_boost_applied_ratio"] == 0.5
    assert summary["non_korean_top1_when_korean_available_total"] == 1
    assert abs(summary["stale_minutes"] - (40.0 / 60.0)) < 1e-9


def test_evaluate_gate_detects_korean_priority_ranking_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "query_total": 1,
            "korean_top1_ratio": 0.4,
            "korean_topk_coverage_ratio": 0.3,
            "priority_boost_applied_ratio": 0.2,
            "non_korean_top1_when_korean_available_total": 3,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_query_total=2,
        min_korean_top1_ratio=0.9,
        min_korean_topk_coverage_ratio=0.9,
        min_priority_boost_applied_ratio=0.9,
        max_non_korean_top1_when_korean_available_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "query_total": 0,
            "korean_top1_ratio": 1.0,
            "korean_topk_coverage_ratio": 1.0,
            "priority_boost_applied_ratio": 1.0,
            "non_korean_top1_when_korean_available_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_query_total=0,
        min_korean_top1_ratio=0.0,
        min_korean_topk_coverage_ratio=0.0,
        min_priority_boost_applied_ratio=0.0,
        max_non_korean_top1_when_korean_available_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
