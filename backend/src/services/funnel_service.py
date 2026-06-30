"""Funnel tracking helpers for offer posts."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.api.schemas import QueueItem


class FunnelService:
    """Build UTM URLs and write append-only funnel events."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "posts.jsonl"

    def build_utm_url(self, item: QueueItem) -> str | None:
        if not item.targetUrl:
            return None
        return build_utm_url(
            item.targetUrl,
            campaign=item.utmCampaign or self.default_campaign(item),
            content=item.utmContent or item.id,
        )

    def log_event(
        self,
        item: QueueItem,
        *,
        status: str,
        run_id: str | None = None,
        quality_score: int | None = None,
        notes: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        event = {
            "time": now.isoformat(),
            "postId": item.id,
            "pillar": item.pillar,
            "ctaType": item.ctaType,
            "targetUrl": item.targetUrl,
            "utmCampaign": item.utmCampaign or self.default_campaign(item),
            "utmContent": item.utmContent or item.id,
            "utmUrl": self.build_utm_url(item),
            "status": status,
            "runId": run_id,
            "qualityScore": quality_score if quality_score is not None else item.qualityScore,
            "postedAt": item.postedAt.isoformat() if item.postedAt else None,
            "notes": notes if notes is not None else item.notes,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def export_csv(self) -> str:
        rows = self._read_events()
        output = StringIO()
        fieldnames = [
            "time",
            "postId",
            "pillar",
            "ctaType",
            "utmCampaign",
            "utmContent",
            "utmUrl",
            "status",
            "runId",
            "qualityScore",
            "postedAt",
            "notes",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
        return output.getvalue()

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    @staticmethod
    def default_campaign(item: QueueItem) -> str:
        return item.pillar or "offer_engine"


def build_utm_url(target_url: str, *, campaign: str, content: str) -> str:
    """Return target_url with the project's default X UTM parameters."""
    parsed = urlparse(target_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": "x",
            "utm_medium": "social",
            "utm_campaign": campaign,
            "utm_content": content,
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))
