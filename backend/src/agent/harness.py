"""High-level agent orchestration layer."""

from __future__ import annotations

from datetime import datetime, timezone

from src.agent.context_loader import AgentContextLoader
from src.agent.events import AgentEventWriter
from src.agent.policy import AgentPolicy
from src.api.schemas import (
    AgentCapabilities,
    AgentDraftResponse,
    AgentPublishDecision,
    AgentPublishRequest,
    AgentProposalRequest,
    ArtifactListResponse,
    CreateAgentDraftRequest,
    DraftProposal,
    QueueListResponse,
    RunDetail,
    RunRecord,
    QueueItem,
)
from src.config import Settings
from src.database import PostgresStore
from src.services.quality_service import QualityService
from src.services.artifact_service import ArtifactService
from src.services.queue_service import QueueService, validate_post_text
from src.services.run_service import RunService


class AgentHarness:
    """Facade used by API routes and future external agent adapters."""

    def __init__(
        self,
        settings: Settings,
        queue_service: QueueService,
        run_service: RunService,
        artifact_service: ArtifactService,
        context_loader: AgentContextLoader | None = None,
        event_writer: AgentEventWriter | None = None,
        store: PostgresStore | None = None,
    ) -> None:
        self.settings = settings
        self.queue_service = queue_service
        self.run_service = run_service
        self.artifact_service = artifact_service
        self.context_loader = context_loader or AgentContextLoader()
        self.events = event_writer or AgentEventWriter(settings, store)
        self.policy = AgentPolicy(settings)
        self.quality_service = QualityService()

    def get_capabilities(self) -> AgentCapabilities:
        allowed, reason = self.run_service.can_start_publish()
        can_publish = self.settings.agent_enabled and allowed
        return AgentCapabilities(
            canCreateDraft=self.settings.agent_enabled,
            canDryRun=self.settings.agent_enabled,
            canPublish=can_publish,
            publishBlockedReason=None if can_publish else reason or "Agent harness is disabled.",
            queueStorage="postgresql",
            requiresHumanApprovalForPublish=self.settings.agent_publish_requires_approval,
        )

    def list_queue(self, limit: int = 50, offset: int = 0) -> QueueListResponse:
        items, total = self.queue_service.list_items(limit=limit, offset=offset)
        return QueueListResponse(items=items, total=total)

    def propose_post(self, request: AgentProposalRequest) -> DraftProposal:
        self.context_loader.load()
        proposal_id = self._make_id("proposal")
        item = self._request_to_item(
            proposal_id,
            request.text,
            pillar=request.pillar,
            cta_type=request.ctaType,
            target_url=request.targetUrl,
            utm_campaign=request.utmCampaign,
            utm_content=request.utmContent,
            source="agent_proposal",
        )
        validation = self.quality_service.evaluate(item, self.queue_service.list_items(limit=200)[0])
        if validation.errors:
            recommended_action = "block"
        elif validation.warnings:
            recommended_action = "revise"
        else:
            recommended_action = "create_draft"
        proposal = DraftProposal(
            proposalId=proposal_id,
            text=item.text,
            validation=validation,
            recommendedAction=recommended_action,
        )
        self.events.write(
            "proposal_created",
            "Agent proposal created.",
            details={
                "textLength": validation.textLength,
                "valid": validation.valid,
                "recommendedAction": recommended_action,
            },
        )
        return proposal

    def create_draft(self, request: CreateAgentDraftRequest) -> AgentDraftResponse:
        text = self._normalize_text(request.text)
        preview = self._request_to_item(
            self._make_id("draft-preview"),
            text,
            pillar=request.pillar,
            cta_type=request.ctaType,
            target_url=request.targetUrl,
            utm_campaign=request.utmCampaign,
            utm_content=request.utmContent,
            source="agent",
        )
        validation = self.quality_service.evaluate(preview, self.queue_service.list_items(limit=200)[0])
        decision = self.policy.can_create_draft(validation)
        if not decision.allowed:
            self.events.write(
                "validation_failed",
                decision.reason or "Draft validation failed.",
                details={"errors": validation.errors, "warnings": validation.warnings},
            )
            raise ValueError(decision.reason or "Draft validation failed.")

        item = self.queue_service.create_item(
            text,
            source="agent",
            pillar=request.pillar,
            cta_type=request.ctaType,
            target_url=request.targetUrl,
            utm_campaign=request.utmCampaign,
            utm_content=request.utmContent,
        )
        self.events.write(
            "draft_created",
            "Agent draft created.",
            queue_item_id=item.id,
            details={"textLength": validation.textLength, "reviewRequired": request.reviewRequired},
        )
        return AgentDraftResponse(id=item.id, status=item.status, validation=validation)

    def start_dry_run(self, queue_item_id: str) -> RunRecord:
        item = self.queue_service.get_item(queue_item_id)
        decision = self.policy.can_start_dry_run(item)
        if not decision.allowed:
            self.events.write("validation_failed", decision.reason or "Dry-run blocked.", queue_item_id=queue_item_id)
            raise ValueError(decision.reason or "Dry-run blocked.")
        self.events.write("dry_run_requested", "Agent dry-run requested.", queue_item_id=queue_item_id)
        run = self.run_service.start_dry_run(queue_item_id)
        self.events.write(
            "dry_run_completed",
            "Agent dry-run completed.",
            queue_item_id=queue_item_id,
            run_id=run.id,
            details={"status": run.status, "message": run.message},
        )
        return run

    def get_run(self, run_id: str) -> RunDetail | None:
        return self.run_service.get_run(run_id)

    def list_artifacts(self, limit: int = 50) -> ArtifactListResponse:
        return ArtifactListResponse(items=self.artifact_service.list_artifacts(limit=limit))

    def request_publish(self, request: AgentPublishRequest) -> AgentPublishDecision:
        item = self.queue_service.get_item(request.queueItemId)
        runs = [run for run in self.run_service.list_runs(limit=200) if run.queueItemId == request.queueItemId]
        active_allowed, active_reason = self.run_service.can_start_publish(request.queueItemId)
        decision = self.policy.can_request_publish(
            item,
            runs,
            confirm=request.confirm,
            active_publish_allowed=active_allowed,
            active_publish_reason=active_reason,
        )
        self.events.write(
            "publish_requested",
            "Agent publish requested.",
            queue_item_id=request.queueItemId,
            details={"allowed": decision.allowed, "approvalNote": request.approvalNote},
        )
        if not decision.allowed:
            self.events.write(
                "publish_blocked",
                decision.reason or "Publish blocked.",
                queue_item_id=request.queueItemId,
                details={"requiredActions": decision.requiredActions},
            )
            return AgentPublishDecision(
                allowed=False,
                reason=decision.reason,
                requiredActions=decision.requiredActions,
            )
        run = self.run_service.start_publish(request.queueItemId)
        return AgentPublishDecision(allowed=True, runId=run.id, status=run.status)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()

    @staticmethod
    def _make_id(prefix: str) -> str:
        now = datetime.now(timezone.utc)
        return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S-%f')}"

    def _request_to_item(
        self,
        item_id: str,
        text: str,
        *,
        pillar,
        cta_type,
        target_url,
        utm_campaign,
        utm_content,
        source: str,
    ) -> QueueItem:
        normalized = self._normalize_text(text)
        validation = validate_post_text(normalized)
        now = datetime.now(timezone.utc)
        return QueueItem(
            id=item_id,
            text=normalized,
            textLength=validation.textLength,
            status="draft" if validation.valid else "blocked",
            risk="low" if validation.valid else "high",
            source=source,
            pillar=pillar,
            ctaType=cta_type,
            targetUrl=target_url,
            utmCampaign=utm_campaign,
            utmContent=utm_content,
            createdAt=now,
            updatedAt=now,
        )
