"""Logging configuration for GPU Worker."""

import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the worker logger."""
    logger = logging.getLogger("worker")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = setup_logging()


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a child logger with the given name."""
    if name:
        return logging.getLogger(f"worker.{name}")
    return logger
