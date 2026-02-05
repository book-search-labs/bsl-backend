from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_embed_returns_vectors():
    payload = {"model": "embed_default", "normalize": True, "texts": ["hello", "world"]}
    response = client.post("/v1/embed", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "v1"
    assert data["vectors"]
    assert len(data["vectors"]) == 2
    assert len(data["vectors"][0]) == data["dim"]
