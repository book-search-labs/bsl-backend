from app.core import chat_state_store


def test_sanitize_for_logging_masks_pii_patterns(monkeypatch):
    monkeypatch.setattr(chat_state_store._SETTINGS, "log_message_mode", "masked_raw")
    payload = {
        "email": "user@example.com",
        "phone": "010-1234-5678",
        "payment": "4111-1111-1111-1111",
        "address": "서울시 강남구 테헤란로 123",
    }

    sanitized = chat_state_store._sanitize_for_logging(payload)

    assert sanitized["email"] == "[REDACTED:EMAIL]"
    assert sanitized["phone"] == "[REDACTED:PHONE]"
    assert sanitized["payment"] == "[REDACTED:PAYMENT_ID]"
    assert "[REDACTED:ADDRESS]" in sanitized["address"]


def test_sanitize_for_logging_hashes_message_fields_in_hash_summary_mode(monkeypatch):
    monkeypatch.setattr(chat_state_store._SETTINGS, "log_message_mode", "hash_summary")
    payload = {"message_text": "문의 내용: user@example.com, 010-9999-8888"}

    sanitized = chat_state_store._sanitize_for_logging(payload)

    assert sanitized["message_text"].startswith("[HASH:")
    assert "[REDACTED:EMAIL]" in sanitized["message_text"]
    assert "[REDACTED:PHONE]" in sanitized["message_text"]


def test_sanitize_for_logging_keeps_non_message_fields_as_masked_raw_in_hash_mode(monkeypatch):
    monkeypatch.setattr(chat_state_store._SETTINGS, "log_message_mode", "hash_summary")
    payload = {"reason_code": "EMAIL user@example.com"}

    sanitized = chat_state_store._sanitize_for_logging(payload)

    assert sanitized["reason_code"] == "EMAIL [REDACTED:EMAIL]"
