"""Funnel tracking helpers for offer posts."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.api.schemas import QueueItem
from src.database import PostgresStore


class FunnelService:
    """Build UTM URLs and write append-only funnel events."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

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
            "id": f"funnel-{now.strftime('%Y%m%d-%H%M%S-%f')}",
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
        self.store.upsert("funnel_events", event, event_time=now)

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

    def _read_events(self) -> list[dict[str, object]]:
        return self.store.list("funnel_events", order_by="event_time ASC, id ASC")

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
