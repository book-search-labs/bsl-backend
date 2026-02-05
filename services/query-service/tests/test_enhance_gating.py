import httpx
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


def test_enhance_skip_no_reason(monkeypatch):
    monkeypatch.setenv("QS_SPELL_PROVIDER", "off")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "off")
    _reset_state(monkeypatch)
    client = TestClient(app)
    payload = {
        "request_id": "req_none",
        "trace_id": "trace_none",
        "q_norm": "harry potter",
        "q_nospace": "harrypotter",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
    }
    response = client.post("/query/enhance", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "SKIP"
    assert "NO_REASON" in data["reason_codes"]


def test_enhance_budget_exceeded(monkeypatch):
    monkeypatch.setenv("QS_SPELL_PROVIDER", "off")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "off")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_WINDOW", "1")
    monkeypatch.setenv("QS_ENHANCE_WINDOW_SEC", "60")
    monkeypatch.setenv("QS_ENHANCE_COOLDOWN_SEC", "0")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "100")
    _reset_state(monkeypatch)

    client = TestClient(app)
    payload1 = {
        "request_id": "req_b1",
        "trace_id": "trace_b1",
        "q_norm": "alpha",
        "q_nospace": "alpha",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "ZERO_RESULTS",
        "signals": {"latency_budget_ms": 800},
    }
    payload2 = {
        "request_id": "req_b2",
        "trace_id": "trace_b2",
        "q_norm": "beta",
        "q_nospace": "beta",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "ZERO_RESULTS",
        "signals": {"latency_budget_ms": 800},
    }
    response1 = client.post("/query/enhance", json=payload1)
    response2 = client.post("/query/enhance", json=payload2)
    assert response1.status_code == 200
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["decision"] == "SKIP"
    assert "BUDGET_EXCEEDED" in data2["reason_codes"]


def test_enhance_cooldown(monkeypatch):
    monkeypatch.setenv("QS_SPELL_PROVIDER", "off")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "off")
    monkeypatch.setenv("QS_ENHANCE_COOLDOWN_SEC", "300")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_WINDOW", "100")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "100")
    _reset_state(monkeypatch)

    client = TestClient(app)
    payload = {
        "request_id": "req_cool",
        "trace_id": "trace_cool",
        "q_norm": "gamma",
        "q_nospace": "gamma",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "ZERO_RESULTS",
        "signals": {"latency_budget_ms": 800},
    }
    client.post("/query/enhance", json=payload)
    response2 = client.post("/query/enhance", json=payload)
    data2 = response2.json()
    assert data2["decision"] == "SKIP"
    assert "COOLDOWN_HIT" in data2["reason_codes"]


def test_enhance_per_query_cap(monkeypatch):
    monkeypatch.setenv("QS_SPELL_PROVIDER", "off")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "off")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "1")
    monkeypatch.setenv("QS_ENHANCE_COOLDOWN_SEC", "0")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_WINDOW", "100")
    _reset_state(monkeypatch)

    client = TestClient(app)
    payload = {
        "request_id": "req_cap",
        "trace_id": "trace_cap",
        "q_norm": "delta",
        "q_nospace": "delta",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "ZERO_RESULTS",
        "signals": {"latency_budget_ms": 800},
    }
    client.post("/query/enhance", json=payload)
    response2 = client.post("/query/enhance", json=payload)
    data2 = response2.json()
    assert data2["decision"] == "SKIP"
    assert "PER_QUERY_CAP" in data2["reason_codes"]


def test_degrade_spell_timeout(monkeypatch):
    async def _raise(*_args, **_kwargs):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("app.core.spell._call_spell_http", _raise)
    monkeypatch.setenv("QS_SPELL_PROVIDER", "http")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "off")
    monkeypatch.setenv("QS_ENHANCE_COOLDOWN_SEC", "0")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_WINDOW", "100")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "100")
    _reset_state(monkeypatch)

    client = TestClient(app)
    payload = {
        "request_id": "req_spell_timeout",
        "trace_id": "trace_spell_timeout",
        "q_norm": "harry pottre",
        "q_nospace": "harrypottre",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "HIGH_OOV",
        "signals": {"latency_budget_ms": 800},
    }
    response = client.post("/query/enhance", json=payload)
    data = response.json()
    assert data["decision"] == "RUN"
    assert "SPELL_ERROR_TIMEOUT" in data["reason_codes"]
    assert data["final"]["text"] == payload["q_norm"]


def test_degrade_rewrite_timeout(monkeypatch):
    async def _raise(*_args, **_kwargs):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("app.core.rewrite._call_llm", _raise)
    monkeypatch.setenv("QS_SPELL_PROVIDER", "off")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "llm")
    monkeypatch.setenv("QS_ENHANCE_COOLDOWN_SEC", "0")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_WINDOW", "100")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "100")
    _reset_state(monkeypatch)

    client = TestClient(app)
    payload = {
        "request_id": "req_rewrite_timeout",
        "trace_id": "trace_rewrite_timeout",
        "q_norm": "harry potter",
        "q_nospace": "harrypotter",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "LOW_CONFIDENCE",
        "signals": {"latency_budget_ms": 800, "score_gap": 0.01},
    }
    response = client.post("/query/enhance", json=payload)
    data = response.json()
    assert data["decision"] == "RUN"
    assert "REWRITE_ERROR_TIMEOUT" in data["reason_codes"]
    assert data["final"]["text"] == payload["q_norm"]
