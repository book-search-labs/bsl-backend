from app.core import chat_state_store


class _FakeCursor:
    def __init__(self, steps, executed):
        self._steps = steps
        self._executed = executed
        self.rowcount = 0
        self._fetchone = None

    def execute(self, sql, params=None):
        self._executed.append((str(sql), params))
        if not self._steps:
            raise AssertionError("unexpected SQL execution")
        step = self._steps.pop(0)
        self.rowcount = int(step.get("rowcount") or 0)
        self._fetchone = step.get("fetchone")
        return self.rowcount

    def fetchone(self):
        return self._fetchone

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self, steps, executed):
        self._steps = steps
        self._executed = executed
        self.closed = False

    def cursor(self):
        return _FakeCursor(self._steps, self._executed)

    def close(self):
        self.closed = True


def test_run_retention_cleanup_dry_run(monkeypatch):
    monkeypatch.setattr(chat_state_store._SETTINGS, "enabled", True)
    monkeypatch.setattr(chat_state_store._SETTINGS, "session_state_retention_days", 14)
    monkeypatch.setattr(chat_state_store._SETTINGS, "turn_event_retention_days", 30)
    monkeypatch.setattr(chat_state_store._SETTINGS, "action_audit_retention_days", 90)
    monkeypatch.setattr(chat_state_store._SETTINGS, "retention_delete_batch_size", 500)
    monkeypatch.setattr(chat_state_store, "_enabled", lambda: True)

    executed = []
    steps = [
        {"fetchone": {"cnt": 3}},
        {"fetchone": {"cnt": 5}},
        {"fetchone": {"cnt": 7}},
    ]
    monkeypatch.setattr(chat_state_store, "_connect", lambda: _FakeConnection(steps, executed))
    audit_calls = []
    monkeypatch.setattr(chat_state_store, "append_action_audit", lambda **kwargs: audit_calls.append(kwargs) or True)

    result = chat_state_store.run_retention_cleanup(dry_run=True, trace_id="trace_ret", request_id="req_ret")

    assert result["status"] == "ok"
    assert result["dry_run"] is True
    assert result["deleted"] == {
        "chat_session_state": 3,
        "chat_turn_event": 5,
        "chat_action_audit": 7,
    }
    assert all(sql.startswith("SELECT COUNT(*) AS cnt FROM ") for sql, _ in executed)
    assert audit_calls
    assert audit_calls[0]["reason_code"] == "RETENTION:DRY_RUN"


def test_run_retention_cleanup_delete_mode(monkeypatch):
    monkeypatch.setattr(chat_state_store._SETTINGS, "enabled", True)
    monkeypatch.setattr(chat_state_store._SETTINGS, "session_state_retention_days", 10)
    monkeypatch.setattr(chat_state_store._SETTINGS, "turn_event_retention_days", 20)
    monkeypatch.setattr(chat_state_store._SETTINGS, "action_audit_retention_days", 40)
    monkeypatch.setattr(chat_state_store._SETTINGS, "retention_delete_batch_size", 123)
    monkeypatch.setattr(chat_state_store, "_enabled", lambda: True)

    executed = []
    steps = [
        {"rowcount": 2},
        {"rowcount": 4},
        {"rowcount": 6},
    ]
    monkeypatch.setattr(chat_state_store, "_connect", lambda: _FakeConnection(steps, executed))
    audit_calls = []
    monkeypatch.setattr(chat_state_store, "append_action_audit", lambda **kwargs: audit_calls.append(kwargs) or True)

    result = chat_state_store.run_retention_cleanup(dry_run=False, trace_id="trace_del", request_id="req_del")

    assert result["status"] == "ok"
    assert result["dry_run"] is False
    assert result["deleted"] == {
        "chat_session_state": 2,
        "chat_turn_event": 4,
        "chat_action_audit": 6,
    }
    assert "DELETE FROM chat_session_state" in executed[0][0]
    assert executed[0][1] == (10, 123)
    assert "DELETE FROM chat_turn_event" in executed[1][0]
    assert executed[1][1] == (20, 123)
    assert "DELETE FROM chat_action_audit" in executed[2][0]
    assert executed[2][1] == (40, 123)
    assert audit_calls
    assert audit_calls[0]["reason_code"] == "RETENTION:APPLIED"
