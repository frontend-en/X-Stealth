"""Safety policy for agent-controlled actions."""

from __future__ import annotations

from datetime import datetime, timezone

from src.agent.schemas import PolicyDecision
from src.api.schemas import QueueItem, RunRecord, ValidationResult
from src.config import Settings


class AgentPolicy:
    """Centralize backend-side gates for agent actions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def can_create_draft(self, validation: ValidationResult) -> PolicyDecision:
        if not self.settings.agent_enabled:
            return PolicyDecision(allowed=False, reason="Agent harness is disabled.", requiredActions=["Enable AGENT_ENABLED."])
        if not validation.valid:
            return PolicyDecision(allowed=False, reason="Draft text failed validation.", requiredActions=validation.errors)
        return PolicyDecision(allowed=True)

    def can_start_dry_run(self, queue_item: QueueItem | None) -> PolicyDecision:
        if not self.settings.agent_enabled:
            return PolicyDecision(allowed=False, reason="Agent harness is disabled.", requiredActions=["Enable AGENT_ENABLED."])
        if queue_item is None:
            return PolicyDecision(allowed=False, reason="Queue item was not found.")
        if queue_item.status == "blocked":
            return PolicyDecision(allowed=False, reason="Queue item is blocked by validation.")
        return PolicyDecision(allowed=True)

    def can_request_publish(
        self,
        queue_item: QueueItem | None,
        runs: list[RunRecord],
        *,
        confirm: bool,
        active_publish_allowed: bool,
        active_publish_reason: str | None,
    ) -> PolicyDecision:
        if not self.settings.agent_enabled:
            return PolicyDecision(allowed=False, reason="Agent harness is disabled.", requiredActions=["Enable AGENT_ENABLED."])
        if queue_item is None:
            return PolicyDecision(allowed=False, reason="Queue item was not found.")
        if queue_item.status != "approved":
            return PolicyDecision(
                allowed=False,
                reason="Queue item must be manually approved before publishing.",
                requiredActions=["Approve the queue item after a successful dry-run."],
            )
        if self.settings.agent_publish_requires_approval and not confirm:
            return PolicyDecision(allowed=False, reason="Publish approval is required.", requiredActions=["Pass confirm=true."])
        if not active_publish_allowed:
            return PolicyDecision(
                allowed=False,
                reason=active_publish_reason or "Publishing is not allowed.",
                requiredActions=self._required_actions_for_publish(),
            )
        if self.settings.agent_require_successful_dry_run_before_publish and not self._has_successful_dry_run(queue_item, runs):
            return PolicyDecision(
                allowed=False,
                reason="A successful dry-run is required after the latest draft change.",
                requiredActions=["Run a successful dry-run for this queue item."],
            )
        return PolicyDecision(allowed=True)

    def _has_successful_dry_run(self, queue_item: QueueItem, runs: list[RunRecord]) -> bool:
        changed_at = queue_item.updatedAt or queue_item.createdAt or datetime.min.replace(tzinfo=timezone.utc)
        for run in runs:
            if run.queueItemId != queue_item.id or run.mode != "dry_run" or run.status != "completed":
                continue
            if (run.startedAt or datetime.min.replace(tzinfo=timezone.utc)) >= changed_at:
                return True
        return False

    def _required_actions_for_publish(self) -> list[str]:
        actions: list[str] = []
        if self.settings.dry_run:
            actions.append("Set DRY_RUN=false.")
        if not self.settings.posting_enabled:
            actions.append("Set POSTING_ENABLED=true.")
        if not self.settings.auth_state_path.exists():
            actions.append("Create backend auth state for an owned account.")
        return actions
