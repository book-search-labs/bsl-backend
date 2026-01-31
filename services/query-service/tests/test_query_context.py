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
    assert data["meta"]["schemaVersion"] == "qc.v1.1"
    assert data["meta"]["traceId"] == "trace_test"
    assert data["meta"]["requestId"] == "req_test"
    assert data["query"]["raw"] == "  １２３  \n  ABC "
    assert data["query"]["nfkc"] == "  123  \n  ABC "
    assert data["query"]["norm"] == "123 abc"
    assert data["query"]["nospace"] == "123abc"
    assert data["query"]["final"] == "123 abc"
    assert data["query"]["finalSource"] == "norm"
    assert data["query"]["canonicalKey"]
    assert data["query"]["tokens"][0]["t"] == "123"
    assert data["query"]["tokens"][1]["t"] == "abc"
    assert data["detected"]["mode"] == "normal"
    assert data["detected"]["isIsbn"] is False
    assert data["spell"]["applied"] is False
    assert data["rewrite"]["rewritten"] == "123 abc"
    assert "lexical" in data["retrievalHints"]
    assert "vector" in data["retrievalHints"]
    assert "executionHint" in data["retrievalHints"]


def test_query_context_empty_query():
    client = TestClient(app)
    response = client.post("/query-context", json={"query": {"raw": " \t\n "}})
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "empty_query"
    assert data["trace_id"]
    assert data["request_id"]
