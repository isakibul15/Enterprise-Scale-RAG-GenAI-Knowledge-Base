import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)


def configure_logging() -> None:
    """
    Configure loguru for the application.

    Sets up three logging streams:
    - Console: Human-readable colored output to stdout
    - Daily log file: Rotating JSON file for log aggregation (30-day retention)
    - Error log: Dedicated error-only file for alerting (60-day retention)
    """
    logger.remove()  # drop default stderr sink

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "{message}"
    )

    # Human-readable console output
    logger.add(
        sys.stdout,
        format=fmt,
        level=settings.log_level,
        colorize=True,
        enqueue=True,      # thread-safe async logging
    )

    # Rotating JSON file — one file per day, kept for 30 days
    logger.add(
        _LOG_DIR / "app_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
        level=settings.log_level,
        rotation="00:00",      # rotate at midnight
        retention="30 days",
        compression="gz",
        serialize=True,        # JSONL format for log aggregators
        enqueue=True,
    )

    # Error-only file for alerting pipelines
    logger.add(
        _LOG_DIR / "errors.log",
        level="ERROR",
        rotation="10 MB",
        retention="60 days",
        compression="gz",
        serialize=True,
        enqueue=True,
    )
