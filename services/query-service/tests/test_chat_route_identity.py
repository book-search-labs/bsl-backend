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
