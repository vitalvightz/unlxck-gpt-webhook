from __future__ import annotations

import re

_SENSITIVE_ERROR_KEY_PATTERN = re.compile(
    r"(?i)([\"']?)\b(email|full_name|first_name|last_name|name|authorization|access_token|"
    r"refresh_token|id_token|token|password)\b\1\s*([:=]|=>)\s*(\"[^\"\n]*\"|'[^'\n]*'|[^,;\s}]+)"
)
_SENSITIVE_PAYLOAD_PATTERN = re.compile(
    r"(?i)([\"']?)\b(request_payload|payload|intake|onboarding_draft)\b\1\s*([:=]|=>)\s*(\{.*?\}|\[.*?\]|'[^']*'|\"[^\"]*\"|[^,;\s]+)"
)
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*")
_LONG_SECRET_PATTERN = re.compile(r"\b[A-Za-z0-9_]{32,}\b")
_ERROR_TEXT_MAX_LENGTH = 300


def _redact_sensitive_error_key(match: re.Match[str]) -> str:
    quote, key, separator = match.group(1), match.group(2), match.group(3)
    return f"{quote}{key}{quote}{separator}[redacted]"


def _redact_sensitive_payload(match: re.Match[str]) -> str:
    quote, key, separator = match.group(1), match.group(2), match.group(3)
    return f"{quote}{key}{quote}{separator}[redacted_payload]"


def sanitize_error_text(exc: Exception | str) -> str:
    text = " ".join(str(exc).split())
    if not text:
        return "<empty>"
    text = _BEARER_TOKEN_PATTERN.sub("Bearer [redacted]", text)
    text = _EMAIL_PATTERN.sub("[redacted_email]", text)
    text = _SENSITIVE_PAYLOAD_PATTERN.sub(_redact_sensitive_payload, text)
    text = _SENSITIVE_ERROR_KEY_PATTERN.sub(_redact_sensitive_error_key, text)
    text = _LONG_SECRET_PATTERN.sub("[redacted_secret]", text)
    if len(text) > _ERROR_TEXT_MAX_LENGTH:
        text = f"{text[:_ERROR_TEXT_MAX_LENGTH]}…"
    return text
