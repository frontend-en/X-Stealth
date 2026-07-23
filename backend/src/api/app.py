"""FastAPI app for the dashboard integration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from src.api.auth import DashboardAuth
from src.api.errors import api_error
from src.api.schemas import (
    AgentCapabilities,
    AgentDraftResponse,
    AgentPublishDecision,
    AgentPublishRequest,
    AuthSessionResponse,
    AgentProposalRequest,
    ArtifactListResponse,
    ArtifactType,
    CreateQueueItemRequest,
    CreateQueueItemResponse,
    ConversationDetail,
    CreateChatMessageRequest,
    CreateConversationRequest,
    CreateConversationResponse,
    ConversationListResponse,
    CreatePipelineDraftRequest,
    CreatePipelineDraftResponse,
    PipelineRun,
    PasswordLoginRequest,
    StartPipelineResponse,
    CreateAgentDraftRequest,
    DraftProposal,
    HealthResponse,
    QueueItemDetail,
    QueueListResponse,
    RunDetail,
    RunListResponse,
    StartPublishRequest,
    StartRunRequest,
    StartRunResponse,
    UpdateQueueItemRequest,
    ValidatePostRequest,
    ValidationResult,
)
from src.agent.harness import AgentHarness
from src.agent.pipeline import PipelineOrchestrator
from src.config import Settings, load_settings
from src.database import PostgresStore
from src.logging_config import setup_logging
from src.services.artifact_service import ArtifactService
from src.services.funnel_service import FunnelService
from src.services.quality_service import QualityService
from src.services.queue_service import QueueService, validate_post_text
from src.services.run_service import RunService
from src.services.settings_service import get_public_settings


def _cors_origins() -> list[str]:
    local_origins = {"http://127.0.0.1:5173", "http://localhost:5173"}
    configured_origins = {
        origin.strip()
        for origin in load_settings().cors_origins.split(",")
        if origin.strip()
    }
    return sorted(local_origins | configured_origins)


app = FastAPI(title="X Stealth AutoPoster API", version="0.1.0")
app.state.dashboard_auth = DashboardAuth()

AUTH_COOKIE_NAME = "x_autoposter_session"
PUBLIC_API_PATHS = frozenset({"/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/session"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_dashboard_session(request: Request, call_next):
    """Fail closed for every dashboard endpoint except the login probe."""
    if (
        request.method == "OPTIONS"
        or not request.url.path.startswith("/api/v1/")
        or request.url.path in PUBLIC_API_PATHS
    ):
        return await call_next(request)

    auth: DashboardAuth = app.state.dashboard_auth
    if auth.is_valid_session(request.cookies.get(AUTH_COOKIE_NAME)):
        return await call_next(request)

    return JSONResponse(
        status_code=401,
        content={"detail": {"error": {"code": "AUTH_REQUIRED", "message": "Authentication is required.", "details": {}}}},
    )


def get_settings() -> Settings:
    settings = load_settings()
    setup_logging(settings.log_level, settings.logs_dir)
    return settings


def get_dashboard_auth() -> DashboardAuth:
    return app.state.dashboard_auth


def get_store(settings: Annotated[Settings, Depends(get_settings)]) -> PostgresStore:
    if not hasattr(app.state, "store"):
        store = PostgresStore(settings.database_url)
        store.ensure_schema()
        queue = QueueService(store)
        run_service = RunService(settings, queue, ArtifactService(settings), store=store)
        app.state.store = store
    return app.state.store


def get_queue_service(
    settings: Annotated[Settings, Depends(get_settings)], store: Annotated[PostgresStore, Depends(get_store)]
) -> QueueService:
    return QueueService(store)


def get_artifact_service(settings: Annotated[Settings, Depends(get_settings)]) -> ArtifactService:
    return ArtifactService(settings)


def get_quality_service() -> QualityService:
    return QualityService()


def get_funnel_service(
    settings: Annotated[Settings, Depends(get_settings)], store: Annotated[PostgresStore, Depends(get_store)]
) -> FunnelService:
    return FunnelService(store)


def get_run_service(
    settings: Annotated[Settings, Depends(get_settings)],
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    store: Annotated[PostgresStore, Depends(get_store)],
) -> RunService:
    if not hasattr(app.state, "run_service"):
        app.state.run_service = RunService(settings, queue_service, artifact_service, store=store)
    return app.state.run_service


def get_agent_harness(
    settings: Annotated[Settings, Depends(get_settings)],
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
    run_service: Annotated[RunService, Depends(get_run_service)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    store: Annotated[PostgresStore, Depends(get_store)],
) -> AgentHarness:
    return AgentHarness(settings, queue_service, run_service, artifact_service, store=store)


def get_pipeline_orchestrator(
    settings: Annotated[Settings, Depends(get_settings)],
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
    store: Annotated[PostgresStore, Depends(get_store)],
) -> PipelineOrchestrator:
    if not hasattr(app.state, "pipeline_orchestrator"):
        app.state.pipeline_orchestrator = PipelineOrchestrator(settings, queue_service, store=store)
    return app.state.pipeline_orchestrator


@app.get("/api/v1/health", response_model=HealthResponse)
def health(_: Annotated[PostgresStore, Depends(get_store)]) -> HealthResponse:
    return HealthResponse(status="ok", version=app.version, time=datetime.now(timezone.utc))


@app.post("/api/v1/auth/login", response_model=AuthSessionResponse)
def login(
    request: PasswordLoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[DashboardAuth, Depends(get_dashboard_auth)],
) -> Response:
    if not settings.dashboard_password:
        raise api_error(503, "AUTH_NOT_CONFIGURED", "DASHBOARD_PASSWORD is not configured.")
    if not auth.password_matches(request.password, settings.dashboard_password):
        raise api_error(401, "INVALID_PASSWORD", "The password is incorrect.")

    response = JSONResponse(content=AuthSessionResponse(authenticated=True).model_dump())
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=auth.create_session(settings.auth_session_ttl_minutes),
        max_age=settings.auth_session_ttl_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@app.get("/api/v1/auth/session", response_model=AuthSessionResponse)
def auth_session(request: Request, auth: Annotated[DashboardAuth, Depends(get_dashboard_auth)]) -> AuthSessionResponse:
    return AuthSessionResponse(authenticated=auth.is_valid_session(request.cookies.get(AUTH_COOKIE_NAME)))


@app.post("/api/v1/auth/logout", response_model=AuthSessionResponse)
def logout(request: Request, auth: Annotated[DashboardAuth, Depends(get_dashboard_auth)]) -> Response:
    auth.revoke_session(request.cookies.get(AUTH_COOKIE_NAME))
    response = JSONResponse(content=AuthSessionResponse(authenticated=False).model_dump())
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
    return response


@app.get("/api/v1/settings")
def settings(
    settings_obj: Annotated[Settings, Depends(get_settings)],
    run_service: Annotated[RunService, Depends(get_run_service)],
):
    return get_public_settings(
        settings_obj,
        next_publish_allowed_at=run_service.next_publish_allowed_at(),
    )


@app.get("/api/v1/queue", response_model=QueueListResponse)
def list_queue(
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QueueListResponse:
    items, total = queue_service.list_items(limit=limit, offset=offset)
    return QueueListResponse(items=items, total=total)


@app.get("/api/v1/queue/{item_id}", response_model=QueueItemDetail)
def get_queue_item(
    item_id: str,
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
    run_service: Annotated[RunService, Depends(get_run_service)],
    quality_service: Annotated[QualityService, Depends(get_quality_service)],
) -> QueueItemDetail:
    item = queue_service.get_item(item_id)
    if item is None:
        raise api_error(404, "NOT_FOUND", "Queue item was not found.", {"itemId": item_id})
    runs = [run for run in run_service.list_runs(limit=200) if run.queueItemId == item_id]
    return QueueItemDetail(
        **item.model_dump(),
        validation=validate_post_text(item.text),
        quality=quality_service.evaluate(item, queue_service.list_items(limit=200)[0]),
        runs=runs,
    )


@app.post("/api/v1/queue/validate", response_model=ValidationResult)
def validate_queue_item(request: ValidatePostRequest) -> ValidationResult:
    return validate_post_text(request.text)


@app.post("/api/v1/queue", response_model=CreateQueueItemResponse)
def create_queue_item(
    request: CreateQueueItemRequest,
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
) -> CreateQueueItemResponse:
    item = queue_service.create_item(
        request.text,
        source="api",
        scheduled_for=request.scheduledFor,
        pillar=request.pillar,
        cta_type=request.ctaType,
        target_url=request.targetUrl,
        utm_campaign=request.utmCampaign,
        utm_content=request.utmContent,
        notes=request.notes,
    )
    return CreateQueueItemResponse(id=item.id, status=item.status)


@app.patch("/api/v1/queue/{item_id}", response_model=QueueItemDetail)
def update_queue_item(
    item_id: str,
    request: UpdateQueueItemRequest,
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
    run_service: Annotated[RunService, Depends(get_run_service)],
    quality_service: Annotated[QualityService, Depends(get_quality_service)],
) -> QueueItemDetail:
    item = queue_service.update_item(
        item_id,
        text=request.text,
        pillar=request.pillar,
        cta_type=request.ctaType,
        target_url=request.targetUrl,
        utm_campaign=request.utmCampaign,
        utm_content=request.utmContent,
        notes=request.notes,
        scheduled_for=request.scheduledFor,
    )
    if item is None:
        raise api_error(404, "NOT_FOUND", "Queue item was not found.", {"itemId": item_id})
    runs = [run for run in run_service.list_runs(limit=200) if run.queueItemId == item_id]
    return QueueItemDetail(
        **item.model_dump(),
        validation=validate_post_text(item.text),
        quality=quality_service.evaluate(item, queue_service.list_items(limit=200)[0]),
        runs=runs,
    )


@app.post("/api/v1/queue/{item_id}/approve", response_model=QueueItemDetail)
def approve_queue_item(
    item_id: str,
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
    run_service: Annotated[RunService, Depends(get_run_service)],
    quality_service: Annotated[QualityService, Depends(get_quality_service)],
) -> QueueItemDetail:
    try:
        item = queue_service.approve_item(item_id)
    except ValueError as exc:
        raise api_error(409, "APPROVAL_BLOCKED", str(exc), {"itemId": item_id}) from exc
    if item is None:
        raise api_error(404, "NOT_FOUND", "Queue item was not found.", {"itemId": item_id})
    runs = [run for run in run_service.list_runs(limit=200) if run.queueItemId == item_id]
    return QueueItemDetail(
        **item.model_dump(),
        validation=validate_post_text(item.text),
        quality=quality_service.evaluate(item, queue_service.list_items(limit=200)[0]),
        runs=runs,
    )


@app.post("/api/v1/queue/{item_id}/skip", response_model=QueueItemDetail)
def skip_queue_item(
    item_id: str,
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
    run_service: Annotated[RunService, Depends(get_run_service)],
    quality_service: Annotated[QualityService, Depends(get_quality_service)],
) -> QueueItemDetail:
    item = queue_service.skip_item(item_id)
    if item is None:
        raise api_error(404, "NOT_FOUND", "Queue item was not found.", {"itemId": item_id})
    runs = [run for run in run_service.list_runs(limit=200) if run.queueItemId == item_id]
    return QueueItemDetail(
        **item.model_dump(),
        validation=validate_post_text(item.text),
        quality=quality_service.evaluate(item, queue_service.list_items(limit=200)[0]),
        runs=runs,
    )


@app.post("/api/v1/queue/{item_id}/reject", response_model=QueueItemDetail)
def reject_queue_item(
    item_id: str,
    queue_service: Annotated[QueueService, Depends(get_queue_service)],
    run_service: Annotated[RunService, Depends(get_run_service)],
    quality_service: Annotated[QualityService, Depends(get_quality_service)],
) -> QueueItemDetail:
    item = queue_service.reject_item(item_id)
    if item is None:
        raise api_error(404, "NOT_FOUND", "Queue item was not found.", {"itemId": item_id})
    runs = [run for run in run_service.list_runs(limit=200) if run.queueItemId == item_id]
    return QueueItemDetail(
        **item.model_dump(),
        validation=validate_post_text(item.text),
        quality=quality_service.evaluate(item, queue_service.list_items(limit=200)[0]),
        runs=runs,
    )


@app.get("/api/v1/runs", response_model=RunListResponse)
def list_runs(
    run_service: Annotated[RunService, Depends(get_run_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RunListResponse:
    items = run_service.list_runs(limit=limit)
    return RunListResponse(items=items, total=len(items))


@app.get("/api/v1/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, run_service: Annotated[RunService, Depends(get_run_service)]) -> RunDetail:
    run = run_service.get_run(run_id)
    if run is None:
        raise api_error(404, "NOT_FOUND", "Run was not found.", {"runId": run_id})
    return run


@app.post("/api/v1/runs/dry-run", response_model=StartRunResponse)
def start_dry_run(request: StartRunRequest, run_service: Annotated[RunService, Depends(get_run_service)]):
    run = run_service.start_dry_run(request.queueItemId)
    return StartRunResponse(runId=run.id, status=run.status)


@app.post("/api/v1/runs/publish", response_model=StartRunResponse)
async def start_publish(request: StartPublishRequest, run_service: Annotated[RunService, Depends(get_run_service)]):
    if not request.confirm:
        raise api_error(400, "VALIDATION_ERROR", "Publish confirmation is required.", {"field": "confirm"})
    allowed, reason = run_service.can_start_publish(request.queueItemId)
    if not allowed:
        raise api_error(409, "POSTING_DISABLED", reason or "Publishing is disabled.")
    run = run_service.start_publish(request.queueItemId)
    return StartRunResponse(runId=run.id, status=run.status)


@app.get("/api/v1/artifacts", response_model=ArtifactListResponse)
def list_artifacts(
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    type: ArtifactType | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ArtifactListResponse:
    return ArtifactListResponse(items=artifact_service.list_artifacts(artifact_type=type, limit=limit))


@app.get("/api/v1/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)]):
    path = artifact_service.resolve_artifact_path(artifact_id)
    if path is None:
        raise api_error(404, "ARTIFACT_NOT_ALLOWED", "Artifact was not found or is not allowed.")
    return FileResponse(path)


@app.get("/api/v1/funnel/export.csv")
def export_funnel_csv(funnel_service: Annotated[FunnelService, Depends(get_funnel_service)]):
    return Response(
        content=funnel_service.export_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="funnel-export.csv"'},
    )


@app.get("/api/v1/agent/capabilities", response_model=AgentCapabilities)
def agent_capabilities(harness: Annotated[AgentHarness, Depends(get_agent_harness)]) -> AgentCapabilities:
    return harness.get_capabilities()


@app.post("/api/v1/agent/proposals", response_model=DraftProposal)
def agent_propose_post(
    request: AgentProposalRequest,
    harness: Annotated[AgentHarness, Depends(get_agent_harness)],
) -> DraftProposal:
    return harness.propose_post(request)


@app.post("/api/v1/agent/drafts", response_model=AgentDraftResponse)
def agent_create_draft(
    request: CreateAgentDraftRequest,
    harness: Annotated[AgentHarness, Depends(get_agent_harness)],
) -> AgentDraftResponse:
    try:
        return harness.create_draft(request)
    except ValueError as exc:
        raise api_error(400, "POLICY_BLOCKED", str(exc)) from exc


@app.post("/api/v1/agent/runs/dry-run", response_model=StartRunResponse)
def agent_start_dry_run(
    request: StartRunRequest,
    harness: Annotated[AgentHarness, Depends(get_agent_harness)],
) -> StartRunResponse:
    try:
        run = harness.start_dry_run(request.queueItemId)
    except ValueError as exc:
        raise api_error(400, "POLICY_BLOCKED", str(exc)) from exc
    return StartRunResponse(runId=run.id, status=run.status)


@app.post("/api/v1/agent/runs/publish-request", response_model=AgentPublishDecision)
def agent_request_publish(
    request: AgentPublishRequest,
    harness: Annotated[AgentHarness, Depends(get_agent_harness)],
) -> AgentPublishDecision:
    return harness.request_publish(request)


@app.post("/api/v1/conversations", response_model=CreateConversationResponse)
def create_conversation(
    request: CreateConversationRequest,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
) -> CreateConversationResponse:
    conversation = orchestrator.create_conversation(request.title)
    return CreateConversationResponse(id=conversation.id, sessionNumber=conversation.sessionNumber)


@app.get("/api/v1/conversations", response_model=ConversationListResponse)
def list_conversations(
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationListResponse:
    items, total = orchestrator.list_conversations(limit=limit, offset=offset)
    return ConversationListResponse(items=items, total=total)


@app.get("/api/v1/conversations/sessions/{session_number}", response_model=ConversationDetail)
def get_conversation_by_number(
    session_number: int,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
) -> ConversationDetail:
    conversation = orchestrator.get_conversation_by_number(session_number)
    if conversation is None:
        raise api_error(404, "NOT_FOUND", "Session was not found.", {"sessionNumber": session_number})
    return conversation


@app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
) -> ConversationDetail:
    conversation = orchestrator.get_conversation(conversation_id)
    if conversation is None:
        raise api_error(404, "NOT_FOUND", "Conversation was not found.", {"conversationId": conversation_id})
    return conversation


@app.delete("/api/v1/conversations/{conversation_id}", status_code=204, response_class=Response)
def delete_conversation(
    conversation_id: str,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
) -> Response:
    if not orchestrator.delete_conversation(conversation_id):
        raise api_error(404, "NOT_FOUND", "Conversation was not found.", {"conversationId": conversation_id})
    return Response(status_code=204)


@app.post("/api/v1/conversations/{conversation_id}/messages", response_model=StartPipelineResponse)
async def create_chat_message(
    conversation_id: str,
    request: CreateChatMessageRequest,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
) -> StartPipelineResponse:
    try:
        message, run = orchestrator.start(conversation_id, request.content)
    except ValueError as exc:
        raise api_error(404, "NOT_FOUND", str(exc), {"conversationId": conversation_id}) from exc
    return StartPipelineResponse(messageId=message.id, pipelineRunId=run.id)


@app.get("/api/v1/pipeline-runs/{run_id}", response_model=PipelineRun)
def get_pipeline_run(
    run_id: str,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
) -> PipelineRun:
    run = orchestrator.get_run(run_id)
    if run is None:
        raise api_error(404, "NOT_FOUND", "Pipeline run was not found.", {"pipelineRunId": run_id})
    return run


@app.get("/api/v1/pipeline-runs/{run_id}/events")
async def stream_pipeline_run(
    run_id: str,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
):
    if orchestrator.get_run(run_id) is None:
        raise api_error(404, "NOT_FOUND", "Pipeline run was not found.", {"pipelineRunId": run_id})
    return StreamingResponse(
        orchestrator.stream(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/pipeline-runs/{run_id}/retry", response_model=PipelineRun)
async def retry_pipeline_run(
    run_id: str,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
) -> PipelineRun:
    try:
        return orchestrator.retry(run_id)
    except ValueError as exc:
        raise api_error(409, "RETRY_BLOCKED", str(exc), {"pipelineRunId": run_id}) from exc


@app.post("/api/v1/pipeline-runs/{run_id}/create-draft", response_model=CreatePipelineDraftResponse)
def create_pipeline_draft(
    run_id: str,
    request: CreatePipelineDraftRequest,
    orchestrator: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
) -> CreatePipelineDraftResponse:
    try:
        item = orchestrator.create_draft(
            run_id,
            request.candidateId,
            pillar=request.pillar,
            cta_type=request.ctaType,
            target_url=request.targetUrl,
            utm_campaign=request.utmCampaign,
            utm_content=request.utmContent,
        )
    except ValueError as exc:
        raise api_error(409, "DRAFT_BLOCKED", str(exc), {"pipelineRunId": run_id}) from exc
    return CreatePipelineDraftResponse(id=item.id, status=item.status)
