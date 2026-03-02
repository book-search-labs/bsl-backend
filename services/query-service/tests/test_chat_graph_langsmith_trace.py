import asyncio

from app.core.cache import CacheClient
from app.core.chat_graph import langsmith_trace


def _run(coro):
    return asyncio.run(coro)


def test_resolve_trace_decision_disabled_by_default(monkeypatch):
    monkeypatch.delenv("QS_CHAT_LANGSMITH_ENABLED", raising=False)
    monkeypatch.delenv("QS_CHAT_LANGSMITH_KILL_SWITCH", raising=False)

    decision = langsmith_trace.resolve_trace_decision(
        trace_id="trace_1",
        session_id="u:101:default",
        context={"tenant_id": "tenant-a", "channel": "web"},
    )
    assert decision.enabled is False
    assert decision.sampled is False
    assert decision.reason == "disabled"


def test_resolve_trace_decision_tenant_override(monkeypatch):
    monkeypatch.setenv("QS_CHAT_LANGSMITH_ENABLED", "1")
    monkeypatch.setenv("QS_CHAT_LANGSMITH_SAMPLE_RATE", "0.0")
    monkeypatch.setenv(
        "QS_CHAT_LANGSMITH_SAMPLE_OVERRIDES_JSON",
        '{"tenants":{"tenant-a":1.0},"channels":{"web":0.5}}',
    )

    decision = langsmith_trace.resolve_trace_decision(
        trace_id="trace_2",
        session_id="u:102:default",
        context={"tenant_id": "tenant-a", "channel": "web"},
    )
    assert decision.enabled is True
    assert decision.sampled is True
    assert decision.reason == "sample_all"


def test_redact_payload_hash_summary_masks_pii(monkeypatch):
    monkeypatch.setenv("QS_CHAT_LANGSMITH_REDACTION_MODE", "hash_summary")
    redacted = langsmith_trace.redact_payload(
        {
            "query": "email test@example.com, phone +82 10-1234-5678, card 4111 1111 1111 1111",
            "trace_id": "trace_x",
        }
    )
    query = redacted["query"]
    assert isinstance(query, dict)
    assert "hash" in query
    assert "summary" in query
    assert redacted["trace_id"] == "trace_x"


def test_emit_trace_event_skips_when_disabled(monkeypatch):
    langsmith_trace._CACHE = CacheClient(None)
    decision = langsmith_trace.TraceDecision(enabled=False, sampled=False, reason="disabled", sample_rate=0.0)

    result = _run(
        langsmith_trace.emit_trace_event(
            decision=decision,
            run_id="run_1",
            trace_id="trace_3",
            request_id="req_3",
            session_id="u:103:default",
            event_type="run_start",
            node=None,
            metadata={"trace_id": "trace_3", "request_id": "req_3", "session_id": "u:103:default"},
            payload={"query": "배송 상태 알려줘"},
        )
    )
    assert result.exported is False
    assert result.status == "skipped_disabled"
    rows = langsmith_trace.load_trace_audit("u:103:default")
    assert len(rows) == 1
    assert rows[0]["status"] == "skipped_disabled"


def test_emit_trace_event_exports_when_sampled(monkeypatch):
    langsmith_trace._CACHE = CacheClient(None)

    class _FakeResponse:
        status_code = 200
        content = b'{"id":"ls_run_1"}'

        @staticmethod
        def json():
            return {"id": "ls_run_1"}

    class _FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            return _FakeResponse()

    monkeypatch.setattr(langsmith_trace.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setenv("QS_CHAT_LANGSMITH_REDACTION_MODE", "masked_raw")
    monkeypatch.setenv("QS_CHAT_LANGSMITH_ENDPOINT", "https://example.com/runs")

    decision = langsmith_trace.TraceDecision(enabled=True, sampled=True, reason="sampled", sample_rate=1.0)
    result = _run(
        langsmith_trace.emit_trace_event(
            decision=decision,
            run_id="run_2",
            trace_id="trace_4",
            request_id="req_4",
            session_id="u:104:default",
            event_type="node",
            node="execute",
            metadata={"trace_id": "trace_4", "request_id": "req_4", "session_id": "u:104:default"},
            payload={"query": "주문 취소해줘"},
        )
    )
    assert result.exported is True
    assert result.status == "ok"
    rows = langsmith_trace.load_trace_audit("u:104:default")
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
