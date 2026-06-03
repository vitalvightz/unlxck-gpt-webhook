from __future__ import annotations

from api.error_sanitizer import sanitize_error_text


def test_sanitize_error_text_redacts_sensitive_generation_error_details():
    raw_error = (
        "request_payload={'email':'fighter@example.com','full_name':'Test Fighter'} "
        "authorization=Bearer sk-testtoken123456789012345678901234567890 "
        "token=abcdef1234567890abcdef1234567890abcdef12"
    )

    sanitized = sanitize_error_text(raw_error)

    assert "fighter@example.com" not in sanitized
    assert "Test Fighter" not in sanitized
    assert "Bearer sk-testtoken" not in sanitized
    assert "abcdef1234567890" not in sanitized
    assert "request_payload=>[redacted_payload]" in sanitized or "request_payload=[redacted_payload]" in sanitized
