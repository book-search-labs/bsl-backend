from fastapi.testclient import TestClient

from app.main import app
from app.api import routes


def test_chat_route_injects_auth_identity_into_client_payload(monkeypatch):
    captured = {}

    async def fake_run_chat(body, trace_id, request_id):
        captured["body"] = body
        return {
            "version": "v1",
            "trace_id": trace_id,
            "request_id": request_id,
            "status": "ok",
            "answer": {"role": "assistant", "content": "ok"},
            "sources": [],
            "citations": [],
        }

    monkeypatch.setattr(routes, "run_chat", fake_run_chat)

    client = TestClient(app)
    response = client.post(
        "/chat",
        headers={"x-user-id": "101", "x-admin-id": "42"},
        json={"message": {"role": "user", "content": "배송 상태"}},
    )

    assert response.status_code == 200
    assert captured["body"]["client"]["user_id"] == "101"
    assert captured["body"]["client"]["admin_id"] == "42"


def test_chat_route_rejects_invalid_json_body():
    client = TestClient(app)
    response = client.post(
        "/chat",
        data="{invalid",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"


def test_rag_explain_route_rejects_invalid_json_body():
    client = TestClient(app)
    response = client.post(
        "/internal/rag/explain",
        data="{invalid",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"


def test_chat_provider_snapshot_route_returns_payload(monkeypatch):
    async_payload = {
        "routing": {"final_chain": ["primary", "fallback_1"]},
        "providers": [{"name": "primary", "url": "http://llm-primary", "cooldown": False, "stats": {}}],
        "config": {"forced_provider": None},
    }

    def fake_snapshot(trace_id, request_id):
        return async_payload

    monkeypatch.setattr(routes, "get_chat_provider_snapshot", fake_snapshot)

    client = TestClient(app)
    response = client.get("/internal/chat/providers")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["snapshot"]["routing"]["final_chain"][0] == "primary"


def test_chat_rollout_snapshot_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_chat_rollout_snapshot",
        lambda trace_id, request_id: {
            "mode": "canary",
            "canary_percent": 5,
            "auto_rollback_enabled": True,
            "gate_window_sec": 300,
            "gate_min_samples": 20,
            "gate_fail_ratio_threshold": 0.2,
            "rollback_cooldown_sec": 60,
            "active_rollback": None,
            "gates": {
                "agent": {"engine": "agent", "total": 10, "failures": 1, "fail_ratio": 0.1},
                "legacy": {"engine": "legacy", "total": 5, "failures": 0, "fail_ratio": 0.0},
            },
            "trace_id": trace_id,
            "request_id": request_id,
        },
    )

    client = TestClient(app)
    response = client.get("/internal/chat/rollout")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["rollout"]["mode"] == "canary"
    assert data["rollout"]["gates"]["agent"]["total"] == 10


def test_chat_rollout_reset_route_returns_payload(monkeypatch):
    captured = {}

    def fake_reset_chat_rollout_state(
        trace_id,
        request_id,
        *,
        clear_gate=True,
        clear_rollback=True,
        engine=None,
        actor_admin_id=None,
    ):
        captured["clear_gate"] = clear_gate
        captured["clear_rollback"] = clear_rollback
        captured["engine"] = engine
        captured["actor_admin_id"] = actor_admin_id
        return {
            "reset_applied": True,
            "reset_at_ms": 1760000300000,
            "before": {"mode": "canary"},
            "after": {"mode": "canary"},
            "options": {"clear_gate": clear_gate, "clear_rollback": clear_rollback, "engine": engine},
        }

    monkeypatch.setattr(routes, "reset_chat_rollout_state", fake_reset_chat_rollout_state)

    client = TestClient(app)
    response = client.post(
        "/internal/chat/rollout/reset",
        headers={"x-admin-id": "1"},
        json={"clear_gate": True, "clear_rollback": False, "engine": "agent"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["reset"]["reset_applied"] is True
    assert captured["clear_gate"] is True
    assert captured["clear_rollback"] is False
    assert captured["engine"] == "agent"
    assert captured["actor_admin_id"] == "1"


def test_chat_rollout_reset_route_rejects_invalid_engine():
    client = TestClient(app)
    response = client.post("/internal/chat/rollout/reset", json={"engine": 1})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"


def test_chat_rollout_reset_route_rejects_invalid_engine_value(monkeypatch):
    def fake_reset_chat_rollout_state(
        trace_id,
        request_id,
        *,
        clear_gate=True,
        clear_rollback=True,
        engine=None,
        actor_admin_id=None,
    ):
        raise ValueError("invalid_engine")

    monkeypatch.setattr(routes, "reset_chat_rollout_state", fake_reset_chat_rollout_state)
    client = TestClient(app)
    response = client.post("/internal/chat/rollout/reset", json={"engine": "unknown"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"


def test_chat_recommend_experiment_snapshot_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_recommend_experiment_snapshot",
        lambda: {
            "enabled": True,
            "auto_disabled": False,
            "disabled_until": None,
            "disable_reason": None,
            "total": 12,
            "blocked": 2,
            "block_rate": 0.16,
            "min_samples": 20,
            "max_block_rate": 0.4,
        },
    )

    client = TestClient(app)
    response = client.get("/internal/chat/recommend/experiment")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["experiment"]["enabled"] is True
    assert data["experiment"]["blocked"] == 2


def test_chat_recommend_experiment_reset_route_returns_payload(monkeypatch):
    captured = {}

    def fake_reset_recommend_experiment_state(*, overrides=None, clear_overrides=False):
        captured["overrides"] = overrides
        captured["clear_overrides"] = clear_overrides
        return {
            "reset_applied": True,
            "reset_at_ms": 1760000100000,
            "before": {"enabled": True, "total": 15, "blocked": 8, "block_rate": 0.53},
            "after": {"enabled": True, "total": 0, "blocked": 0, "block_rate": 0.0},
            "override": None,
        }

    monkeypatch.setattr(
        routes,
        "reset_recommend_experiment_state",
        fake_reset_recommend_experiment_state,
    )

    client = TestClient(app)
    response = client.post("/internal/chat/recommend/experiment/reset", json={})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["reset"]["reset_applied"] is True
    assert data["reset"]["before"]["total"] == 15
    assert data["reset"]["after"]["total"] == 0
    assert captured["overrides"] is None
    assert captured["clear_overrides"] is False


def test_chat_recommend_experiment_reset_route_accepts_overrides(monkeypatch):
    captured = {}

    def fake_reset_recommend_experiment_state(*, overrides=None, clear_overrides=False):
        captured["overrides"] = overrides
        captured["clear_overrides"] = clear_overrides
        return {
            "reset_applied": True,
            "reset_at_ms": 1760000100000,
            "before": {"enabled": True, "total": 4, "blocked": 1, "block_rate": 0.25},
            "after": {"enabled": True, "total": 0, "blocked": 0, "block_rate": 0.0},
            "override": {"overrides": overrides or {}},
        }

    monkeypatch.setattr(routes, "reset_recommend_experiment_state", fake_reset_recommend_experiment_state)

    client = TestClient(app)
    response = client.post(
        "/internal/chat/recommend/experiment/reset",
        json={
            "clear_overrides": True,
            "overrides": {
                "enabled": True,
                "diversity_percent": 70,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["reset"]["override"]["overrides"]["diversity_percent"] == 70
    assert captured["clear_overrides"] is True
    assert captured["overrides"]["enabled"] is True


def test_chat_recommend_experiment_reset_route_rejects_invalid_overrides():
    client = TestClient(app)
    response = client.post("/internal/chat/recommend/experiment/reset", json={"overrides": "bad"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"


def test_chat_recommend_experiment_reset_route_rejects_invalid_clear_overrides():
    client = TestClient(app)
    response = client.post("/internal/chat/recommend/experiment/reset", json={"clear_overrides": "yes"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"


def test_chat_recommend_experiment_reset_route_rejects_invalid_override_value(monkeypatch):
    def fake_reset_recommend_experiment_state(*, overrides=None, clear_overrides=False):
        raise ValueError("override.max_block_rate must be between 0 and 1")

    monkeypatch.setattr(routes, "reset_recommend_experiment_state", fake_reset_recommend_experiment_state)

    client = TestClient(app)
    response = client.post(
        "/internal/chat/recommend/experiment/reset",
        json={"overrides": {"max_block_rate": 1.5}},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert "max_block_rate" in payload["error"]["message"]


def test_chat_recommend_experiment_config_route_returns_payload(monkeypatch):
    captured = {}

    def fake_update_recommend_experiment_config_overrides(overrides, *, clear=False):
        captured["overrides"] = overrides
        captured["clear"] = clear
        return {"updated_at": 1760000200, "ttl_sec": 604800, "overrides": {"enabled": True, "diversity_percent": 70}}

    monkeypatch.setattr(routes, "update_recommend_experiment_config_overrides", fake_update_recommend_experiment_config_overrides)
    monkeypatch.setattr(
        routes,
        "get_recommend_experiment_snapshot",
        lambda: {
            "enabled": True,
            "auto_disabled": False,
            "disabled_until": None,
            "disable_reason": None,
            "total": 12,
            "blocked": 2,
            "block_rate": 0.16,
            "min_samples": 20,
            "max_block_rate": 0.4,
            "diversity_percent": 70,
            "auto_disable_sec": 600,
            "quality_min_candidates": 2,
            "quality_min_diversity": 2,
            "config_overrides": {"enabled": True, "diversity_percent": 70},
        },
    )

    client = TestClient(app)
    response = client.post(
        "/internal/chat/recommend/experiment/config",
        json={"clear_overrides": True, "overrides": {"enabled": True, "diversity_percent": 70}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["config_update"]["overrides"]["diversity_percent"] == 70
    assert data["experiment"]["config_overrides"]["enabled"] is True
    assert captured["clear"] is True
    assert captured["overrides"]["diversity_percent"] == 70


def test_chat_recommend_experiment_config_route_requires_patch_payload():
    client = TestClient(app)
    response = client.post("/internal/chat/recommend/experiment/config", json={})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"


def test_chat_recommend_experiment_config_route_rejects_invalid_overrides():
    client = TestClient(app)
    response = client.post("/internal/chat/recommend/experiment/config", json={"overrides": "bad"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"


def test_chat_recommend_experiment_config_route_rejects_invalid_override_value(monkeypatch):
    def fake_update_recommend_experiment_config_overrides(overrides, *, clear=False):
        raise ValueError("override.max_block_rate must be between 0 and 1")

    monkeypatch.setattr(routes, "update_recommend_experiment_config_overrides", fake_update_recommend_experiment_config_overrides)

    client = TestClient(app)
    response = client.post(
        "/internal/chat/recommend/experiment/config",
        json={"overrides": {"max_block_rate": 1.5}},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert "max_block_rate" in payload["error"]["message"]


def test_chat_session_state_route_returns_payload(monkeypatch):
    captured = []

    def fake_inc(name, labels=None):
        captured.append((name, labels or {}))

    def fake_session_state(session_id, trace_id, request_id):
        assert session_id == "u:101:default"
        return {
            "session_id": session_id,
            "fallback_count": 2,
            "fallback_escalation_threshold": 3,
            "escalation_ready": False,
            "recommended_action": "RETRY",
            "recommended_message": "생성된 답변과 근거 문서가 일치하지 않아 답변을 보류했습니다. 잠시 후 다시 시도해 주세요.",
            "unresolved_context": {
                "reason_code": "LLM_NO_CITATIONS",
                "reason_message": "생성된 답변과 근거 문서가 일치하지 않아 답변을 보류했습니다. 잠시 후 다시 시도해 주세요.",
                "next_action": "RETRY",
                "trace_id": "trace_prev",
                "request_id": "req_prev",
                "updated_at": 1760000000,
                "query_preview": "환불 조건 문의",
            },
            "selection_snapshot": {
                "type": "BOOK_RECOMMENDATION",
                "candidates_count": 3,
                "selected_index": 2,
                "selected_title": "도서 B",
            },
            "pending_action_snapshot": {
                "type": "REFUND_REQUEST",
                "state": "AWAITING_CONFIRMATION",
                "expires_at": 1760001234,
            },
            "llm_call_budget": {
                "count": 2,
                "limit": 5,
                "limited": False,
                "window_sec": 60,
                "window_start": 1760000000,
            },
            "semantic_cache": {
                "enabled": True,
                "auto_disabled": False,
                "disabled_until": None,
                "disable_reason": None,
                "similarity_threshold": 0.82,
                "drift_total": 4,
                "drift_errors": 0,
                "drift_error_rate": 0.0,
                "drift_max_error_rate": 0.2,
            },
            "episode_memory": {
                "enabled": True,
                "opt_in": True,
                "count": 2,
                "items": ["전자책 선호", "입문서 선호"],
            },
            "recommend_experiment": {
                "enabled": True,
                "auto_disabled": False,
                "disabled_until": None,
                "disable_reason": None,
                "total": 12,
                "blocked": 3,
                "block_rate": 0.25,
                "min_samples": 20,
                "max_block_rate": 0.4,
                "diversity_percent": 70,
                "auto_disable_sec": 600,
                "quality_min_candidates": 2,
                "quality_min_diversity": 2,
                "config_overrides": {"enabled": True, "diversity_percent": 70},
            },
            "trace_id": trace_id,
            "request_id": request_id,
        }

    monkeypatch.setattr(routes.metrics, "inc", fake_inc)
    monkeypatch.setattr(routes, "get_chat_session_state", fake_session_state)

    client = TestClient(app)
    response = client.get("/internal/chat/session/state", params={"session_id": "u:101:default"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["session"]["fallback_count"] == 2
    assert data["session"]["recommended_action"] == "RETRY"
    assert data["session"]["unresolved_context"]["reason_code"] == "LLM_NO_CITATIONS"
    assert data["session"]["selection_snapshot"]["selected_title"] == "도서 B"
    assert data["session"]["pending_action_snapshot"]["type"] == "REFUND_REQUEST"
    assert data["session"]["llm_call_budget"]["limit"] == 5
    assert data["session"]["semantic_cache"]["enabled"] is True
    assert data["session"]["semantic_cache"]["drift_total"] == 4
    assert data["session"]["episode_memory"]["count"] == 2
    assert data["session"]["recommend_experiment"]["block_rate"] == 0.25
    assert data["session"]["recommend_experiment"]["diversity_percent"] == 70
    assert data["session"]["recommend_experiment"]["quality_min_candidates"] == 2
    assert data["session"]["recommend_experiment"]["config_overrides"]["enabled"] is True
    assert any(name == "chat_session_state_requests_total" and labels.get("result") == "ok" for name, labels in captured)


def test_chat_session_state_route_requires_session_id(monkeypatch):
    captured = []

    def fake_inc(name, labels=None):
        captured.append((name, labels or {}))

    monkeypatch.setattr(routes.metrics, "inc", fake_inc)
    client = TestClient(app)
    response = client.get("/internal/chat/session/state")

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert any(name == "chat_session_state_requests_total" and labels.get("result") == "missing_session_id" for name, labels in captured)


def test_chat_session_state_route_rejects_invalid_session_id(monkeypatch):
    captured = []

    def fake_inc(name, labels=None):
        captured.append((name, labels or {}))

    monkeypatch.setattr(routes.metrics, "inc", fake_inc)
    client = TestClient(app)
    response = client.get("/internal/chat/session/state", params={"session_id": "bad session"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert any(name == "chat_session_state_requests_total" and labels.get("result") == "invalid_session_id" for name, labels in captured)


def test_chat_session_reset_route_returns_payload(monkeypatch):
    captured = []

    def fake_inc(name, labels=None):
        captured.append((name, labels or {}))

    def fake_reset(session_id, trace_id, request_id):
        assert session_id == "u:101:default"
        return {
            "session_id": session_id,
            "reset_applied": True,
            "previous_fallback_count": 3,
            "previous_unresolved_context": True,
            "previous_llm_call_count": 1,
            "previous_episode_memory_count": 2,
            "episode_memory_cleared": True,
            "reset_at_ms": 1760000000,
            "trace_id": trace_id,
            "request_id": request_id,
        }

    monkeypatch.setattr(routes.metrics, "inc", fake_inc)
    monkeypatch.setattr(routes, "reset_chat_session_state", fake_reset)

    client = TestClient(app)
    response = client.post("/internal/chat/session/reset", json={"session_id": "u:101:default"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["session"]["reset_applied"] is True
    assert data["session"]["previous_fallback_count"] == 3
    assert data["session"]["previous_llm_call_count"] == 1
    assert data["session"]["previous_episode_memory_count"] == 2
    assert data["session"]["episode_memory_cleared"] is True
    assert any(name == "chat_session_reset_requests_total" and labels.get("result") == "ok" for name, labels in captured)


def test_chat_session_reset_route_requires_session_id(monkeypatch):
    captured = []

    def fake_inc(name, labels=None):
        captured.append((name, labels or {}))

    monkeypatch.setattr(routes.metrics, "inc", fake_inc)
    client = TestClient(app)
    response = client.post("/internal/chat/session/reset", json={})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert any(name == "chat_session_reset_requests_total" and labels.get("result") == "missing_session_id" for name, labels in captured)


def test_chat_session_reset_route_rejects_invalid_session_id(monkeypatch):
    captured = []

    def fake_inc(name, labels=None):
        captured.append((name, labels or {}))

    monkeypatch.setattr(routes.metrics, "inc", fake_inc)
    client = TestClient(app)
    response = client.post("/internal/chat/session/reset", json={"session_id": "bad session"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert any(name == "chat_session_reset_requests_total" and labels.get("result") == "invalid_session_id" for name, labels in captured)


def test_chat_session_reset_route_rejects_invalid_json(monkeypatch):
    captured = []

    def fake_inc(name, labels=None):
        captured.append((name, labels or {}))

    monkeypatch.setattr(routes.metrics, "inc", fake_inc)
    client = TestClient(app)
    response = client.post(
        "/internal/chat/session/reset",
        data="{invalid",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert any(name == "chat_session_reset_requests_total" and labels.get("result") == "invalid_json" for name, labels in captured)
