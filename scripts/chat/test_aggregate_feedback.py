import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "aggregate_feedback.py"
    spec = importlib.util.spec_from_file_location("aggregate_feedback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_feedback_includes_rates_and_reason_counts():
    module = _load_module()
    records = [
        {"rating": "up", "flag_hallucination": False, "flag_insufficient": False},
        {"rating": "down", "reason_code": "recommend_low_diversity", "flag_hallucination": True},
        {"rating": "down", "reason_code": "recommend_low_diversity", "flag_insufficient": True},
        {"rating": "down", "reason_code": "policy_mismatch"},
    ]
    summary, reason_counts = module.summarize_feedback(records)
    assert summary["total"] == 4
    assert summary["rating_up"] == 1
    assert summary["rating_down"] == 3
    assert summary["down_rate"] == 0.75
    assert summary["hallucination"] == 1
    assert summary["insufficient"] == 1
    assert reason_counts["recommend_low_diversity"] == 2
    assert reason_counts["policy_mismatch"] == 1


def test_build_backlog_items_respects_thresholds():
    module = _load_module()
    summary = {
        "total": 30,
        "down_rate": 0.4,
        "hallucination_rate": 0.2,
        "insufficient_rate": 0.25,
    }
    reason_counts = {
        "recommend_low_diversity": 8,
        "policy_mismatch": 3,
    }
    items = module.build_backlog_items(
        summary,
        reason_counts,
        min_total_for_backlog=20,
        down_rate_threshold=0.35,
        hallucination_rate_threshold=0.12,
        insufficient_rate_threshold=0.2,
        top_reason_count_threshold=5,
    )
    item_ids = {item["id"] for item in items}
    assert "chat.feedback.down_rate" in item_ids
    assert "chat.feedback.hallucination_rate" in item_ids
    assert "chat.feedback.insufficient_rate" in item_ids
    assert "chat.feedback.reason.recommend_low_diversity" in item_ids
    assert "chat.feedback.reason.policy_mismatch" not in item_ids
