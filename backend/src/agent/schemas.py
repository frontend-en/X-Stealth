"""Internal schemas for the agent harness."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    """Allowlisted context assembled for agent requests."""

    role: str = ""
    rules: str = ""
    examples: str = ""
    memoryContext: str = ""
    memoryHistory: str = ""
    memoryMistakes: str = ""


class AgentEvent(BaseModel):
    """Append-only audit event for agent actions."""

    id: str
    type: Literal[
        "proposal_created",
        "draft_created",
        "validation_failed",
        "dry_run_requested",
        "dry_run_completed",
        "queue_item_approved",
        "queue_item_skipped",
        "queue_item_rejected",
        "publish_requested",
        "publish_blocked",
        "publish_started",
        "publish_completed",
        "publish_failed",
    ]
    time: datetime
    actor: str = "agent"
    queueItemId: str | None = None
    runId: str | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    """Policy decision for an agent action."""

    allowed: bool
    reason: str | None = None
    requiredActions: list[str] = Field(default_factory=list)
