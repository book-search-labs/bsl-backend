import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_trust_rerank_integration.py"
    spec = importlib.util.spec_from_file_location("chat_trust_rerank_integration", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_trust_rerank_reduces_low_trust_topk_ratio():
    module = _load_module()
    rows = [
        {
            "query_id": "q1",
            "source_type": "USER_GENERATED",
            "retrieval_score": 0.95,
            "trust_weight": 0.2,
            "freshness_ttl_sec": 86400,
            "updated_at": "2026-03-03T00:00:00Z",
        },
        {
            "query_id": "q1",
            "source_type": "OFFICIAL_POLICY",
            "retrieval_score": 0.90,
            "trust_weight": 1.0,
            "freshness_ttl_sec": 86400,
            "updated_at": "2026-03-03T00:00:00Z",
        },
        {
            "query_id": "q1",
            "source_type": "ANNOUNCEMENT",
            "retrieval_score": 0.88,
            "trust_weight": 0.7,
            "freshness_ttl_sec": 86400,
            "updated_at": "2026-03-03T00:00:00Z",
        },
    ]
    summary = module.summarize_trust_rerank(
        rows,
        top_k=1,
        low_trust_threshold=0.5,
        trust_boost_scale=0.3,
        stale_penalty=0.5,
        default_freshness_ttl_sec=86400,
        now=datetime(2026, 3, 3, 0, 10, tzinfo=timezone.utc),
    )
    assert summary["query_total"] == 1
    assert summary["low_trust_topk_before_ratio"] == 1.0
    assert summary["low_trust_topk_after_ratio"] == 0.0
    assert summary["trust_lift_ratio"] == 1.0


def test_evaluate_gate_detects_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 10,
            "query_total": 10,
            "low_trust_topk_after_ratio": 0.80,
            "stale_topk_after_ratio": 0.50,
            "trust_lift_ratio": 0.10,
            "stale_drop_ratio": 0.05,
            "stale_minutes": 120.0,
        },
        min_window=1,
        min_query_total=1,
        max_low_trust_topk_ratio=0.40,
        max_stale_topk_ratio=0.20,
        min_trust_lift_ratio=0.30,
        min_stale_drop_ratio=0.20,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 5


def test_evaluate_gate_allows_empty_window_with_zero_min():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "query_total": 0,
            "low_trust_topk_after_ratio": 0.0,
            "stale_topk_after_ratio": 0.0,
            "trust_lift_ratio": 0.0,
            "stale_drop_ratio": 0.0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_query_total=0,
        max_low_trust_topk_ratio=0.4,
        max_stale_topk_ratio=0.2,
        min_trust_lift_ratio=0.0,
        min_stale_drop_ratio=0.0,
        max_stale_minutes=60.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_trust_rerank_regressions():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "low_trust_topk_after_ratio": 0.1,
                "stale_topk_after_ratio": 0.1,
                "trust_lift_ratio": 0.5,
                "stale_drop_ratio": 0.5,
                "stale_minutes": 5.0,
            }
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "low_trust_topk_after_ratio": 0.3,
            "stale_topk_after_ratio": 0.3,
            "trust_lift_ratio": 0.2,
            "stale_drop_ratio": 0.2,
            "stale_minutes": 40.0,
        },
        max_low_trust_topk_after_ratio_increase=0.05,
        max_stale_topk_after_ratio_increase=0.05,
        max_trust_lift_ratio_drop=0.10,
        max_stale_drop_ratio_drop=0.10,
        max_stale_minutes_increase=10.0,
    )
    assert len(failures) == 5
