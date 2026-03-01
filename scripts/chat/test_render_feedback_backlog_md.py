import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "render_feedback_backlog_md.py"
    spec = importlib.util.spec_from_file_location("render_feedback_backlog_md", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_render_markdown_with_items():
    module = _load_module()
    payload = {
        "generated_at": "2026-03-01T10:00:00+00:00",
        "source": "evaluation/chat/feedback.jsonl",
        "total": 30,
        "thresholds": {"down_rate_threshold": 0.35},
        "items": [
            {
                "id": "chat.feedback.down_rate",
                "priority": "high",
                "title": "High chat dislike rate",
                "metric": "down_rate",
                "value": 0.4,
                "threshold": 0.35,
                "suggested_ticket": "B-0627",
                "owner": "chat-recommend",
            }
        ],
    }
    markdown = module.render_markdown(payload)
    assert "# Chat Feedback Backlog (Auto)" in markdown
    assert "High chat dislike rate" in markdown
    assert "suggested_ticket: `B-0627`" in markdown
    assert "value=0.4 threshold=0.35" in markdown


def test_render_markdown_without_items():
    module = _load_module()
    markdown = module.render_markdown({"items": []})
    assert "No backlog items generated." in markdown
