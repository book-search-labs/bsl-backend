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
