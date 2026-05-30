from __future__ import annotations

import io
import json
import logging

import pytest

from fightcamp import logging_utils


def test_safe_log_record_processor_extracts_only_approved_extra_fields() -> None:
    record = logging.LogRecord(
        name="tests.safe_logging",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="safe event",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.athlete_id = "athlete-456"
    record.auth_event = "token_resolved"
    record.status = "success"
    record.error_code = "none"
    record.email = "private@example.com"

    event_dict = logging_utils._extract_safe_log_record_fields(
        logging.getLogger("tests.safe_logging"),
        "info",
        {"event": "safe event", "_record": record},
    )

    assert event_dict["request_id"] == "req-123"
    assert event_dict["athlete_id"] == "athlete-456"
    assert event_dict["auth_event"] == "token_resolved"
    assert event_dict["status"] == "success"
    assert event_dict["error_code"] == "none"
    assert "email" not in event_dict


def test_structlog_logging_preserves_safe_stdlib_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    if logging_utils.structlog is None:
        pytest.skip("structlog is not installed")

    stream = io.StringIO()
    root_logger = logging.getLogger()
    old_handlers = list(root_logger.handlers)
    old_level = root_logger.level
    monkeypatch.setattr(logging_utils.sys, "stdout", stream)
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    try:
        logging_utils.configure_logging()
        logging.getLogger("tests.safe_logging").info(
            "safe auth event",
            extra={
                "request_id": "req-123",
                "athlete_id": "athlete-456",
                "auth_event": "token_resolved",
                "status": "success",
                "error_code": "none",
                "email": "private@example.com",
            },
        )
    finally:
        for handler in root_logger.handlers:
            handler.flush()
        root_logger.handlers[:] = old_handlers
        root_logger.setLevel(old_level)
        logging_utils.clear_log_context()
        logging_utils.structlog.reset_defaults()

    payload = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert payload["request_id"] == "req-123"
    assert payload["athlete_id"] == "athlete-456"
    assert payload["auth_event"] == "token_resolved"
    assert payload["status"] == "success"
    assert payload["error_code"] == "none"
    assert "email" not in payload
    assert "private@example.com" not in stream.getvalue()
