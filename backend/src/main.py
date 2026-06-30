"""Application entry point."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from .config import load_settings
from .logging_config import setup_logging
from .tweet_source import FileTweetSource
from .x_bot import XBot


async def async_main() -> int:
    settings = load_settings()
    setup_logging(settings.log_level, settings.logs_dir)
    log = logger.bind(component="main")

    for directory in (settings.logs_dir, settings.screenshots_dir, settings.traces_dir, settings.data_path.parent):
        directory.mkdir(parents=True, exist_ok=True)

    source = FileTweetSource(settings.data_path)
    text = source.next_tweet()
    if text is None:
        log.warning("No tweets found", path=str(settings.data_path))
        return 0

    bot = XBot(settings)
    await bot.run_once(text)
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
