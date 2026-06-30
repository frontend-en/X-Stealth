"""Tweet source abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TweetSource(ABC):
    """Source that returns text to publish."""

    @abstractmethod
    def next_tweet(self) -> str | None:
        """Return the next tweet text or None when the source is empty."""


class FileTweetSource(TweetSource):
    """Reads tweets from a plain text file.

    Blank lines and lines starting with # are ignored. Multi-line posts can be
    separated with a line containing only ---.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._items = self._load_items()
        self._index = 0

    def next_tweet(self) -> str | None:
        if self._index >= len(self._items):
            return None
        item = self._items[self._index]
        self._index += 1
        return item

    def _load_items(self) -> list[str]:
        if not self.path.exists():
            return []

        raw = self.path.read_text(encoding="utf-8")
        chunks: list[list[str]] = [[]]
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped == "---":
                chunks.append([])
                continue
            if not stripped or stripped.startswith("#"):
                continue
            chunks[-1].append(line.rstrip())

        return ["\n".join(chunk).strip() for chunk in chunks if "\n".join(chunk).strip()]
