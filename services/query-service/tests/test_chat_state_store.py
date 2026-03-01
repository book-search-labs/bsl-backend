from app.core import chat_state_store


def test_chat_state_store_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(chat_state_store._SETTINGS, "enabled", False)

    assert chat_state_store.get_session_state("u:1:default") is None
    assert (
        chat_state_store.upsert_session_state(
            "u:1:default",
            user_id="1",
            trace_id="trace_1",
            request_id="req_1",
            fallback_count=1,
        )
        is None
    )
    assert (
        chat_state_store.append_turn_event(
            conversation_id="u:1:default",
            turn_id="req_1",
            event_type="TURN_RECEIVED",
            trace_id="trace_1",
            request_id="req_1",
            route="INPUT",
            reason_code=None,
            payload={"query_len": 3},
        )
        is False
    )
    assert (
        chat_state_store.append_action_audit(
            conversation_id="u:1:default",
            action_type="SESSION_RESET",
            action_state="EXECUTED",
            decision="ALLOW",
            result="SUCCESS",
            actor_user_id="1",
            actor_admin_id=None,
            target_ref="u:1:default",
            auth_context={"session_id": "u:1:default"},
            trace_id="trace_1",
            request_id="req_1",
            reason_code="MANUAL_RESET",
            idempotency_key="SESSION_RESET:u:1:default:req_1",
            metadata={},
        )
        is False
    )
