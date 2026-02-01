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


def test_spell_http_provider(monkeypatch):
    async def _fake_call(_text, _trace_id, _request_id, _locale):
        return "harry potter", 0.8, "mis", {"latency_ms": 12, "model": "spell_v1"}

    monkeypatch.setattr("app.core.spell._call_spell_http", _fake_call)
    monkeypatch.setenv("QS_SPELL_PROVIDER", "http")
    monkeypatch.setenv("QS_REWRITE_PROVIDER", "off")
    monkeypatch.setenv("QS_ENHANCE_COOLDOWN_SEC", "0")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_WINDOW", "100")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "100")
    _reset_state(monkeypatch)

    client = TestClient(app)
    payload = {
        "request_id": "req_spell_http",
        "trace_id": "trace_spell_http",
        "q_norm": "harry pottre",
        "q_nospace": "harrypottre",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "HIGH_OOV",
        "signals": {"latency_budget_ms": 800},
    }
    response = client.post("/query/enhance", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["spell"]["applied"] is True
    assert data["spell"]["corrected"] == "harry potter"


def test_spell_candidates_cached_debug(monkeypatch):
    monkeypatch.setenv("QS_SPELL_PROVIDER", "mock")
    monkeypatch.setenv("QS_SPELL_MOCK_RESPONSE", "harry potter")
    monkeypatch.setenv("QS_SPELL_CANDIDATE_ENABLE", "1")
    monkeypatch.setenv("QS_SPELL_KEYBOARD_LOCALE", "en")
    monkeypatch.setenv("QS_ENHANCE_DEBUG", "1")
    monkeypatch.setenv("QS_ENHANCE_COOLDOWN_SEC", "0")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_WINDOW", "100")
    monkeypatch.setenv("QS_ENHANCE_MAX_PER_QUERY_PER_HOUR", "100")
    _reset_state(monkeypatch)

    client = TestClient(app)
    payload = {
        "request_id": "req_spell_cache",
        "trace_id": "trace_spell_cache",
        "q_norm": "harry pottre",
        "q_nospace": "harrypottre",
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "en"},
        "reason": "HIGH_OOV",
        "signals": {"latency_budget_ms": 800},
    }
    client.post("/query/enhance", json=payload)
    response = client.post("/query/enhance", json=payload)
    data = response.json()
    assert data["cache"]["enhance_hit"] is True
    assert "debug" in data
    assert "spell" in data["debug"]
    assert data["debug"]["spell"].get("candidates") is not None
