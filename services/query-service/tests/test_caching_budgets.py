from fastapi.testclient import TestClient

from app.main import app
from app.api import routes
from app.core.cache import CacheClient
from app.core.enhance import load_config
from app.core.metrics import metrics


def _reset_state(monkeypatch):
    routes.CACHE = CacheClient(None)
    routes.ENHANCE_CONFIG = load_config()
    with metrics._lock:
        metrics._counters.clear()


def test_prepare_cache_hit(monkeypatch):
    monkeypatch.setenv("QS_SPELL_PROVIDER", "off")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "off")
    _reset_state(monkeypatch)
    client = TestClient(app)
    payload = {"query": {"raw": "Harry Potter"}, "client": {"locale": "en-US"}}
    client.post("/query/prepare", json=payload)
    client.post("/query/prepare", json=payload)
    metrics_data = client.get("/metrics").json()
    assert metrics_data.get("qs_norm_cache_hit_total", 0) >= 1


def test_enhance_cache_hit(monkeypatch):
    monkeypatch.setenv("QS_SPELL_PROVIDER", "off")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "mock")
    monkeypatch.setenv("QS_REWRITE_MOCK_RESPONSE", '{"q_rewrite": "harry potter", "confidence": 0.8}')
    monkeypatch.setenv("QS_ENHANCE_COOLDOWN_SEC", "0")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_WINDOW", "100")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "100")
    _reset_state(monkeypatch)

    client = TestClient(app)
    payload = {
        "request_id": "req_cache",
        "trace_id": "trace_cache",
        "q_norm": "harry pottre",
        "q_nospace": "harrypottre",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "LOW_CONFIDENCE",
        "signals": {"latency_budget_ms": 800, "score_gap": 0.01},
    }
    response1 = client.post("/query/enhance", json=payload)
    response2 = client.post("/query/enhance", json=payload)
    assert response1.status_code == 200
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["cache"]["enhance_hit"] is True


def test_enhance_deny_cache(monkeypatch):
    monkeypatch.setenv("QS_SPELL_PROVIDER", "off")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "off")
    monkeypatch.setenv("QS_ENHANCE_MIN_LATENCY_BUDGET_MS", "200")
    monkeypatch.setenv("QS_ENHANCE_COOLDOWN_SEC", "0")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_WINDOW", "100")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "100")
    _reset_state(monkeypatch)

    client = TestClient(app)
    payload = {
        "request_id": "req_deny",
        "trace_id": "trace_deny",
        "q_norm": "harry potter",
        "q_nospace": "harrypotter",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "ZERO_RESULTS",
        "signals": {"latency_budget_ms": 50},
    }
    response1 = client.post("/query/enhance", json=payload)
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["decision"] == "SKIP"
    assert "LOW_BUDGET" in data1["reason_codes"]

    response2 = client.post("/query/enhance", json=payload)
    data2 = response2.json()
    assert data2["decision"] == "SKIP"
    assert "DENY_CACHE_HIT" in data2["reason_codes"]
