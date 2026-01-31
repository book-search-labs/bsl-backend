from fastapi.testclient import TestClient

from app.main import app


def test_query_enhance_skip_isbn():
    client = TestClient(app)
    payload = {
        "request_id": "req_test",
        "trace_id": "trace_test",
        "q_norm": "9788912345678",
        "q_nospace": "9788912345678",
        "detected": {"mode": "isbn", "is_isbn": True, "has_volume": False, "lang": "en"},
        "reason": "ZERO_RESULTS",
        "signals": {"latency_budget_ms": 800},
    }
    response = client.post("/query/enhance", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "SKIP"
    assert "ISBN_QUERY" in data["reason_codes"]


def test_query_enhance_run_zero_results():
    client = TestClient(app)
    payload = {
        "request_id": "req_test_2",
        "trace_id": "trace_test_2",
        "q_norm": "harry potter",
        "q_nospace": "harrypotter",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "ZERO_RESULTS",
        "signals": {"latency_budget_ms": 800, "score_gap": 0.01},
    }
    response = client.post("/query/enhance", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "RUN"
    assert data["strategy"] == "SPELL_THEN_REWRITE"
