from fastapi.testclient import TestClient

from app.main import app
from app.core import state
from app.core.settings import SETTINGS
from app.core.spell_manager import SpellModelManager


client = TestClient(app)


def _reset_spell(backend: str = "toy", enable: bool = True, fallback: str = "toy") -> None:
    SETTINGS.spell_enable = enable
    SETTINGS.spell_backend = backend
    SETTINGS.spell_fallback = fallback
    SETTINGS.spell_model_id = "spell_default"
    SETTINGS.spell_model_path = ""
    SETTINGS.spell_tokenizer_path = ""
    SETTINGS.spell_max_len = 64
    state.spell_manager = SpellModelManager()


def test_spell_returns_corrected():
    _reset_spell()
    payload = {
        "version": "v1",
        "trace_id": "trace_spell",
        "request_id": "req_spell",
        "text": "harry pottre",
        "locale": "en-US",
    }
    response = client.post("/v1/spell", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "v1"
    assert data["corrected"]
    assert data["confidence"] >= 0.0


def test_spell_missing_model_returns_503():
    _reset_spell(backend="onnx", fallback="error")
    SETTINGS.spell_model_path = "/missing/spell.onnx"
    SETTINGS.spell_tokenizer_path = "/missing/tokenizer.json"
    state.spell_manager = SpellModelManager()
    payload = {
        "version": "v1",
        "trace_id": "trace_spell_missing",
        "request_id": "req_spell_missing",
        "text": "harry pottre",
    }
    response = client.post("/v1/spell", json=payload)
    assert response.status_code == 503


def test_spell_input_validation():
    _reset_spell()
    payload = {"version": "v1", "trace_id": "trace_empty", "request_id": "req_empty", "text": "   "}
    response = client.post("/v1/spell", json=payload)
    assert response.status_code == 400

    SETTINGS.spell_max_len = 4
    state.spell_manager = SpellModelManager()
    payload = {"version": "v1", "trace_id": "trace_long", "request_id": "req_long", "text": "12345"}
    response = client.post("/v1/spell", json=payload)
    assert response.status_code == 413
