from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.api.schemas import QueueItem
from src.services.queue_service import QueueService


class QueueServiceTests(unittest.TestCase):
    def test_managed_item_replaces_legacy_item_with_same_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_path = root / "tweets.txt"
            managed_path = root / "queue.jsonl"
            legacy_path.write_text("Legacy post\n", encoding="utf-8")

            managed_item = QueueItem(
                id="tweet-0001",
                text="Managed post state.",
                textLength=19,
                status="rejected",
                risk="low",
                source="test",
                createdAt=datetime(2026, 1, 1, tzinfo=timezone.utc),
                updatedAt=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
            managed_path.write_text(managed_item.model_dump_json() + "\n", encoding="utf-8")

            items, total = QueueService(legacy_path, managed_path).list_items()

            self.assertEqual(total, 1)
            self.assertEqual([item.id for item in items], ["tweet-0001"])
            self.assertEqual(items[0].text, "Managed post state.")
            self.assertEqual(items[0].status, "rejected")


if __name__ == "__main__":
    unittest.main()
