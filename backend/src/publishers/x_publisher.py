"""Publisher adapter backed by the browser automation client."""

from __future__ import annotations

from src.config import Settings
from src.publishers.base import PublishResult
from src.x_bot import XBot


class XPublisher:
    """Delegate real publish execution to XBot."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def publish_once(self, text: str) -> PublishResult:
        await XBot(self.settings).run_once(text)
        return PublishResult(success=True, message="Publish run completed.")
