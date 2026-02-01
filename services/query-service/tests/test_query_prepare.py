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


def test_query_prepare_canonical_key_stable():
    client = TestClient(app)
    cases = [
        "Harry Potter",
        "해리포터 1권",
        "ISBN 978-89-123-4567-8",
        "ㄱㄴㄷ",
    ]
    for raw in cases:
        payload = {"query": {"raw": raw}, "client": {"locale": "ko-KR"}}
        response1 = client.post("/query/prepare", json=payload)
        response2 = client.post("/query/prepare", json=payload)
        assert response1.status_code == 200
        assert response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()
        assert data1["canonical_key"]
        assert data1["canonical_key"] == data2["canonical_key"]
