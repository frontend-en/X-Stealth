"""Agent audit event writer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agent.schemas import AgentEvent
from src.config import Settings
from src.database import PostgresStore


class AgentEventWriter:
    """Write append-only agent events without exposing sensitive state."""

    def __init__(self, settings: Settings, store: PostgresStore) -> None:
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
        self.store.upsert("agent_events", event.model_dump(mode="json"), event_time=now)
        return event
