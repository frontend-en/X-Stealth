from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.services.funnel_service import build_utm_url
from src.services.quality_service import QualityService
from src.services.queue_service import QueueService


class OfferEngineTests(unittest.TestCase):
    def test_build_utm_url_preserves_existing_query(self) -> None:
        url = build_utm_url("https://example.com/checklist?ref=site", campaign="audit", content="post_1")
        self.assertIn("ref=site", url)
        self.assertIn("utm_source=x", url)
        self.assertIn("utm_medium=social", url)
        self.assertIn("utm_campaign=audit", url)
        self.assertIn("utm_content=post_1", url)

    def test_quality_gate_requires_offer_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = QueueService(Path(tmp) / "tweets.txt", Path(tmp) / "queue.jsonl")
            item = service.create_item("A useful post with no offer metadata.", source="test")

            result = QualityService().evaluate(item, service.list_items()[0])

            self.assertFalse(result.valid)
            self.assertIn("Post pillar is required.", result.errors)
            self.assertIn("Target URL is required.", result.errors)

    def test_queue_approval_requires_dry_run_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = QueueService(Path(tmp) / "tweets.txt", Path(tmp) / "queue.jsonl")
            item = service.create_item(
                "Why sites fail: unclear promise.\n\nChecklist:",
                source="test",
                pillar="errors",
                cta_type="checklist",
                target_url="https://example.com/checklist",
                utm_campaign="audit",
                utm_content="post_1",
            )

            with self.assertRaises(ValueError):
                service.approve_item(item.id)

            service.mark_dry_run_passed(item.id, run_id="run_1", quality_score=88, utm_url="https://example.com")
            approved = service.approve_item(item.id)

            self.assertIsNotNone(approved)
            self.assertEqual(approved.status, "approved")


if __name__ == "__main__":
    unittest.main()
