"""Run registry and execution service."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.api.schemas import Artifact, RunDetail, RunRecord, RunStatus
from src.config import Settings
from src.publishers.base import Publisher
from src.publishers.x_publisher import XPublisher
from src.services.funnel_service import FunnelService
from src.services.quality_service import QualityService
from src.services.artifact_service import ArtifactService
from src.services.queue_service import QueueService, validate_post_text
from src.database import PostgresStore


class RunService:
    """Manage dry-run and publish runs."""

    def __init__(
        self,
        settings: Settings,
        queue_service: QueueService,
        artifact_service: ArtifactService,
        publisher: Publisher | None = None,
        store: PostgresStore | None = None,
    ) -> None:
        self.settings = settings
        self.queue_service = queue_service
        self.artifact_service = artifact_service
        self.publisher = publisher or XPublisher(settings)
        self.store = store
        self.runs_path = settings.data_path.parent / "runs.jsonl"
        self.quality_service = QualityService()
        self.funnel_service = FunnelService(settings.data_path.parent, store)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._publish_lock_path = settings.data_path.parent / "active-publish.lock"
        self._owns_publish_lock = False

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        runs = self._read_runs()
        return sorted(runs, key=lambda run: run.startedAt or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[
            :limit
        ]

    def get_run(self, run_id: str) -> RunDetail | None:
        for run in self._read_runs():
            if run.id == run_id:
                return RunDetail(**run.model_dump(), logs=[])
        return None

    def start_dry_run(self, queue_item_id: str) -> RunRecord:
        item = self.queue_service.get_item(queue_item_id)
        now = self._now()
        run = RunRecord(
            id=self._make_run_id(now),
            queueItemId=queue_item_id,
            mode="dry_run",
            status="completed",
            startedAt=now,
            finishedAt=now,
            message="Dry run completed. Publishing was skipped.",
            artifacts=[],
        )
        if item is None:
            run.status = "failed"
            run.message = "Queue item was not found."
        else:
            quality = self.quality_service.evaluate(item, self.queue_service.list_items(limit=200)[0])
            run.qualityScore = quality.qualityScore
            if not quality.valid:
                run.status = "blocked"
                run.message = "; ".join(quality.errors)
                self.funnel_service.log_event(
                    item,
                    status="dry_run_blocked",
                    run_id=run.id,
                    quality_score=quality.qualityScore,
                    notes=run.message,
                )
            else:
                updated = self.queue_service.mark_dry_run_passed(
                    queue_item_id,
                    run_id=run.id,
                    quality_score=quality.qualityScore,
                    utm_url=quality.utmUrl,
                )
                self.funnel_service.log_event(
                    updated or item,
                    status="dry_run_passed",
                    run_id=run.id,
                    quality_score=quality.qualityScore,
                    notes=run.message,
                )
        self._append_run(run)
        return run

    def can_start_publish(self, queue_item_id: str | None = None) -> tuple[bool, str | None]:
        if self.settings.dry_run or not self.settings.posting_enabled:
            return False, "Publishing is disabled by backend configuration."
        if not self.settings.auth_state_path.exists():
            return False, "Auth state is missing."
        if any(not task.done() for task in self._tasks.values()):
            return False, "Another publish run is already active."
        if self.store is not None and self.store.publish_locked():
            return False, "Another publish run is already active."
        if self.store is None and self._publish_lock_path.exists():
            return False, "Another publish run is already active."
        next_allowed_at = self.next_publish_allowed_at()
        if next_allowed_at is not None and self._now() < next_allowed_at:
            return False, f"Next publish attempt is allowed at {next_allowed_at.isoformat()}."
        if queue_item_id is not None:
            item = self.queue_service.get_item(queue_item_id)
            if item is None:
                return False, "Queue item was not found."
            if item.status != "approved":
                return False, "Queue item must be approved before publishing."
            if not self._has_successful_dry_run(item):
                return False, "A successful dry-run is required after the latest draft change."
            if self._publish_attempt_count(item.id) >= self.settings.scheduler_max_publish_attempts:
                return False, "Maximum publish attempts have been reached for this queue item."
        return True, None

    def start_publish(self, queue_item_id: str) -> RunRecord:
        item = self.queue_service.get_item(queue_item_id)
        now = self._now()
        run = RunRecord(
            id=self._make_run_id(now),
            queueItemId=queue_item_id,
            mode="publish",
            status="queued",
            startedAt=now,
            finishedAt=None,
            message="Publish run queued.",
            artifacts=[],
        )
        if item is None:
            run.status = "failed"
            run.finishedAt = now
            run.message = "Queue item was not found."
            self._append_run(run)
            return run

        allowed, reason = self.can_start_publish(queue_item_id)
        if not allowed:
            run.status = "blocked"
            run.finishedAt = now
            run.message = reason or "Publishing is not allowed."
            self._append_run(run)
            self.funnel_service.log_event(item, status="publish_blocked", run_id=run.id, notes=run.message)
            return run

        validation = validate_post_text(item.text)
        if not validation.valid:
            run.status = "blocked"
            run.finishedAt = now
            run.message = "; ".join(validation.errors)
            self._append_run(run)
            return run

        run.qualityScore = item.qualityScore
        if not self._acquire_publish_lock():
            run.status = "blocked"
            run.finishedAt = self._now()
            run.message = "Another publish run is already active."
            self._append_run(run)
            self.funnel_service.log_event(item, status="publish_blocked", run_id=run.id, notes=run.message)
            return run
        self._append_run(run)
        try:
            self._tasks[run.id] = asyncio.create_task(self._execute_publish(run, item))
        except Exception:
            self._release_publish_lock()
            raise
        return run

    async def _execute_publish(self, run: RunRecord, item) -> None:
        running = run.model_copy(update={"status": "running", "message": "Publish run started."})
        self._append_run(running)
        self.funnel_service.log_event(item, status="publish_started", run_id=run.id)
        try:
            try:
                result = await self.publisher.publish_once(item.text)
                if not result.success:
                    raise RuntimeError(result.message or "Publish run failed.")
            except Exception as exc:
                artifacts = self._latest_artifacts()
                failed = running.model_copy(
                    update={
                        "status": "failed",
                        "finishedAt": self._now(),
                        "message": str(exc),
                        "artifacts": artifacts,
                    }
                )
                self._append_run(failed)
                self.funnel_service.log_event(item, status="publish_failed", run_id=run.id, notes=str(exc))
                return

            posted_item = self.queue_service.mark_posted(item.id) or item
            completed = running.model_copy(
                update={
                    "status": "completed",
                    "finishedAt": self._now(),
                    "message": result.message or "Publish run completed.",
                    "artifacts": self._latest_artifacts(),
                }
            )
            self._append_run(completed)
            self.funnel_service.log_event(posted_item, status="posted", run_id=run.id)
        finally:
            self._release_publish_lock()

    def _latest_artifacts(self) -> list[Artifact]:
        return self.artifact_service.list_artifacts(limit=5)

    def _read_runs(self) -> list[RunRecord]:
        if self.store is not None:
            return [RunRecord.model_validate(row) for row in self.store.runs()]
        latest: dict[str, RunRecord] = {}
        if not self.runs_path.exists():
            return []
        for line in self.runs_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                raw: dict[str, Any] = json.loads(line)
                run = RunRecord.model_validate(raw)
                latest[run.id] = run
            except (json.JSONDecodeError, ValueError):
                continue
        return list(latest.values())

    def _append_run(self, run: RunRecord) -> None:
        if self.store is not None:
            self.store.upsert_run(run.model_dump(mode="json"))
            return
        self.runs_path.parent.mkdir(parents=True, exist_ok=True)
        with self.runs_path.open("a", encoding="utf-8") as handle:
            handle.write(run.model_dump_json() + "\n")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _make_run_id(now: datetime) -> str:
        return f"run-{now.strftime('%Y%m%d-%H%M%S-%f')}"

    def _has_successful_dry_run(self, item) -> bool:
        if not item.dryRunId:
            return False
        for run in self._read_runs():
            if run.id == item.dryRunId and run.queueItemId == item.id:
                return run.mode == "dry_run" and run.status == "completed"
        return False

    def next_publish_allowed_at(self) -> datetime | None:
        """Return the UTC time at which a new real publish attempt may start."""
        attempts = [
            run.startedAt
            for run in self._read_runs()
            if run.mode == "publish"
            and run.status in {"running", "completed", "failed"}
            and run.startedAt is not None
        ]
        if not attempts:
            return None
        return max(attempts) + timedelta(minutes=self.settings.min_post_interval_minutes)

    def _publish_attempt_count(self, queue_item_id: str) -> int:
        return sum(
            run.queueItemId == queue_item_id
            and run.mode == "publish"
            and run.status in {"running", "completed", "failed"}
            for run in self._read_runs()
        )

    def _acquire_publish_lock(self) -> bool:
        """Atomically reserve the shared data directory for one publish attempt."""
        if self.store is not None:
            claimed = self.store.claim_publish_lock()
            self._owns_publish_lock = claimed
            return claimed
        self._publish_lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self._publish_lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(self._now().isoformat())
        self._owns_publish_lock = True
        return True

    def _release_publish_lock(self) -> None:
        if not self._owns_publish_lock:
            return
        if self.store is not None:
            self.store.release_publish_lock()
            self._owns_publish_lock = False
            return
        try:
            self._publish_lock_path.unlink(missing_ok=True)
        finally:
            self._owns_publish_lock = False

    def migrate_legacy_file(self) -> None:
        if self.store is None:
            return

        def import_runs(raw: str) -> None:
            latest: dict[str, RunRecord] = {}
            for line in raw.splitlines():
                try:
                    item = RunRecord.model_validate(json.loads(line))
                    latest[item.id] = item
                except (json.JSONDecodeError, ValueError):
                    continue
            for item in latest.values():
                self.store.upsert_run(item.model_dump(mode="json"))

        self.store.import_once(self.runs_path, import_runs)
