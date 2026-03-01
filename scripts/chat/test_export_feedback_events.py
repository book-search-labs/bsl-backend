import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "export_feedback_events.py"
    spec = importlib.util.spec_from_file_location("export_feedback_events", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_parse_payload_accepts_dict_and_json_text():
    module = _load_module()
    payload = {"rating": "up"}
    assert module.parse_payload(payload) == payload
    assert module.parse_payload('{"rating":"down"}') == {"rating": "down"}
    assert module.parse_payload("not-json") == {}


def test_normalize_feedback_record_masks_comment_by_default():
    module = _load_module()
    row = {
        "event_id": 11,
        "status": "SENT",
        "created_at": "2026-03-01 10:00:00",
        "payload_json": {
            "version": "v1",
            "trace_id": "trace_1",
            "request_id": "req_1",
            "session_id": "u:101:default",
            "message_id": "msg-1",
            "rating": "down",
            "reason_code": "recommend_low_diversity",
            "comment": "책 추천이 너무 비슷해요",
            "flag_hallucination": False,
            "flag_insufficient": False,
            "actor_user_id": "101",
            "auth_mode": "user",
            "event_time": "2026-03-01T01:00:00Z",
        },
    }
    normalized = module.normalize_feedback_record(row, include_comment=False)
    assert normalized["rating"] == "down"
    assert normalized["comment_hash"]
    assert "comment" not in normalized
    assert normalized["outbox_event_id"] == 11
    assert normalized["auth_mode"] == "user"


def test_normalize_feedback_record_can_include_comment():
    module = _load_module()
    row = {
        "event_id": 12,
        "status": "NEW",
        "created_at": "2026-03-01 11:00:00",
        "payload_json": {
            "session_id": "conv-1",
            "rating": "up",
            "comment": "좋아요",
        },
    }
    normalized = module.normalize_feedback_record(row, include_comment=True)
    assert normalized["comment"] == "좋아요"
    assert "comment_hash" not in normalized


def test_main_writes_empty_file_when_no_rows(tmp_path, monkeypatch):
    module = _load_module()
    output_path = tmp_path / "feedback.jsonl"

    class _DummyConn:
        def close(self):
            return None

    monkeypatch.setattr(module, "connect_mysql", lambda: _DummyConn())
    monkeypatch.setattr(module, "fetch_feedback_rows", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "sys.argv",
        [
            "export_feedback_events.py",
            "--output",
            str(output_path),
            "--days",
            "1",
        ],
    )

    assert module.main() == 0
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == ""


def test_main_writes_jsonl_rows(tmp_path, monkeypatch):
    module = _load_module()
    output_path = tmp_path / "feedback.jsonl"
    rows = [
        {
            "event_id": 1,
            "status": "SENT",
            "created_at": "2026-03-01 10:00:00",
            "payload_json": {"session_id": "u:101:default", "rating": "down", "comment": "너무 비슷함"},
        }
    ]

    class _DummyConn:
        def close(self):
            return None

    monkeypatch.setattr(module, "connect_mysql", lambda: _DummyConn())
    monkeypatch.setattr(module, "fetch_feedback_rows", lambda *args, **kwargs: rows)
    monkeypatch.setattr(
        "sys.argv",
        [
            "export_feedback_events.py",
            "--output",
            str(output_path),
            "--days",
            "1",
        ],
    )

    assert module.main() == 0
    lines = [line for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["session_id"] == "u:101:default"
    assert record["rating"] == "down"
    assert "comment_hash" in record
