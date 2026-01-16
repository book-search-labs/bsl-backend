from fastapi.testclient import TestClient

from app.main import app


def test_query_context_normalization():
    client = TestClient(app)
    payload = {"query": {"raw": "  １２３  \n  ABC "}}
    response = client.post(
        "/query-context",
        json=payload,
        headers={"x-trace-id": "trace_test", "x-request-id": "req_test"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "v1"
    assert data["trace_id"] == "trace_test"
    assert data["request_id"] == "req_test"
    assert data["query"]["normalized"] == "123 ABC"
    assert data["query"]["canonical"] == "123 ABC"
    assert data["query"]["tokens"] == ["123", "ABC"]
    assert data["spell"]["applied"] is False
    assert data["rewrite"]["rewritten"] == "123 ABC"


def test_query_context_empty_query():
    client = TestClient(app)
    response = client.post("/query-context", json={"query": {"raw": " \t\n "}})
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "empty_query"
    assert data["trace_id"]
    assert data["request_id"]
