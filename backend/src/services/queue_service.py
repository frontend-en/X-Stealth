"""PostgreSQL-backed queue service."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from src.api.schemas import CtaType, PostPillar, QueueItem, QueueItemRisk, QueueItemStatus, ValidationResult
from src.database import PostgresStore


CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate_post_text(text: str) -> ValidationResult:
    """Validate post text before a run."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    errors: list[str] = []
    warnings: list[str] = []

    if not normalized.strip():
        errors.append("Post text is empty.")
    if len(normalized) > 280:
        errors.append("Post text exceeds 280 characters.")
    if CONTROL_CHARS_RE.search(normalized):
        errors.append("Post text contains unsupported control characters.")
    if "  " in normalized:
        warnings.append("Post text contains repeated spaces.")

    return ValidationResult(
        valid=not errors,
        textLength=len(normalized),
        errors=errors,
        warnings=warnings,
    )


def risk_for_validation(validation: ValidationResult) -> QueueItemRisk:
    """Map validation output to dashboard risk."""
    if validation.errors:
        return "high"
    if validation.warnings:
        return "medium"
    return "low"


class QueueService:
    """Manage queue items persisted in PostgreSQL."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def list_items(self, limit: int = 50, offset: int = 0) -> tuple[list[QueueItem], int]:
        rows, total = self.store.queue_items(limit=limit, offset=offset)
        return [QueueItem.model_validate(row) for row in rows], total

    def get_item(self, item_id: str) -> QueueItem | None:
        row = self.store.queue_item(item_id)
        return QueueItem.model_validate(row) if row else None

    def get_text(self, item_id: str) -> str | None:
        item = self.get_item(item_id)
        return item.text if item else None

    def create_item(
        self,
        text: str,
        *,
        source: str = "agent",
        scheduled_for=None,
        pillar: PostPillar | None = None,
        cta_type: CtaType | None = None,
        target_url: str | None = None,
        utm_campaign: str | None = None,
        utm_content: str | None = None,
        notes: str = "",
    ) -> QueueItem:
        """Create a queue item in PostgreSQL."""

        now = self._now()
        validation = validate_post_text(text)
        status = "draft" if validation.valid else "blocked"
        item = QueueItem(
            id=self._make_item_id(now),
            text=text.replace("\r\n", "\n").replace("\r", "\n").strip(),
            textLength=validation.textLength,
            status=status,
            risk=risk_for_validation(validation),
            source=source,
            pillar=pillar,
            ctaType=cta_type,
            targetUrl=target_url,
            utmCampaign=utm_campaign,
            utmContent=utm_content,
            notes=notes,
            createdAt=now,
            updatedAt=now,
            scheduledFor=scheduled_for,
        )
        self._append_item(item)
        return item

    def update_item(
        self,
        item_id: str,
        *,
        text: str | None = None,
        pillar: PostPillar | None = None,
        cta_type: CtaType | None = None,
        target_url: str | None = None,
        utm_campaign: str | None = None,
        utm_content: str | None = None,
        notes: str | None = None,
        scheduled_for=None,
    ) -> QueueItem | None:
        item = self.get_item(item_id)
        if item is None:
            return None

        next_text = self._normalize_text(text) if text is not None else item.text
        validation = validate_post_text(next_text)
        status: QueueItemStatus = "blocked" if not validation.valid else "queued"
        updated = item.model_copy(
            update={
                "text": next_text,
                "textLength": validation.textLength,
                "status": status,
                "risk": risk_for_validation(validation),
                "pillar": pillar if pillar is not None else item.pillar,
                "ctaType": cta_type if cta_type is not None else item.ctaType,
                "targetUrl": target_url if target_url is not None else item.targetUrl,
                "utmCampaign": utm_campaign if utm_campaign is not None else item.utmCampaign,
                "utmContent": utm_content if utm_content is not None else item.utmContent,
                "notes": notes if notes is not None else item.notes,
                "scheduledFor": scheduled_for if scheduled_for is not None else item.scheduledFor,
                "updatedAt": self._now(),
                "approvedAt": None,
                "dryRunId": None,
                "qualityScore": None,
            }
        )
        self._append_item(updated)
        return updated

    def mark_dry_run_passed(self, item_id: str, *, run_id: str, quality_score: int, utm_url: str | None) -> QueueItem | None:
        return self._set_state(
            item_id,
            "dry_run_passed",
            dryRunId=run_id,
            qualityScore=quality_score,
            utmUrl=utm_url,
        )

    def approve_item(self, item_id: str) -> QueueItem | None:
        item = self.get_item(item_id)
        if item is None:
            return None
        if item.status != "dry_run_passed":
            raise ValueError("Queue item must pass dry-run before approval.")
        return self._set_state(item_id, "approved", approvedAt=self._now())

    def skip_item(self, item_id: str) -> QueueItem | None:
        return self._set_state(item_id, "skipped")

    def reject_item(self, item_id: str) -> QueueItem | None:
        return self._set_state(item_id, "rejected")

    def mark_posted(self, item_id: str) -> QueueItem | None:
        return self._set_state(item_id, "posted", postedAt=self._now())

    def _set_state(self, item_id: str, status: QueueItemStatus, **updates: Any) -> QueueItem | None:
        item = self.get_item(item_id)
        if item is None:
            return None
        updated = item.model_copy(update={"status": status, "updatedAt": self._now(), **updates})
        self._append_item(updated)
        return updated

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _make_item_id(self, now: datetime) -> str:
        existing_count = self.store.count("queue_items") + 1
        return f"queue-{now.strftime('%Y%m%d-%H%M%S-%f')}-{existing_count:06d}"

    def _append_item(
        self,
        item: QueueItem,
    ) -> None:
        self.store.upsert_queue_item(item.model_dump(mode="json"))

    @staticmethod
    def _normalize_text(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()
