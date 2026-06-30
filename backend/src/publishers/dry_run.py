"""Publisher adapter that validates without opening a browser."""

from __future__ import annotations

from src.publishers.base import PublishResult
from src.services.queue_service import validate_post_text


class DryRunPublisher:
    """Validate publish input and report the result without side effects."""

    async def publish_once(self, text: str) -> PublishResult:
        validation = validate_post_text(text)
        if not validation.valid:
            return PublishResult(success=False, message="; ".join(validation.errors))
        return PublishResult(success=True, message="Dry run completed. Publishing was skipped.")
