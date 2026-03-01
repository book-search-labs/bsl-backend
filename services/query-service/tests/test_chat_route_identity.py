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
