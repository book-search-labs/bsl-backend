from fastapi.testclient import TestClient

from app.main import app
from app.core import rewrite_log


def _init_db(monkeypatch, tmp_path):
    db_path = tmp_path / "rewrite_failures.db"
    monkeypatch.setenv("QS_REWRITE_DB_PATH", str(db_path))
    rewrite_log._rewrite_log = None
    return rewrite_log.get_rewrite_log()


def test_rewrite_failures_empty(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    client = TestClient(app)
    response = client.get("/internal/qc/rewrite/failures")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []


def test_rewrite_failures_filters(monkeypatch, tmp_path):
    log = _init_db(monkeypatch, tmp_path)
    log.log(
        {
            "request_id": "req_a",
            "trace_id": "trace_a",
            "canonical_key": "ck:a",
            "q_raw": "hp",
            "q_norm": "hp",
            "reason": "ZERO_RESULTS",
            "decision": "RUN",
            "strategy": "REWRITE_ONLY",
            "failure_tag": "REWRITE_ERROR_TIMEOUT",
            "error_code": "timeout",
            "error_message": "timeout",
            "created_at": "2024-01-01T00:00:00Z",
        }
    )
    log.log(
        {
            "request_id": "req_b",
            "trace_id": "trace_b",
            "canonical_key": "ck:b",
            "q_raw": "abc",
            "q_norm": "abc",
            "reason": "HIGH_OOV",
            "decision": "RUN",
            "strategy": "SPELL_ONLY",
            "failure_tag": "SPELL_REJECT_NO_CHANGE",
            "created_at": "2024-01-02T00:00:00Z",
        }
    )

    client = TestClient(app)
    response = client.get("/internal/qc/rewrite/failures", params={"reason": "ZERO_RESULTS"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["reason"] == "ZERO_RESULTS"
    assert items[0]["error_code"] == "timeout"

    response = client.get("/internal/qc/rewrite/failures", params={"since": "2024-01-02T00:00:00Z"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["reason"] == "HIGH_OOV"
