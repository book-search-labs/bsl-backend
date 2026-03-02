from app.core.cache import CacheClient
from app.core.chat_graph import canary_controller, feature_router


def test_evaluate_canary_gate_blocks_when_blocker_ratio_high(monkeypatch):
    monkeypatch.setenv("QS_CHAT_CANARY_BLOCKER_THRESHOLD", "0.02")
    decision = canary_controller.evaluate_canary_gate(
        {
            "blocker_ratio": 0.05,
            "mismatch_ratio": 0.04,
        }
    )

    assert decision.passed is False
    assert decision.gate_status == "BLOCK"
    assert decision.reason == "blocker_ratio_exceeded"


def test_apply_auto_rollback_sets_force_legacy_override(monkeypatch):
    canary_controller._CACHE = CacheClient(None)

    decision = canary_controller.CanaryGateDecision(
        passed=False,
        gate_status="BLOCK",
        reason="blocker_ratio_exceeded",
        blocker_ratio=0.2,
        mismatch_ratio=0.3,
    )
    result = canary_controller.apply_auto_rollback(
        decision,
        trace_id="trace_1",
        request_id="req_1",
        source="unit_test",
    )

    assert result.applied is True
    override = canary_controller.current_force_legacy_override()
    assert isinstance(override, dict)
    assert override["enabled"] is True


def test_apply_auto_rollback_releases_override_after_cooldown(monkeypatch):
    canary_controller._CACHE = CacheClient(None)

    canary_controller._CACHE.set_json(
        "chat:graph:force-legacy:override",
        {
            "enabled": True,
            "set_at": 1,
            "cooldown_until": 1,
            "reason": "old",
            "gate_status": "BLOCK",
            "blocker_ratio": 0.2,
            "mismatch_ratio": 0.2,
        },
        ttl=600,
    )

    decision = canary_controller.CanaryGateDecision(
        passed=True,
        gate_status="PASS",
        reason="within_threshold",
        blocker_ratio=0.0,
        mismatch_ratio=0.0,
    )
    result = canary_controller.apply_auto_rollback(
        decision,
        trace_id="trace_2",
        request_id="req_2",
        source="unit_test",
    )

    assert result.reason in {"released", "noop"}


def test_feature_router_honors_canary_override(monkeypatch):
    canary_controller._CACHE = CacheClient(None)
    feature_router._CACHE = CacheClient(None)

    decision = canary_controller.CanaryGateDecision(
        passed=False,
        gate_status="BLOCK",
        reason="blocker_ratio_exceeded",
        blocker_ratio=0.3,
        mismatch_ratio=0.4,
    )
    canary_controller.apply_auto_rollback(
        decision,
        trace_id="trace_3",
        request_id="req_3",
        source="unit_test",
    )

    routed = feature_router.resolve_engine_mode(
        default_mode="agent",
        context={
            "tenant_id": "tenant-a",
            "user_id": "101",
            "session_id": "u:101:default",
            "channel": "web",
            "risk_band": "normal",
        },
    )

    assert routed.mode == "legacy"
    assert routed.reason == "auto_rollback_override"
