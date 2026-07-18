"""Scheduler eligibility and publish-interval tests without browser access."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.schemas import QueueItem, RunRecord
from src.config import Settings
from src.scheduler_worker import SchedulerWorker
from src.services.artifact_service import ArtifactService
from src.services.queue_service import QueueService
from src.services.run_service import RunService


class SchedulerWorkerTests(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        auth_path = root / "auth.json"
        auth_path.write_text("{}", encoding="utf-8")
        return Settings(
            dry_run=False,
            posting_enabled=True,
            auth_state_path=auth_path,
            data_path=root / "tweets.txt",
            agent_queue_path=root / "queue.jsonl",
            logs_dir=root / "logs",
            screenshots_dir=root / "screenshots",
            traces_dir=root / "traces",
        )

    @staticmethod
    def _item(item_id: str, status: str, scheduled_for: datetime | None) -> QueueItem:
        return QueueItem(
            id=item_id,
            text="A concise approved post.",
            textLength=24,
            status=status,
            risk="low",
            source="test",
            scheduledFor=scheduled_for,
            createdAt=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def test_starts_only_due_approved_item(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            worker = SchedulerWorker(self._settings(Path(temp_dir)))
            now = datetime(2026, 1, 2, tzinfo=timezone.utc)
            due = self._item("due", "approved", now - timedelta(seconds=1))
            future = self._item("future", "approved", now + timedelta(minutes=1))
            unapproved = self._item("draft", "draft", now - timedelta(seconds=1))
            worker.queue_service.list_items = Mock(return_value=([future, unapproved, due], 3))
            worker.run_service.can_start_publish = Mock(return_value=(True, None))
            worker.run_service.start_publish = Mock(return_value=Mock(id="run-1", status="queued"))

            asyncio.run(worker.run_cycle(now))

            worker.run_service.start_publish.assert_called_once_with("due")

    def test_respects_publish_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = self._settings(root)
            service = RunService(settings, QueueService(settings.data_path, settings.agent_queue_path), ArtifactService(settings))
            started_at = datetime.now(timezone.utc)
            service._append_run(
                RunRecord(
                    id="run-1",
                    queueItemId="item-1",
                    mode="publish",
                    status="failed",
                    startedAt=started_at,
                    finishedAt=started_at,
                    message="failed",
                )
            )

            allowed, reason = service.can_start_publish()

            self.assertFalse(allowed)
            self.assertIn("Next publish attempt", reason or "")


if __name__ == "__main__":
    unittest.main()
