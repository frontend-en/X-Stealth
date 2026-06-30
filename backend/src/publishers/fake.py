"""Deterministic publisher for tests and local harness verification."""

from __future__ import annotations

from src.publishers.base import PublishResult


class FakePublisher:
    """Return a configured result without browser automation."""

    def __init__(self, result: PublishResult | None = None) -> None:
        self.result = result or PublishResult(success=True, message="Fake publish completed.")

    async def publish_once(self, text: str) -> PublishResult:
        return self.result
