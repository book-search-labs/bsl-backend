from app.core.cache import CacheClient
from app.core.chat_graph import canary_controller, feature_router


def test_resolve_engine_mode_defaults_to_input_mode(monkeypatch):
    canary_controller._CACHE = CacheClient(None)
    monkeypatch.delenv("QS_CHAT_FORCE_LEGACY", raising=False)
    monkeypatch.delenv("QS_CHAT_OPENFEATURE_FLAGS_JSON", raising=False)

    decision = feature_router.resolve_engine_mode(
        default_mode="shadow",
        context={
            "tenant_id": "tenant-a",
            "user_id": "101",
            "session_id": "u:101:default",
            "channel": "web",
            "risk_band": "normal",
        },
    )

    assert decision.mode == "shadow"
    assert decision.reason == "ok"


def test_resolve_engine_mode_honors_force_legacy(monkeypatch):
    canary_controller._CACHE = CacheClient(None)
    monkeypatch.setenv("QS_CHAT_FORCE_LEGACY", "1")

    decision = feature_router.resolve_engine_mode(
        default_mode="agent",
        context={
            "tenant_id": "tenant-a",
            "user_id": "101",
            "session_id": "u:101:default",
            "channel": "web",
            "risk_band": "normal",
        },
    )

    assert decision.mode == "legacy"
    assert decision.force_legacy is True
    assert decision.reason == "force_legacy"


def test_resolve_engine_mode_applies_context_overrides(monkeypatch):
    canary_controller._CACHE = CacheClient(None)
    monkeypatch.delenv("QS_CHAT_FORCE_LEGACY", raising=False)
    monkeypatch.setenv(
        "QS_CHAT_OPENFEATURE_FLAGS_JSON",
        '{"defaults":{"chat.engine.mode":"legacy"},"tenants":{"tenant-b":{"chat.engine.mode":"agent"}}}',
    )

    decision = feature_router.resolve_engine_mode(
        default_mode="legacy",
        context={
            "tenant_id": "tenant-b",
            "user_id": "202",
            "session_id": "u:202:default",
            "channel": "web",
            "risk_band": "normal",
        },
    )

    assert decision.mode == "agent"


def test_resolve_engine_mode_falls_back_to_legacy_on_high_risk(monkeypatch):
    canary_controller._CACHE = CacheClient(None)
    monkeypatch.delenv("QS_CHAT_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("QS_CHAT_OPENFEATURE_FLAGS_JSON", '{"defaults":{"chat.engine.mode":"agent"}}')

    decision = feature_router.resolve_engine_mode(
        default_mode="agent",
        context={
            "tenant_id": "tenant-a",
            "user_id": "101",
            "session_id": "u:101:default",
            "channel": "web",
            "risk_band": "high",
        },
    )

    assert decision.mode == "legacy"
    assert decision.reason == "high_risk_fallback"


def test_routing_audit_append_and_load():
    canary_controller._CACHE = CacheClient(None)
    feature_router._CACHE = CacheClient(None)
    decision = feature_router.EngineRouteDecision(
        mode="legacy",
        reason="force_legacy",
        source="flag",
        force_legacy=True,
    )

    feature_router.append_routing_audit(
        "u:101:default",
        trace_id="trace_1",
        request_id="req_1",
        context={
            "tenant_id": "tenant-a",
            "user_id": "101",
            "session_id": "u:101:default",
            "channel": "web",
            "risk_band": "high",
        },
        decision=decision,
    )

    rows = feature_router.load_routing_audit("u:101:default")
    assert len(rows) == 1
    assert rows[0]["mode"] == "legacy"
    assert rows[0]["force_legacy"] is True
