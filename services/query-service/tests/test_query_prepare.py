from fastapi.testclient import TestClient

from app.main import app


def test_query_prepare_v11():
    client = TestClient(app)
    payload = {"query": {"raw": "Harry Potter"}, "client": {"locale": "en-US"}}
    response = client.post("/query/prepare", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["schemaVersion"] == "qc.v1.1"
    assert data["query"]["norm"] == "harry potter"
    assert data["detected"]["hasVolume"] is False
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
        assert data1["query"]["canonicalKey"]
        assert data1["query"]["canonicalKey"] == data2["query"]["canonicalKey"]


def test_query_prepare_matches_query_context_alias():
    client = TestClient(app)
    payload = {"query": {"raw": "author:김영하 데미안"}, "client": {"locale": "ko-KR"}}

    prepare_response = client.post("/query/prepare", json=payload)
    context_response = client.post("/query-context", json=payload)

    assert prepare_response.status_code == 200
    assert context_response.status_code == 200

    prepare_data = prepare_response.json()
    context_data = context_response.json()

    # timestamp is generated at response time; normalize it for shape parity checks.
    prepare_data["meta"]["timestampMs"] = 0
    context_data["meta"]["timestampMs"] = 0
    assert prepare_data == context_data
