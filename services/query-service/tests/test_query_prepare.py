from fastapi.testclient import TestClient

from app.main import app


def test_query_prepare_v1():
    client = TestClient(app)
    payload = {"query": {"raw": "Harry Potter"}, "client": {"locale": "en-US"}}
    response = client.post("/query/prepare", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "v1"
    assert data["q_norm"] == "harry potter"
    assert data["detected"]["has_volume"] is False
    assert data["detected"]["mode"] == "normal"
