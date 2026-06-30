"""Application logging setup."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logging(log_level: str = "INFO", log_dir: str | Path = "logs") -> None:
    """Configure console, application, and error log sinks."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stdout,
        level=log_level.upper(),
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "{extra} | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )
    logger.add(
        log_path / "bot.log",
        level=log_level.upper(),
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
        encoding="utf-8",
    )
    logger.add(
        log_path / "error.log",
        level="ERROR",
        rotation="5 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,
        encoding="utf-8",
        backtrace=True,
        diagnose=False,
    )


__all__ = ["logger", "setup_logging"]
