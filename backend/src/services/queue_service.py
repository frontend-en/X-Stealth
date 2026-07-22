"""Queue service backed by the configured tweet text file."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.api.schemas import CtaType, PostPillar, QueueItem, QueueItemRisk, QueueItemStatus, ValidationResult
from src.tweet_source import FileTweetSource


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
    """Read queue items from the configured source."""

    def __init__(self, data_path: Path, queue_path: Path | None = None) -> None:
        self.data_path = data_path
        self.queue_path = queue_path

    def list_items(self, limit: int = 50, offset: int = 0) -> tuple[list[QueueItem], int]:
        items = self._load_items()
        return items[offset : offset + limit], len(items)

    def get_item(self, item_id: str) -> QueueItem | None:
        for item in self._load_items():
            if item.id == item_id:
                return item
        return None

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
        metadata: dict[str, Any] | None = None,
    ) -> QueueItem:
        """Create a writable queue item in the managed JSONL queue."""
        if self.queue_path is None:
            raise RuntimeError("Writable queue storage is not configured.")

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
        self._append_item(item, metadata=metadata, validation=validation)
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
        self._append_item(updated, validation=validation)
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

    def _load_items(self) -> list[QueueItem]:
        items_by_id = {item.id: item for item in self._load_legacy_items()}
        items_by_id.update({item.id: item for item in self._load_managed_items()})
        return sorted(
            items_by_id.values(),
            key=lambda item: item.createdAt or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    def _load_managed_items(self) -> list[QueueItem]:
        if self.queue_path is None or not self.queue_path.exists():
            return []

        latest: dict[str, QueueItem] = {}
        for line in self.queue_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                raw: dict[str, Any] = json.loads(line)
                latest[raw["id"]] = QueueItem.model_validate(raw)
            except (KeyError, json.JSONDecodeError, ValueError):
                continue
        return sorted(
            latest.values(),
            key=lambda item: item.createdAt or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    def _load_legacy_items(self) -> list[QueueItem]:
        source = FileTweetSource(self.data_path)
        loaded: list[QueueItem] = []
        index = 1

        while True:
            text = source.next_tweet()
            if text is None:
                break
            validation = validate_post_text(text)
            loaded.append(
                QueueItem(
                    id=f"tweet-{index:04d}",
                    text=text,
                    textLength=validation.textLength,
                    status="queued" if validation.valid else "blocked",
                    risk=risk_for_validation(validation),
                    source=self.data_path.as_posix(),
                    createdAt=None,
                    updatedAt=None,
                    scheduledFor=None,
                )
            )
            index += 1

        return loaded

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _make_item_id(self, now: datetime) -> str:
        existing_count = len(self._load_managed_items()) + 1
        return f"queue-{now.strftime('%Y%m%d-%H%M%S-%f')}-{existing_count:06d}"

    def _append_item(
        self,
        item: QueueItem,
        *,
        metadata: dict[str, Any] | None = None,
        validation: ValidationResult | None = None,
    ) -> None:
        if self.queue_path is None:
            raise RuntimeError("Writable queue storage is not configured.")
        record = item.model_dump(mode="json")
        if validation is not None:
            record["validation"] = validation.model_dump(mode="json")
        if metadata is not None:
            record["metadata"] = metadata
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        with self.queue_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _normalize_text(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()
