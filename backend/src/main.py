"""Application entry point."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from .config import load_settings
from .logging_config import setup_logging
from .database import PostgresStore
from .scheduler_worker import SchedulerWorker


async def async_main() -> int:
    settings = load_settings()
    setup_logging(settings.log_level, settings.logs_dir)
    log = logger.bind(component="main")

    for directory in (settings.logs_dir, settings.screenshots_dir, settings.traces_dir):
        directory.mkdir(parents=True, exist_ok=True)

    store = PostgresStore(settings.database_url)
    worker = SchedulerWorker(settings, store)
    await worker.run_cycle()
    log.info("Completed one PostgreSQL queue scheduling cycle")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(async_main()))
    except KeyboardInterrupt:
        logger.warning("Interrupted")
        raise SystemExit(130)
    except Exception:
        logger.exception("Fatal error")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
