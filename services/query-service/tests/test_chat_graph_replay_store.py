import asyncio

from app.core.chat_graph.replay_store import (
    load_replay,
    load_run,
    resolve_run_id,
    response_diff,
    save_replay,
)
from app.core.chat_graph.runtime import run_chat_graph


def _run(coro):
    return asyncio.run(coro)


def _ok_response(trace_id: str, request_id: str) -> dict:
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "ok",
        "reason_code": "OK",
        "recoverable": False,
        "next_action": "NONE",
        "retry_after_ms": None,
        "answer": {"role": "assistant", "content": "ok"},
        "sources": [],
        "citations": [],
        "fallback_count": 0,
        "escalated": False,
    }


def test_run_chat_graph_records_checkpoints_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("QS_CHAT_GRAPH_REPLAY_DIR", str(tmp_path))

    async def fake_legacy_executor(request, trace_id, request_id):
        return _ok_response(trace_id, request_id)

    result = _run(
        run_chat_graph(
            {
                "session_id": "u:801:default",
                "message": {"role": "user", "content": "배송 상태 알려줘"},
            },
            "trace_rec",
            "req_rec",
            legacy_executor=fake_legacy_executor,
            run_id="run_test_record",
            record_run=True,
        )
    )

    assert result.response["status"] == "ok"
    run = load_run("run_test_record")
    assert isinstance(run, dict)
    assert run["status"] == "done"
    assert isinstance(run.get("checkpoints"), list)
    assert len(run["checkpoints"]) >= 7
    assert resolve_run_id("req_rec") == "run_test_record"


def test_replay_store_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setenv("QS_CHAT_GRAPH_REPLAY_DIR", str(tmp_path))

    original = _ok_response("trace_o", "req_o")
    replayed = dict(original)
    replayed["reason_code"] = "PROVIDER_TIMEOUT"
    diff = response_diff(original, replayed)
    assert diff["matched"] is False

    save_replay(
        "replay_test_1",
        run_id="run_x",
        request_payload={"message": {"role": "user", "content": "x"}},
        replay_response=replayed,
        original_response=original,
        diff=diff,
        success=False,
    )

    replay = load_replay("replay_test_1")
    assert isinstance(replay, dict)
    assert replay["status"] == "mismatch"
    assert replay["diff"]["matched"] is False
