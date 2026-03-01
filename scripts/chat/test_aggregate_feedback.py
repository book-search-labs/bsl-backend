import importlib.util
import json
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


def test_build_empty_summary_returns_zero_baseline():
    module = _load_module()
    summary = module.build_empty_summary()
    assert summary["total"] == 0
    assert summary["rating_up"] == 0
    assert summary["rating_down"] == 0
    assert summary["down_rate"] == 0.0
    assert summary["reason_counts"] == {}


def test_main_allow_empty_writes_summary_and_backlog(tmp_path, monkeypatch):
    module = _load_module()
    input_path = tmp_path / "feedback.jsonl"
    output_path = tmp_path / "feedback_summary.json"
    backlog_path = tmp_path / "feedback_backlog.json"
    input_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "aggregate_feedback.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--backlog-output",
            str(backlog_path),
            "--allow-empty",
        ],
    )

    assert module.main() == 0
    summary = json.loads(output_path.read_text(encoding="utf-8"))
    backlog = json.loads(backlog_path.read_text(encoding="utf-8"))
    assert summary["total"] == 0
    assert summary["reason_counts"] == {}
    assert backlog["total"] == 0
    assert backlog["items"] == []
    assert backlog["source"] == str(input_path)


def test_main_without_allow_empty_returns_failure_on_empty_input(tmp_path, monkeypatch):
    module = _load_module()
    input_path = tmp_path / "feedback.jsonl"
    output_path = tmp_path / "feedback_summary.json"
    input_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "aggregate_feedback.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )

    assert module.main() == 1
    assert not output_path.exists()
