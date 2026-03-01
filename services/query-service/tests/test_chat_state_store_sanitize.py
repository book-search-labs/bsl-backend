from app.core import chat_state_store


def test_redact_text_masks_email_phone_payment_and_address():
    raw = "연락처 010-1234-5678, 이메일 foo.bar@example.com, 카드 1234-5678-9012-3456, 주소 서울시 강남구 테헤란로 123"
    redacted = chat_state_store._redact_text(raw)

    assert "[REDACTED:PHONE]" in redacted
    assert "[REDACTED:EMAIL]" in redacted
    assert "[REDACTED:PAYMENT_ID]" in redacted
    assert "[REDACTED:ADDRESS]" in redacted



def test_sanitize_for_logging_hash_summary_applies_only_message_fields(monkeypatch):
    monkeypatch.setattr(chat_state_store._SETTINGS, "log_message_mode", "hash_summary")

    payload = {
        "message_text": "문의자 이메일은 user@example.com 입니다",
        "note": "연락처 010-9999-1111",
        "nested": {
            "content": "카드 1234-5678-9012-3456 정보",
            "meta": "서울시 강남구 테헤란로 123",
        },
    }

    sanitized = chat_state_store._sanitize_for_logging(payload)

    message_text = str(sanitized["message_text"])
    nested_content = str(sanitized["nested"]["content"])
    assert message_text.startswith("[HASH:")
    assert "[REDACTED:EMAIL]" in message_text
    assert nested_content.startswith("[HASH:")
    assert "[REDACTED:PAYMENT_ID]" in nested_content

    # non-message fields are redacted without hash envelope
    assert sanitized["note"] == "연락처 [REDACTED:PHONE]"
    assert sanitized["nested"]["meta"] == "서울시 [REDACTED:ADDRESS]"



def test_sanitize_for_logging_masked_raw_keeps_plain_redaction(monkeypatch):
    monkeypatch.setattr(chat_state_store._SETTINGS, "log_message_mode", "masked_raw")

    payload = {"message_text": "문의자 이메일 user@example.com"}
    sanitized = chat_state_store._sanitize_for_logging(payload)

    assert sanitized["message_text"] == "문의자 이메일 [REDACTED:EMAIL]"
