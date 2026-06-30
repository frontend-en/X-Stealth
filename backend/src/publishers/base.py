"""Publisher protocol shared by run execution adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PublishResult:
    """Result returned by publisher adapters."""

    success: bool
    message: str | None = None


class Publisher(Protocol):
    """Executor that can attempt one publish operation."""

    async def publish_once(self, text: str) -> PublishResult:
        """Publish or simulate publishing one post."""
