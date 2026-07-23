"""API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


QueueItemStatus = Literal[
    "queued",
    "draft",
    "blocked",
    "dry_run_passed",
    "approved",
    "posted",
    "skipped",
    "rejected",
    "failed",
    "dry_run_completed",
]
QueueItemRisk = Literal["low", "medium", "high"]
PostPillar = Literal["cases", "errors", "breakdowns", "mini_guides", "personal_experience"]
CtaType = Literal["checklist", "audit", "consultation", "template", "case_study", "newsletter", "none"]
RunMode = Literal["dry_run", "publish"]
RunStatus = Literal["queued", "running", "completed", "failed", "cancelled", "blocked"]
ArtifactType = Literal["log", "screenshot", "trace"]


class HealthResponse(BaseModel):
    status: str
    version: str
    time: datetime


class PasswordLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class AuthSessionResponse(BaseModel):
    authenticated: bool


class WarmupScrollRange(BaseModel):
    min: int
    max: int


class PublicSettingsResponse(BaseModel):
    dryRun: bool
    postingEnabled: bool
    headless: bool
    xBaseUrl: str
    dataPath: str
    logsDir: str
    screenshotsDir: str
    tracesDir: str
    minPostIntervalMinutes: int
    nextPublishAllowedAt: datetime | None = None
    warmupScrollRange: WarmupScrollRange
    hasAuthState: bool
    hasProxyConfigured: bool


class ValidationResult(BaseModel):
    valid: bool
    textLength: int
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QualityResult(ValidationResult):
    qualityScore: int = Field(default=0, ge=0, le=100)
    pillar: PostPillar | None = None
    ctaType: CtaType | None = None
    utmUrl: str | None = None


class QueueItem(BaseModel):
    id: str
    text: str
    textLength: int
    status: QueueItemStatus
    risk: QueueItemRisk
    source: str
    pillar: PostPillar | None = None
    ctaType: CtaType | None = None
    targetUrl: str | None = None
    utmCampaign: str | None = None
    utmContent: str | None = None
    utmUrl: str | None = None
    qualityScore: int | None = Field(default=None, ge=0, le=100)
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    scheduledFor: datetime | None = None
    approvedAt: datetime | None = None
    postedAt: datetime | None = None
    dryRunId: str | None = None
    notes: str = ""


class QueueListResponse(BaseModel):
    items: list[QueueItem]
    total: int


class QueueItemDetail(QueueItem):
    validation: ValidationResult
    quality: QualityResult | None = None
    runs: list["RunRecord"] = Field(default_factory=list)


class ValidatePostRequest(BaseModel):
    text: str = Field(default="", max_length=2000)


class CreateQueueItemRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    pillar: PostPillar | None = None
    ctaType: CtaType | None = None
    targetUrl: str | None = Field(default=None, max_length=2000)
    utmCampaign: str | None = Field(default=None, max_length=200)
    utmContent: str | None = Field(default=None, max_length=200)
    notes: str = Field(default="", max_length=2000)
    scheduledFor: datetime | None = None


class CreateQueueItemResponse(BaseModel):
    id: str
    status: QueueItemStatus


class UpdateQueueItemRequest(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    pillar: PostPillar | None = None
    ctaType: CtaType | None = None
    targetUrl: str | None = Field(default=None, max_length=2000)
    utmCampaign: str | None = Field(default=None, max_length=200)
    utmContent: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    scheduledFor: datetime | None = None


class Artifact(BaseModel):
    id: str
    type: ArtifactType
    name: str
    sizeBytes: int
    createdAt: datetime | None = None
    downloadUrl: str


class ArtifactListResponse(BaseModel):
    items: list[Artifact]


class LogEntry(BaseModel):
    level: str
    time: datetime | None = None
    message: str


class RunRecord(BaseModel):
    id: str
    queueItemId: str
    mode: RunMode
    status: RunStatus
    startedAt: datetime | None = None
    finishedAt: datetime | None = None
    message: str | None = None
    qualityScore: int | None = Field(default=None, ge=0, le=100)
    artifacts: list[Artifact] = Field(default_factory=list)


class RunListResponse(BaseModel):
    items: list[RunRecord]
    total: int


class RunDetail(RunRecord):
    logs: list[LogEntry] = Field(default_factory=list)


class StartRunRequest(BaseModel):
    queueItemId: str


class StartPublishRequest(StartRunRequest):
    confirm: bool = False


class StartRunResponse(BaseModel):
    runId: str
    status: RunStatus


class AgentCapabilities(BaseModel):
    canCreateDraft: bool
    canDryRun: bool
    canPublish: bool
    publishBlockedReason: str | None = None
    queueStorage: str
    requiresHumanApprovalForPublish: bool


class AgentProposalRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    pillar: PostPillar | None = None
    ctaType: CtaType | None = None
    targetUrl: str | None = Field(default=None, max_length=2000)
    utmCampaign: str | None = Field(default=None, max_length=200)
    utmContent: str | None = Field(default=None, max_length=200)
    sourcePrompt: str | None = Field(default=None, max_length=2000)


class DraftProposal(BaseModel):
    proposalId: str
    text: str
    validation: QualityResult
    recommendedAction: Literal["create_draft", "revise", "block"]


class CreateAgentDraftRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    pillar: PostPillar | None = None
    ctaType: CtaType | None = None
    targetUrl: str | None = Field(default=None, max_length=2000)
    utmCampaign: str | None = Field(default=None, max_length=200)
    utmContent: str | None = Field(default=None, max_length=200)
    sourcePrompt: str | None = Field(default=None, max_length=2000)
    reviewRequired: bool = True


class AgentDraftResponse(BaseModel):
    id: str
    status: QueueItemStatus
    validation: QualityResult


class AgentPublishRequest(BaseModel):
    queueItemId: str
    confirm: bool = False
    approvalNote: str | None = Field(default=None, max_length=1000)


class AgentPublishDecision(BaseModel):
    allowed: bool
    reason: str | None = None
    requiredActions: list[str] = Field(default_factory=list)
    runId: str | None = None
    status: RunStatus | None = None


PipelineRunStatus = Literal["queued", "running", "completed", "failed", "interrupted"]
PipelineStageStatus = Literal["pending", "running", "completed", "failed"]
ChatRole = Literal["user", "assistant"]


class Conversation(BaseModel):
    id: str
    sessionNumber: int = Field(ge=1)
    title: str
    createdAt: datetime
    updatedAt: datetime
    deletedAt: datetime | None = None


class ChatMessage(BaseModel):
    id: str
    conversationId: str
    role: ChatRole
    content: str = Field(max_length=4000)
    createdAt: datetime
    pipelineRunId: str | None = None


class PipelineArtifact(BaseModel):
    type: Literal["source", "agent_output"] = "source"
    title: str
    url: str | None = None
    publishedAt: str | None = None
    summary: str = ""


class PostCandidate(BaseModel):
    id: str
    text: str = Field(max_length=280)
    score: int = Field(ge=0, le=100)
    rationale: str = ""
    warnings: list[str] = Field(default_factory=list)


class PipelineStage(BaseModel):
    id: str
    name: str
    role: str
    status: PipelineStageStatus = "pending"
    summary: str = ""
    output: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[PipelineArtifact] = Field(default_factory=list)
    startedAt: datetime | None = None
    finishedAt: datetime | None = None
    error: str | None = None


class PipelineRun(BaseModel):
    id: str
    conversationId: str
    messageId: str
    status: PipelineRunStatus = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    stages: list[PipelineStage]
    candidates: list[PostCandidate] = Field(default_factory=list)
    finalRecommendation: str = ""
    createdAt: datetime
    updatedAt: datetime
    completedAt: datetime | None = None


class ConversationDetail(Conversation):
    messages: list[ChatMessage] = Field(default_factory=list)
    runs: list[PipelineRun] = Field(default_factory=list)


class ConversationSummary(Conversation):
    lastMessagePreview: str = ""
    lastRunStatus: PipelineRunStatus | None = None


class ConversationListResponse(BaseModel):
    items: list[ConversationSummary] = Field(default_factory=list)
    total: int = 0


class CreateConversationRequest(BaseModel):
    title: str = Field(default="Новый AI-диалог", min_length=1, max_length=120)


class CreateConversationResponse(BaseModel):
    id: str
    sessionNumber: int


class CreateChatMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class StartPipelineResponse(BaseModel):
    messageId: str
    pipelineRunId: str


class CreatePipelineDraftRequest(BaseModel):
    candidateId: str
    pillar: PostPillar | None = None
    ctaType: CtaType | None = None
    targetUrl: str | None = Field(default=None, max_length=2000)
    utmCampaign: str | None = Field(default=None, max_length=200)
    utmContent: str | None = Field(default=None, max_length=200)


class CreatePipelineDraftResponse(BaseModel):
    id: str
    status: QueueItemStatus
