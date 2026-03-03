import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_crosslingual_query_bridge_guard.py"
    spec = importlib.util.spec_from_file_location("chat_crosslingual_query_bridge_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_crosslingual_query_bridge_guard_tracks_bridge_and_keyword_preservation():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "source_lang": "en",
            "target_lang": "ko",
            "bridge_applied": True,
            "rewrite_confidence": 0.95,
            "parallel_retrieval_enabled": True,
            "query": "order refund status",
            "pivot_query": "주문 환불 상태",
        },
        {
            "timestamp": "2026-03-04T00:00:05Z",
            "source_lang": "zh",
            "target_lang": "ko",
            "bridge_applied": False,
            "query": "배송 지연",
            "pivot_query": "",
        },
        {
            "timestamp": "2026-03-04T00:00:10Z",
            "source_lang": "ko",
            "target_lang": "ko",
            "bridge_applied": True,
            "rewrite_confidence": 0.40,
            "parallel_retrieval_enabled": False,
            "query": "배송 정책",
            "pivot_query": "정책 안내",
        },
    ]
    summary = module.summarize_crosslingual_query_bridge_guard(
        rows,
        low_confidence_threshold=0.6,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["query_total"] == 3
    assert summary["bridge_required_total"] == 2
    assert summary["bridge_applied_total"] == 2
    assert summary["bridge_applied_ratio"] == 1.0
    assert summary["parallel_retrieval_total"] == 1
    assert summary["parallel_retrieval_coverage_ratio"] == 0.5
    assert summary["low_confidence_bridge_total"] == 1
    assert summary["keyword_required_total"] == 2
    assert summary["keyword_preserved_total"] == 1
    assert summary["keyword_preservation_ratio"] == 0.5
    assert abs(summary["stale_minutes"] - (50.0 / 60.0)) < 1e-9


def test_evaluate_gate_detects_crosslingual_query_bridge_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "query_total": 1,
            "bridge_applied_ratio": 0.4,
            "parallel_retrieval_coverage_ratio": 0.3,
            "keyword_preservation_ratio": 0.2,
            "low_confidence_bridge_total": 3,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_query_total=2,
        min_bridge_applied_ratio=0.9,
        min_parallel_retrieval_coverage_ratio=0.9,
        min_keyword_preservation_ratio=0.9,
        max_low_confidence_bridge_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 7


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "query_total": 0,
            "bridge_applied_ratio": 1.0,
            "parallel_retrieval_coverage_ratio": 1.0,
            "keyword_preservation_ratio": 1.0,
            "low_confidence_bridge_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_query_total=0,
        min_bridge_applied_ratio=0.0,
        min_parallel_retrieval_coverage_ratio=0.0,
        min_keyword_preservation_ratio=0.0,
        max_low_confidence_bridge_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
