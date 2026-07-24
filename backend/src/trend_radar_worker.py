"""One-shot entry point for the daily Render Trend Radar cron job."""

from __future__ import annotations

import asyncio

from loguru import logger

from .config import load_settings
from .database import PostgresStore
from .logging_config import setup_logging
from .services.trend_radar import TrendRadarService


async def async_main() -> int:
    settings = load_settings()
    setup_logging(settings.log_level, settings.logs_dir)
    store = PostgresStore(settings.database_url)
    report = await TrendRadarService(settings, store).run_today()
    logger.info("Trend Radar finished", report_date=report.reportDate, status=report.status)
    return 0 if report.status in {"completed", "insufficient_data"} else 1


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
