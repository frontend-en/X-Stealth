"""Load allowlisted project context for the agent harness."""

from __future__ import annotations

from pathlib import Path

from src.agent.schemas import AgentContext
from src.config import PROJECT_ROOT


class AgentContextLoader:
    """Read bounded markdown context from the agent workspace."""

    def __init__(self, root: Path = PROJECT_ROOT / "agent", max_chars_per_file: int = 8000) -> None:
        self.root = root
        self.max_chars_per_file = max_chars_per_file

    def load(self) -> AgentContext:
        return AgentContext(
            role=self._read("config/role.md"),
            rules=self._read("config/rules.md"),
            examples=self._read("config/examples.md"),
            memoryContext=self._read("memory/context.md"),
            memoryHistory=self._read("memory/history.md"),
            memoryMistakes=self._read("memory/mistakes.md"),
        )

    def _read(self, relative_path: str) -> str:
        path = (self.root / relative_path).resolve()
        root = self.root.resolve()
        if root not in (path, *path.parents) or not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")[: self.max_chars_per_file]
