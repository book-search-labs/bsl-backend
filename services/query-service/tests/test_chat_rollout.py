import asyncio

from app.core import chat
from app.core.cache import CacheClient


def test_select_rollout_engine_canary_legacy_when_percent_zero(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ENGINE_MODE", "canary")
    monkeypatch.setenv("QS_CHAT_ENGINE_CANARY_PERCENT", "0")

    selection = chat._select_rollout_engine({"session_id": "s1", "client": {"user_id": "u1"}}, "req_1")

    assert selection["mode"] == "canary"
    assert selection["effective_engine"] == "legacy"


def test_select_rollout_engine_canary_agent_when_percent_hundred(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ENGINE_MODE", "canary")
    monkeypatch.setenv("QS_CHAT_ENGINE_CANARY_PERCENT", "100")

    selection = chat._select_rollout_engine({"session_id": "s1", "client": {"user_id": "u1"}}, "req_2")

    assert selection["effective_engine"] == "agent"


def test_select_rollout_engine_shadow(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ENGINE_MODE", "shadow")

    selection = chat._select_rollout_engine({"session_id": "s1"}, "req_shadow")

    assert selection["effective_engine"] == "legacy"
    assert selection["shadow_enabled"] is True


def test_record_rollout_gate_triggers_auto_rollback(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ROLLOUT_AUTO_ROLLBACK_ENABLED", "1")
    monkeypatch.setenv("QS_CHAT_ROLLOUT_GATE_MIN_SAMPLES", "2")
    monkeypatch.setenv("QS_CHAT_ROLLOUT_GATE_FAIL_RATIO_THRESHOLD", "0.4")
    monkeypatch.setenv("QS_CHAT_ROLLOUT_GATE_WINDOW_SEC", "120")
    monkeypatch.setenv("QS_CHAT_ROLLOUT_ROLLBACK_COOLDOWN_SEC", "120")

    failing = {"status": "error", "reason_code": "PROVIDER_TIMEOUT"}
    chat._record_rollout_gate("agent", failing)
    chat._record_rollout_gate("agent", failing)

    rollback = chat._get_active_rollout_rollback()
    assert rollback is not None
    assert rollback["reason"] == "gate_failure_ratio"


def test_get_chat_rollout_snapshot_includes_gate_and_config(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ENGINE_MODE", "canary")
    monkeypatch.setenv("QS_CHAT_ENGINE_CANARY_PERCENT", "7")
    chat._CACHE.set_json(
        chat._chat_rollout_gate_cache_key("agent"),
        {"window_start": 1760000000, "total": 9, "failures": 2, "fail_ratio": 0.2222, "updated_at": 1760000005},
        ttl=300,
    )

    snapshot = chat.get_chat_rollout_snapshot("trace_test", "req_snapshot")

    assert snapshot["mode"] == "canary"
    assert snapshot["canary_percent"] == 7
    assert snapshot["gates"]["agent"]["total"] == 9
    assert snapshot["gates"]["agent"]["failures"] == 2
    assert snapshot["trace_id"] == "trace_test"
    assert snapshot["request_id"] == "req_snapshot"


def test_reset_chat_rollout_state_clears_gate_and_rollback(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ROLLOUT_ROLLBACK_COOLDOWN_SEC", "120")
    chat._CACHE.set_json(
        chat._chat_rollout_gate_cache_key("agent"),
        {"window_start": 1760000000, "total": 11, "failures": 3, "fail_ratio": 0.2727},
        ttl=300,
    )
    chat._set_rollout_rollback("gate_failure_ratio", 0.6, 10, 6)

    reset = chat.reset_chat_rollout_state(
        "trace_test",
        "req_reset",
        clear_gate=True,
        clear_rollback=True,
        engine="agent",
        actor_admin_id="1",
    )

    assert reset["reset_applied"] is True
    assert reset["before"]["active_rollback"] is not None
    assert reset["before"]["gates"]["agent"]["total"] == 11
    assert reset["after"]["active_rollback"] is None
    assert reset["after"]["gates"]["agent"]["total"] == 0
    assert reset["options"]["cleared_gate_engines"] == ["agent"]


def test_run_chat_uses_legacy_engine_without_tools(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ENGINE_MODE", "legacy")
    captured = {}

    async def fake_impl(request, trace_id, request_id, *, allow_tools):
        captured["allow_tools"] = allow_tools
        return {"status": "ok", "reason_code": "OK"}

    monkeypatch.setattr(chat, "_run_chat_impl", fake_impl)
    monkeypatch.setattr(chat, "_record_rollout_gate", lambda engine, response: None)

    response = asyncio.run(chat.run_chat({"message": {"role": "user", "content": "안녕"}}, "trace_test", "req_test"))

    assert response["status"] == "ok"
    assert captured["allow_tools"] is False


def test_run_chat_uses_agent_engine_with_tools(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ENGINE_MODE", "agent")
    captured = {}

    async def fake_impl(request, trace_id, request_id, *, allow_tools):
        captured["allow_tools"] = allow_tools
        return {"status": "ok", "reason_code": "OK"}

    monkeypatch.setattr(chat, "_run_chat_impl", fake_impl)
    monkeypatch.setattr(chat, "_record_rollout_gate", lambda engine, response: None)

    response = asyncio.run(chat.run_chat({"message": {"role": "user", "content": "안녕"}}, "trace_test", "req_test"))

    assert response["status"] == "ok"
    assert captured["allow_tools"] is True


def test_run_chat_shadow_records_diff_metric(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ENGINE_MODE", "shadow")

    async def fake_impl(request, trace_id, request_id, *, allow_tools):
        assert allow_tools is False
        return {"status": "ok", "reason_code": "OK"}

    async def fake_shadow(request, trace_id, request_id):
        return {"status": "fallback", "reason_code": "RAG_NO_CHUNKS"}

    monkeypatch.setattr(chat, "_run_chat_impl", fake_impl)
    monkeypatch.setattr(chat, "_shadow_agent_signature", fake_shadow)
    monkeypatch.setattr(chat, "_record_rollout_gate", lambda engine, response: None)
    before = dict(chat.metrics.snapshot())

    asyncio.run(chat.run_chat({"message": {"role": "user", "content": "안녕"}}, "trace_test", "req_shadow"))

    after = chat.metrics.snapshot()
    key = "chat_rollout_shadow_diff_total{result=diff}"
    assert after.get(key, 0) >= before.get(key, 0) + 1


def test_run_chat_stream_uses_engine_selection(monkeypatch):
    chat._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_ENGINE_MODE", "legacy")
    captured = {}

    async def fake_stream_impl(request, trace_id, request_id, *, allow_tools):
        captured["allow_tools"] = allow_tools
        yield "event: done\ndata: {\"status\":\"ok\"}\n\n"

    monkeypatch.setattr(chat, "_run_chat_stream_impl", fake_stream_impl)

    async def _collect():
        items = []
        async for item in chat.run_chat_stream({"message": {"role": "user", "content": "안녕"}}, "trace_test", "req_stream"):
            items.append(item)
        return items

    events = asyncio.run(_collect())
    assert captured["allow_tools"] is False
    assert len(events) == 1
