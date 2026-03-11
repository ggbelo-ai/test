"""Centralized logging configuration for the Conviction Engine."""

from __future__ import annotations

import logging
import os
import sys


def setup_logging(level: str | None = None) -> None:
    """Configure logging for all modules.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR). Defaults to LOG_LEVEL env var or INFO.
    """
    log_level = getattr(logging, (level or os.environ.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)

    # Root logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)
    logging.getLogger("openai").setLevel(logging.WARNING)

    logging.getLogger("agents").setLevel(log_level)
    logging.getLogger("integrations").setLevel(log_level)
    logging.getLogger("db").setLevel(log_level)
    logging.getLogger("notifications").setLevel(log_level)
    logging.getLogger("scheduler").setLevel(log_level)
