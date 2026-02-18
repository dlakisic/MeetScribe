"""Logging configuration for MeetScribe."""

import json
import logging
import os
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_RESERVED_LOG_KEYS = set(logging.makeLogRecord({}).__dict__.keys()) | {"asctime", "message"}


def _to_jsonable(value):
    """Best-effort conversion for JSON logging fields."""
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _extract_context(record: logging.LogRecord) -> dict:
    """Extract custom fields set via the `extra` logging argument."""
    context = {}
    for key, value in record.__dict__.items():
        if key in _RESERVED_LOG_KEYS or key.startswith("_"):
            continue
        context[key] = _to_jsonable(value)
    return context


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = _extract_context(record)
        if context:
            payload["context"] = context
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ContextTextFormatter(logging.Formatter):
    """Text formatter that appends `extra` fields as key=value."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        context = _extract_context(record)
        if not context:
            return base
        parts = [f"{k}={v}" for k, v in sorted(context.items())]
        return f"{base} | {' '.join(parts)}"


def _build_stream_handler() -> logging.Handler:
    """Build text handler for terminal output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        ContextTextFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler


def _build_file_handler(path_str: str) -> logging.Handler | None:
    """Build JSON rotating file handler if path is configured."""
    if not path_str:
        return None

    path = Path(path_str).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        filename=path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(JsonFormatter())
    return handler


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the application logger.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("meetscribe")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    logger.addHandler(_build_stream_handler())

    file_path = os.getenv("MEETSCRIBE_LOG_FILE", "")
    file_handler = _build_file_handler(file_path)
    if file_handler:
        logger.addHandler(file_handler)

    return logger


logger = setup_logging()


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a child logger with the given name.

    Args:
        name: Optional name suffix (e.g., "api", "gpu_client")

    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"meetscribe.{name}")
    return logger
