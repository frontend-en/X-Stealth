"""In-memory PostgreSQL-store substitute for unit tests."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class InMemoryStore:
    """Implements the small repository surface used by unit tests."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self.locked = False

    def ensure_schema(self) -> None:
        return None

    def upsert_queue_item(self, payload: dict[str, Any]) -> None:
        self.tables["queue_items"][payload["id"]] = payload

    def queue_items(self, limit: int, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        items = sorted(
            self.tables["queue_items"].values(),
            key=lambda item: (item.get("createdAt") or "", item["id"]),
            reverse=True,
        )
        return items[offset : offset + limit], len(items)

    def queue_item(self, item_id: str) -> dict[str, Any] | None:
        return self.tables["queue_items"].get(item_id)

    def upsert_run(self, payload: dict[str, Any]) -> None:
        self.tables["runs"][payload["id"]] = payload

    def runs(self, limit: int | None = None) -> list[dict[str, Any]]:
        items = self.list("runs", order_by="started_at DESC, id DESC")
        return items if limit is None else items[:limit]

    def upsert(self, table: str, payload: dict[str, Any], **_: Any) -> None:
        self.tables[table][payload["id"]] = payload

    def get(self, table: str, record_id: str) -> dict[str, Any] | None:
        return self.tables[table].get(record_id)

    def list(self, table: str, *, limit: int | None = None, offset: int = 0, order_by: str = "id") -> list[dict[str, Any]]:
        field = {
            "updated_at": "updatedAt",
            "created_at": "createdAt",
            "event_time": "time",
            "started_at": "startedAt",
        }.get(order_by.split()[0], "id")
        reverse = "DESC" in order_by
        items = sorted(self.tables[table].values(), key=lambda item: (item.get(field) or "", item["id"]), reverse=reverse)
        return items[offset:] if limit is None else items[offset : offset + limit]

    def count(self, table: str, **_: Any) -> int:
        return len(self.tables[table])

    def next_conversation_session_number(self) -> int:
        return max((item.get("sessionNumber", 0) for item in self.tables["conversations"].values()), default=0) + 1

    def claim_publish_lock(self) -> bool:
        if self.locked:
            return False
        self.locked = True
        return True

    def release_publish_lock(self) -> None:
        self.locked = False

    def publish_locked(self) -> bool:
        return self.locked
