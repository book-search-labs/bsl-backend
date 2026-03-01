import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "sync_feedback_backlog_tickets.py"
    spec = importlib.util.spec_from_file_location("sync_feedback_backlog_tickets", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_ticket_filename_is_stable():
    module = _load_module()
    name = module._ticket_filename("chat.feedback.down_rate", "High chat dislike rate")
    assert name.startswith("chat-feedback-down-rate--high-chat-dislike-rate")
    assert name.endswith(".md")


def test_sync_tickets_writes_and_prunes(tmp_path):
    module = _load_module()
    payload = {
        "source": "evaluation/chat/feedback.jsonl",
        "generated_at": "2026-03-01T10:00:00+00:00",
        "items": [
            {
                "id": "chat.feedback.down_rate",
                "title": "High chat dislike rate",
                "priority": "high",
                "owner": "chat-recommend",
                "metric": "down_rate",
                "value": 0.4,
                "threshold": 0.35,
                "suggested_ticket": "B-0627",
            }
        ],
    }
    output_dir = tmp_path / "generated"
    stale = output_dir / "stale.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    stale.write_text("stale", encoding="utf-8")

    written, removed = module.sync_tickets(payload, output_dir=output_dir, prune=True)
    assert written >= 2
    assert removed == 1
    assert (output_dir / "_index.md").exists()
    ticket_files = [p for p in output_dir.glob("*.md") if p.name != "_index.md"]
    assert len(ticket_files) == 1
    content = ticket_files[0].read_text(encoding="utf-8")
    assert "AUTO-FEEDBACK" in content
    assert "B-0627" in content


def test_main_uses_input_json(tmp_path, monkeypatch):
    module = _load_module()
    input_path = tmp_path / "feedback_backlog.json"
    output_dir = tmp_path / "tickets"
    input_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "chat.feedback.reason.low_diversity",
                        "title": "Top dislike reason: low_diversity",
                        "metric": "reason_count",
                        "value": 8,
                        "threshold": 5,
                        "suggested_ticket": "B-0627",
                    }
                ]
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "sync_feedback_backlog_tickets.py",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    assert module.main() == 0
    assert (output_dir / "_index.md").exists()
