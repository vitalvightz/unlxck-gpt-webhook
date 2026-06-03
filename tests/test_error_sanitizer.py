from __future__ import annotations

from pathlib import Path

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


def test_generation_orchestrator_does_not_auto_log_raw_exceptions():
    source = Path("api/generation/orchestrator.py").read_text()

    assert "logger.exception" not in source
    assert "exc.child_traceback," not in source
