"""Production scheduler for approved, due X publishing queue items."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger

from .config import Settings, load_settings
from .database import PostgresStore
from .logging_config import setup_logging
from .services.artifact_service import ArtifactService
from .services.queue_service import QueueService
from .services.run_service import RunService


class SchedulerWorker:
    """Poll the managed queue without bypassing publishing safeguards."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = PostgresStore(settings.database_url)
        self.store.ensure_schema()
        self.queue_service = QueueService(settings.data_path, settings.agent_queue_path, self.store)
        self.queue_service.migrate_legacy_files()
        self.run_service = RunService(settings, self.queue_service, ArtifactService(settings), store=self.store)
        self.run_service.migrate_legacy_file()
        self.run_service.funnel_service.migrate_legacy_file()
        self.log = logger.bind(component="scheduler")

    async def run_forever(self) -> None:
        self.log.info("Scheduler worker started", poll_seconds=self.settings.scheduler_poll_seconds)
        while True:
            await self.run_cycle()
            await asyncio.sleep(self.settings.scheduler_poll_seconds)

    async def run_cycle(self, now: datetime | None = None) -> None:
        """Start at most one eligible publish attempt for the current cycle."""
        current_time = now or datetime.now(timezone.utc)
        items, _ = self.queue_service.list_items(limit=200)
        due_items = sorted(
            (
                item
                for item in items
                if item.status == "approved"
                and item.scheduledFor is not None
                and item.scheduledFor <= current_time
            ),
            key=lambda item: item.scheduledFor or current_time,
        )
        if not due_items:
            self.log.debug("Scheduler found no due approved items")
            return

        self.log.info("Scheduler found due approved items", count=len(due_items))
        for item in due_items:
            allowed, reason = self.run_service.can_start_publish(item.id)
            if not allowed:
                self.log.warning(
                    "Scheduler skipped due item",
                    queue_item_id=item.id,
                    reason=reason,
                )
                if reason and reason.startswith("Next publish attempt"):
                    return
                continue

            run = self.run_service.start_publish(item.id)
            self.log.info(
                "Scheduler started publish run",
                queue_item_id=item.id,
                run_id=run.id,
                status=run.status,
            )
            return


async def async_main() -> int:
    settings = load_settings()
    setup_logging(settings.log_level, settings.logs_dir)
    for directory in (settings.logs_dir, settings.screenshots_dir, settings.traces_dir, settings.data_path.parent):
        directory.mkdir(parents=True, exist_ok=True)
    await SchedulerWorker(settings).run_forever()
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(async_main()))
    except KeyboardInterrupt:
        logger.warning("Scheduler interrupted")
        raise SystemExit(130)
    except Exception:
        logger.exception("Scheduler failed")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
