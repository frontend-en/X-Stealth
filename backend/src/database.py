"""PostgreSQL persistence for application state.

The application deliberately keeps browser session state and generated artifacts on
disk.  Everything that represents business state is stored in PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


STATE_TABLES = frozenset(
    {
        "queue_items",
        "runs",
        "agent_events",
        "funnel_events",
        "conversations",
        "chat_messages",
        "pipeline_runs",
        "trend_reports",
    }
)


class PostgresStore:
    """Small synchronous repository shared by the API and scheduler services."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS queue_items (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ,
                    status TEXT NOT NULL,
                    scheduled_for TIMESTAMPTZ
                );
                CREATE INDEX IF NOT EXISTS queue_items_created_at_idx ON queue_items (created_at DESC);
                CREATE INDEX IF NOT EXISTS queue_items_due_idx ON queue_items (status, scheduled_for);

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    queue_item_id TEXT,
                    payload JSONB NOT NULL,
                    started_at TIMESTAMPTZ,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_queue_item_idx ON runs (queue_item_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS runs_publish_idx ON runs (mode, status, started_at DESC);

                CREATE TABLE IF NOT EXISTS agent_events (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    event_time TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS funnel_events (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    event_time TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    session_number INTEGER NOT NULL UNIQUE,
                    updated_at TIMESTAMPTZ NOT NULL,
                    deleted_at TIMESTAMPTZ
                );
                CREATE SEQUENCE IF NOT EXISTS conversation_session_number_seq;
                CREATE INDEX IF NOT EXISTS conversations_updated_idx ON conversations (updated_at DESC);
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chat_messages_conversation_idx ON chat_messages (conversation_id, created_at);
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS pipeline_runs_conversation_idx ON pipeline_runs (conversation_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS trend_reports (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    report_date DATE NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS trend_reports_created_idx ON trend_reports (created_at DESC);
                CREATE TABLE IF NOT EXISTS publish_locks (
                    name TEXT PRIMARY KEY,
                    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                DROP TABLE IF EXISTS legacy_imports;
                """
            )
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES ('001_postgresql_state') ON CONFLICT DO NOTHING"
            )
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES ('002_remove_legacy_file_storage') ON CONFLICT DO NOTHING"
            )
        self._schema_ready = True

    def ensure_trend_reports_schema(self) -> None:
        """Apply the additive Trend Radar table independently of an already warmed schema cache."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trend_reports (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    report_date DATE NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS trend_reports_created_idx ON trend_reports (created_at DESC);
                """
            )

    def upsert_queue_item(self, payload: dict[str, Any]) -> None:
        self.ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO queue_items (id, payload, created_at, updated_at, status, scheduled_for)
                VALUES (%(id)s, %(payload)s, %(created)s, %(updated)s, %(status)s, %(scheduled)s)
                ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at,
                    status = EXCLUDED.status, scheduled_for = EXCLUDED.scheduled_for
                """,
                self._queue_params(payload),
            )

    def queue_items(self, limit: int, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        self.ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM queue_items")
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT payload FROM queue_items ORDER BY created_at DESC NULLS LAST, id DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [row["payload"] for row in cursor.fetchall()], total

    def queue_item(self, item_id: str) -> dict[str, Any] | None:
        return self.get("queue_items", item_id)

    def upsert_run(self, payload: dict[str, Any]) -> None:
        self.ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO runs (id, queue_item_id, payload, started_at, status, mode)
                VALUES (%(id)s, %(queue_item_id)s, %(payload)s, %(started_at)s, %(status)s, %(mode)s)
                ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, status = EXCLUDED.status""",
                {
                    "id": payload["id"], "queue_item_id": payload.get("queueItemId"), "payload": Jsonb(payload),
                    "started_at": payload.get("startedAt"), "status": payload["status"], "mode": payload["mode"],
                },
            )

    def runs(self, limit: int | None = None) -> list[dict[str, Any]]:
        return self.list("runs", limit=limit, order_by="started_at DESC NULLS LAST, id DESC")

    def claim_publish_lock(self) -> bool:
        self.ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO publish_locks (name) VALUES ('publisher') ON CONFLICT DO NOTHING RETURNING name")
            return cursor.fetchone() is not None

    def release_publish_lock(self) -> None:
        self.ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM publish_locks WHERE name = 'publisher'")

    def publish_locked(self) -> bool:
        self.ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM publish_locks WHERE name = 'publisher') AS locked")
            return bool(cursor.fetchone()["locked"])

    def upsert(self, table: str, payload: dict[str, Any], **columns: Any) -> None:
        self.ensure_schema()
        self._validate_table(table)
        if table == "queue_items":
            self.upsert_queue_item(payload)
            return
        if table == "runs":
            self.upsert_run(payload)
            return
        column_names = ["id", "payload", *columns]
        values = {"id": payload["id"], "payload": Jsonb(payload), **columns}
        updates = ", ".join(f"{name} = EXCLUDED.{name}" for name in column_names if name != "id")
        placeholders = ", ".join(f"%({name})s" for name in column_names)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {table} ({', '.join(column_names)}) VALUES ({placeholders}) "
                f"ON CONFLICT (id) DO UPDATE SET {updates}",
                values,
            )

    def get(self, table: str, record_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        self._validate_table(table)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT payload FROM {table} WHERE id = %s", (record_id,))
            row = cursor.fetchone()
            return row["payload"] if row else None

    def list(self, table: str, *, limit: int | None = None, offset: int = 0, order_by: str = "id") -> list[dict[str, Any]]:
        self.ensure_schema()
        self._validate_table(table)
        query = f"SELECT payload FROM {table} ORDER BY {order_by}"
        parameters: list[Any] = []
        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            parameters = [limit, offset]
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return [row["payload"] for row in cursor.fetchall()]

    def count(self, table: str, *, where: str = "", parameters: Iterable[Any] = ()) -> int:
        self.ensure_schema()
        self._validate_table(table)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table} {where}", list(parameters))
            return int(cursor.fetchone()["total"])

    def next_conversation_session_number(self) -> int:
        self.ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT GREATEST(nextval('conversation_session_number_seq'), "
                "COALESCE((SELECT MAX(session_number) + 1 FROM conversations), 1)) AS value"
            )
            return int(cursor.fetchone()["value"])

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _queue_params(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": payload["id"], "payload": Jsonb(payload), "created": payload.get("createdAt"),
            "updated": payload.get("updatedAt"), "status": payload["status"], "scheduled": payload.get("scheduledFor"),
        }

    @staticmethod
    def _validate_table(table: str) -> None:
        if table not in STATE_TABLES:
            raise ValueError(f"Unsupported persistence table: {table}")
