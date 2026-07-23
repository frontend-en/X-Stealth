"""Agent audit event writer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.agent.schemas import AgentEvent
from src.config import Settings
from src.database import PostgresStore


class AgentEventWriter:
    """Write append-only agent events without exposing sensitive state."""

    def __init__(self, settings: Settings, store: PostgresStore | None = None) -> None:
        self.path = settings.agent_events_path
        self.store = store

    def write(
        self,
        event_type: AgentEvent.model_fields["type"].annotation,
        message: str,
        *,
        queue_item_id: str | None = None,
        run_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AgentEvent:
        now = datetime.now(timezone.utc)
        event = AgentEvent(
            id=f"event-{now.strftime('%Y%m%d-%H%M%S-%f')}",
            type=event_type,
            time=now,
            queueItemId=queue_item_id,
            runId=run_id,
            message=message,
            details=details or {},
        )
        if self.store is not None:
            self.store.upsert("agent_events", event.model_dump(mode="json"), event_time=now)
            return event
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return event

    def migrate_legacy_file(self) -> None:
        if self.store is None:
            return

        def import_events(raw: str) -> None:
            for line in raw.splitlines():
                try:
                    event = AgentEvent.model_validate(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
                self.store.upsert("agent_events", event.model_dump(mode="json"), event_time=event.time)

        self.store.import_once(self.path, import_events)
