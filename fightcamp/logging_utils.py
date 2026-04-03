from __future__ import annotations

import json
import importlib
import logging
import os
import sys

try:
    structlog = importlib.import_module("structlog")
except ImportError:  # pragma: no cover - optional dependency in test environments
    structlog = None


class _JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def bind_log_context(**fields: object) -> None:
    if structlog is None:
        return
    structlog.contextvars.bind_contextvars(**fields)


def clear_log_context() -> None:
    if structlog is None:
        return
    structlog.contextvars.clear_contextvars()


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "json").lower()
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    if structlog is not None:
        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
        ]
        renderer = structlog.processors.JSONRenderer()
        if log_format == "console":
            renderer = structlog.dev.ConsoleRenderer(colors=False)
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=renderer,
                foreign_pre_chain=shared_processors,
            )
        )
        structlog.configure(
            processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    else:
        if log_format == "console":
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        else:
            handler.setFormatter(_JsonLogFormatter())

    root_logger.addHandler(handler)
