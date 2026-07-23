"""Durable, human-gated content drafting pipeline for AI Studio."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.api.schemas import (
    ChatMessage,
    Conversation,
    ConversationDetail,
    ConversationSummary,
    PipelineArtifact,
    PipelineRun,
    PipelineStage,
    PostCandidate,
)
from src.config import Settings
from src.database import PostgresStore
from src.services.queue_service import QueueService


STAGES = (
    ("trend_research", "Trend Researcher", "Проверяет публичный контекст и источники"),
    ("strategy", "Content Strategist", "Определяет угол, аудиторию и CTA"),
    ("ghostwriter", "Ghostwriter", "Готовит три оригинальных варианта"),
    ("hook_editor", "Hook Editor", "Усиливает ясность первого абзаца"),
    ("brand_editor", "Brand & Clarity Editor", "Приводит текст к тону и языку"),
    ("fact_policy", "Fact & Policy Reviewer", "Проверяет факты, риски и правила"),
    ("chief", "Chief Agent", "Собирает итог и рекомендации"),
)
TERMINAL_STATES = {"completed", "failed", "interrupted"}


class StageResult(BaseModel):
    """Strict response contract expected from every model call."""

    summary: str = Field(max_length=1000)
    output: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    sources: list[PipelineArtifact] = Field(default_factory=list)
    candidates: list[PostCandidate] = Field(default_factory=list, max_length=3)
    finalRecommendation: str = Field(default="", max_length=1200)


class OpenAIStageClient:
    """Small OpenAI Responses adapter kept outside orchestration and publishing."""

    def __init__(self, settings: Settings, store: PostgresStore | None = None) -> None:
        self.settings = settings

    async def run(self, stage_id: str, prompt: str, *, use_web_search: bool) -> StageResult:
        if not self.settings.openai_api_key or not self.settings.openai_model:
            raise RuntimeError("AI Studio requires OPENAI_API_KEY and OPENAI_MODEL on the backend.")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - installation concern
            raise RuntimeError("The OpenAI Python package is not installed.") from exc

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        tools = [{"type": "web_search_preview"}] if use_web_search else None
        response = await client.responses.create(
            model=self.settings.openai_model,
            instructions=(
                "You are one stage in a human-controlled X post drafting pipeline. "
                "Never claim guaranteed virality, invent sources, create spam, or request credentials. "
                "Return JSON only with summary, output, warnings, sources, candidates, finalRecommendation. "
                "Each candidate must have id, text, score, rationale, warnings and be original and under 281 characters. "
                "Each source must have type='source', title, url, publishedAt, and summary."
            ),
            input=prompt,
            tools=tools,
        )
        raw = getattr(response, "output_text", "")
        return StageResult.model_validate(self._normalize_result(self._json_object(raw)))

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise RuntimeError("The model did not return a valid structured response.") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("The model response must be a JSON object.")
        return parsed

    @staticmethod
    def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
        """Keep a strict internal schema while tolerating harmless JSON shape drift."""
        normalized = dict(raw)
        normalized["summary"] = str(normalized.get("summary") or "")[:1000]
        output = normalized.get("output", {})
        if not isinstance(output, dict):
            normalized["output"] = {"text": str(output)}

        recommendation = normalized.get("finalRecommendation", "")
        if isinstance(recommendation, dict):
            normalized["finalRecommendation"] = str(
                recommendation.get("recommendation")
                or recommendation.get("reason")
                or recommendation.get("summary")
                or recommendation.get("text")
                or json.dumps(recommendation, ensure_ascii=False)
            )
        elif recommendation is None:
            normalized["finalRecommendation"] = ""
        normalized["finalRecommendation"] = str(normalized.get("finalRecommendation") or "")[:1200]

        candidates = normalized.get("candidates", [])
        if isinstance(candidates, list):
            normalized_candidates: list[dict[str, Any]] = []
            for index, candidate in enumerate(candidates[:3], start=1):
                if isinstance(candidate, str):
                    candidate = {"id": f"candidate-{index}", "text": candidate, "score": 70}
                elif isinstance(candidate, dict):
                    candidate = dict(candidate)
                else:
                    continue

                try:
                    score = int(candidate.get("score", 70))
                except (TypeError, ValueError):
                    score = 70
                score = score * 10 if 0 <= score <= 10 else score
                text = str(candidate.get("text") or candidate.get("post") or "")
                warnings = candidate.get("warnings") or []
                if not isinstance(warnings, list):
                    warnings = [str(warnings)]
                warnings = [str(warning) for warning in warnings]
                if len(text) > 280:
                    text = text[:280]
                    warnings.append("Вариант сокращён до лимита X в 280 символов.")
                normalized_candidates.append(
                    {
                        "id": str(candidate.get("id") or candidate.get("candidateId") or f"candidate-{index}"),
                        "text": text,
                        "score": max(0, min(100, score)),
                        "rationale": str(candidate.get("rationale") or ""),
                        "warnings": warnings,
                    }
                )
            normalized["candidates"] = normalized_candidates
        return normalized


class PipelineStore:
    """Append-only JSONL storage; latest record for an id is authoritative."""

    def __init__(self, settings: Settings) -> None:
        self.conversations_path = settings.pipeline_conversations_path
        self.messages_path = settings.pipeline_messages_path
        self.runs_path = settings.pipeline_runs_path
        self.store = store
        self._lock = RLock()
        self._ensure_session_numbers()

    def save_conversation(self, item: Conversation) -> None:
        if self.store is not None:
            self.store.upsert(
                "conversations", item.model_dump(mode="json"), session_number=item.sessionNumber,
                updated_at=item.updatedAt, deleted_at=item.deletedAt,
            )
            return
        self._append(self.conversations_path, item.model_dump(mode="json"))

    def save_message(self, item: ChatMessage) -> None:
        if self.store is not None:
            self.store.upsert(
                "chat_messages", item.model_dump(mode="json"), conversation_id=item.conversationId, created_at=item.createdAt
            )
            return
        self._append(self.messages_path, item.model_dump(mode="json"))

    def save_run(self, item: PipelineRun) -> None:
        if self.store is not None:
            self.store.upsert(
                "pipeline_runs", item.model_dump(mode="json"), conversation_id=item.conversationId,
                updated_at=item.updatedAt, status=item.status,
            )
            return
        self._append(self.runs_path, item.model_dump(mode="json"))

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self._conversations().get(conversation_id)

    def get_conversation_by_number(self, session_number: int) -> Conversation | None:
        return next(
            (item for item in self._conversations().values() if item.sessionNumber == session_number),
            None,
        )

    def get_run(self, run_id: str) -> PipelineRun | None:
        return self.runs().get(run_id)

    def detail(self, conversation_id: str) -> ConversationDetail | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None
        messages = [m for m in self.messages().values() if m.conversationId == conversation_id]
        runs = [r for r in self.runs().values() if r.conversationId == conversation_id]
        return ConversationDetail(
            **conversation.model_dump(),
            messages=sorted(messages, key=lambda item: item.createdAt),
            runs=sorted(runs, key=lambda item: item.createdAt, reverse=True),
        )

    def list_conversations(self, limit: int, offset: int) -> tuple[list[ConversationSummary], int]:
        conversations = self._conversations()
        messages = self.messages()
        runs = self.runs()
        summaries: list[ConversationSummary] = []
        for conversation in conversations.values():
            conversation_messages = [item for item in messages.values() if item.conversationId == conversation.id]
            conversation_runs = [item for item in runs.values() if item.conversationId == conversation.id]
            latest_message = max(conversation_messages, key=lambda item: item.createdAt, default=None)
            latest_run = max(conversation_runs, key=lambda item: item.updatedAt, default=None)
            preview = " ".join((latest_message.content if latest_message else "").split())[:160]
            summaries.append(
                ConversationSummary(
                    **conversation.model_dump(),
                    lastMessagePreview=preview,
                    lastRunStatus=latest_run.status if latest_run else None,
                )
            )
        summaries.sort(key=lambda item: (item.updatedAt, item.sessionNumber), reverse=True)
        return summaries[offset : offset + limit], len(summaries)

    def mark_incomplete_as_interrupted(self) -> None:
        for run in self.runs().values():
            if run.status not in TERMINAL_STATES:
                run.status = "interrupted"
                run.updatedAt = _now()
                self.save_run(run)

    def _conversations(self) -> dict[str, Conversation]:
        return {
            item_id: item
            for item_id, item in self._all_conversations().items()
            if item.deletedAt is None
        }

    def _all_conversations(self) -> dict[str, Conversation]:
        self._ensure_session_numbers()
        if self.store is not None:
            return {
                item.id: item
                for raw in self.store.list("conversations", order_by="updated_at DESC, id DESC")
                if (item := Conversation.model_validate(raw))
            }
        return self._latest(self.conversations_path, Conversation)

    def _ensure_session_numbers(self) -> None:
        """Backfill durable, human-friendly numbers for conversations created before sessions."""
        if self.store is not None:
            return
        with self._lock:
            latest_raw: dict[str, dict[str, Any]] = {}
            if self.conversations_path.exists():
                for line in self.conversations_path.read_text(encoding="utf-8").splitlines():
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(raw, dict) and raw.get("id"):
                        latest_raw[str(raw["id"])] = raw

            used: set[int] = set()
            pending: list[dict[str, Any]] = []
            for raw in latest_raw.values():
                session_number = raw.get("sessionNumber")
                if isinstance(session_number, int) and session_number > 0 and session_number not in used:
                    used.add(session_number)
                else:
                    pending.append(raw)

            next_number = 1
            for raw in sorted(pending, key=lambda item: (item.get("createdAt", ""), str(item.get("id", "")))):
                while next_number in used:
                    next_number += 1
                raw["sessionNumber"] = next_number
                used.add(next_number)
                next_number += 1
                try:
                    self.save_conversation(Conversation.model_validate(raw))
                except ValidationError:
                    continue

    @staticmethod
    def _append(path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _latest(path: Path, model: type[BaseModel]) -> dict[str, Any]:
        records: dict[str, Any] = {}
        if not path.exists():
            return records
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                raw = json.loads(line)
                item = model.model_validate(raw)
                records[item.id] = item
            except (json.JSONDecodeError, ValidationError, KeyError):
                continue
        return records

    def messages(self) -> dict[str, ChatMessage]:
        if self.store is not None:
            return {item.id: item for raw in self.store.list("chat_messages", order_by="created_at ASC, id ASC") if (item := ChatMessage.model_validate(raw))}
        return self._latest(self.messages_path, ChatMessage)

    def runs(self) -> dict[str, PipelineRun]:
        if self.store is not None:
            return {item.id: item for raw in self.store.list("pipeline_runs", order_by="updated_at DESC, id DESC") if (item := PipelineRun.model_validate(raw))}
        return self._latest(self.runs_path, PipelineRun)

    def migrate_legacy_files(self) -> None:
        if self.store is None:
            return

        def import_conversations(raw: str) -> None:
            latest: dict[str, dict[str, Any]] = {}
            for line in raw.splitlines():
                try:
                    item = json.loads(line)
                    if isinstance(item, dict) and item.get("id"):
                        latest[str(item["id"])] = item
                except json.JSONDecodeError:
                    continue
            used = {item.get("sessionNumber") for item in latest.values() if isinstance(item.get("sessionNumber"), int)}
            next_number = 1
            for item in sorted(latest.values(), key=lambda value: (value.get("createdAt", ""), value["id"])):
                if not isinstance(item.get("sessionNumber"), int) or item["sessionNumber"] < 1:
                    while next_number in used:
                        next_number += 1
                    item["sessionNumber"] = next_number
                    used.add(next_number)
                try:
                    self.save_conversation(Conversation.model_validate(item))
                except ValidationError:
                    continue

        def import_records(path: Path, model: type[BaseModel], save) -> None:
            def importer(raw: str) -> None:
                latest: dict[str, BaseModel] = {}
                for line in raw.splitlines():
                    try:
                        item = model.model_validate(json.loads(line))
                        latest[item.id] = item
                    except (json.JSONDecodeError, ValidationError, KeyError):
                        continue
                for item in latest.values():
                    save(item)
            self.store.import_once(path, importer)

        self.store.import_once(self.conversations_path, import_conversations)
        import_records(self.messages_path, ChatMessage, self.save_message)
        import_records(self.runs_path, PipelineRun, self.save_run)


class PipelineOrchestrator:
    """Runs drafting stages and deliberately has no publishing dependency."""

    def __init__(self, settings: Settings, queue_service: QueueService, client: OpenAIStageClient | None = None, store: PostgresStore | None = None) -> None:
        self.settings = settings
        self.queue_service = queue_service
        self.store = PipelineStore(settings, store)
        self.client = client or OpenAIStageClient(settings)
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self.store.mark_incomplete_as_interrupted()

    def create_conversation(self, title: str) -> Conversation:
        with self.store._lock:
            now = _now()
            session_number = store.next_conversation_session_number() if store is not None else max(
                (item.sessionNumber for item in self.store._all_conversations().values()), default=0
            ) + 1
            item = Conversation(
                id=_id("conversation"),
                sessionNumber=session_number,
                title=title.strip(),
                createdAt=now,
                updatedAt=now,
            )
            self.store.save_conversation(item)
            return item

    def get_conversation(self, conversation_id: str) -> ConversationDetail | None:
        return self.store.detail(conversation_id)

    def get_conversation_by_number(self, session_number: int) -> ConversationDetail | None:
        conversation = self.store.get_conversation_by_number(session_number)
        return self.store.detail(conversation.id) if conversation else None

    def list_conversations(self, limit: int, offset: int) -> tuple[list[ConversationSummary], int]:
        return self.store.list_conversations(limit, offset)

    def delete_conversation(self, conversation_id: str) -> bool:
        """Hide a session durably while keeping JSONL history append-only."""
        with self.store._lock:
            conversation = self.store.get_conversation(conversation_id)
            if conversation is None:
                return False

            for run in self.store.runs().values():
                if run.conversationId != conversation_id:
                    continue
                task = self.tasks.pop(run.id, None)
                if task is not None and not task.done():
                    task.cancel()
                if run.status not in TERMINAL_STATES:
                    run.status = "interrupted"
                    run.completedAt = _now()
                    self._save_run(run, "run_interrupted")

            now = _now()
            conversation.deletedAt = now
            conversation.updatedAt = now
            self.store.save_conversation(conversation)
            return True

    def get_run(self, run_id: str) -> PipelineRun | None:
        run = self.store.get_run(run_id)
        if run is None or self.store.get_conversation(run.conversationId) is None:
            return None
        return run

    def start(self, conversation_id: str, content: str) -> tuple[ChatMessage, PipelineRun]:
        conversation = self.store.get_conversation(conversation_id)
        if conversation is None:
            raise ValueError("Conversation was not found.")
        content = content.strip()
        now = _now()
        message = ChatMessage(id=_id("message"), conversationId=conversation_id, role="user", content=content, createdAt=now)
        run = PipelineRun(
            id=_id("pipeline"),
            conversationId=conversation_id,
            messageId=message.id,
            stages=[PipelineStage(id=stage_id, name=name, role=role) for stage_id, name, role in STAGES],
            createdAt=now,
            updatedAt=now,
        )
        message.pipelineRunId = run.id
        previous_messages = [
            item
            for item in self.store.messages().values()
            if item.conversationId == conversation_id and item.role == "user"
        ]
        if not previous_messages:
            conversation.title = _title_from_prompt(content)
        conversation.updatedAt = now
        self.store.save_message(message)
        self.store.save_conversation(conversation)
        self.store.save_run(run)
        self.tasks[run.id] = asyncio.create_task(self._execute(run.id, content, 0))
        return message, run

    def retry(self, run_id: str) -> PipelineRun:
        run = self.get_run(run_id)
        if run is None:
            raise ValueError("Pipeline run was not found.")
        failed_index = next((index for index, stage in enumerate(run.stages) if stage.status == "failed"), None)
        if failed_index is None:
            raise ValueError("Only a failed pipeline stage can be retried.")
        message = self._message(run.messageId)
        if message is None:
            raise ValueError("Pipeline source message was not found.")
        run.status = "queued"
        run.completedAt = None
        run.updatedAt = _now()
        run.stages[failed_index].status = "pending"
        run.stages[failed_index].error = None
        self._save_run(run, "run_queued")
        self.tasks[run.id] = asyncio.create_task(self._execute(run.id, message.content, failed_index))
        return run

    def create_draft(self, run_id: str, candidate_id: str, **metadata: Any):
        run = self.get_run(run_id)
        if run is None or run.status != "completed":
            raise ValueError("Only a completed pipeline can create a draft.")
        candidate = next((item for item in run.candidates if item.id == candidate_id), None)
        if candidate is None:
            raise ValueError("Candidate was not found.")
        return self.queue_service.create_item(
            candidate.text,
            source=f"ai_studio:{run.id}",
            pillar=metadata.get("pillar") or "mini_guides",
            cta_type=metadata.get("cta_type") or "none",
            target_url=metadata.get("target_url"),
            utm_campaign=metadata.get("utm_campaign"),
            utm_content=metadata.get("utm_content"),
            metadata={"pipelineRunId": run.id, "candidateId": candidate.id, "aiGenerated": True},
        )

    async def stream(self, run_id: str):
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.subscribers.setdefault(run_id, set()).add(queue)
        try:
            snapshot = self.get_run(run_id)
            if snapshot is None:
                return
            yield self._sse("snapshot", snapshot.model_dump(mode="json"))
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield self._sse(event["type"], event["data"])
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                current = self.get_run(run_id)
                if current and current.status in TERMINAL_STATES and queue.empty():
                    return
        finally:
            self.subscribers.get(run_id, set()).discard(queue)

    async def _execute(self, run_id: str, user_message: str, start_index: int) -> None:
        run = self.get_run(run_id)
        if run is None:
            return
        run.status = "running"
        self._save_run(run, "run_started")
        for index in range(start_index, len(run.stages)):
            stage = run.stages[index]
            if stage.status == "completed":
                continue
            stage.status = "running"
            stage.startedAt = _now()
            stage.error = None
            self._save_run(run, "stage_started", {"stageId": stage.id})
            try:
                result = await self.client.run(stage.id, self._prompt(run, user_message, stage), use_web_search=stage.id == "trend_research")
            except Exception as exc:
                stage.status = "failed"
                stage.error = str(exc)
                stage.finishedAt = _now()
                run.status = "failed"
                self._save_run(run, "stage_failed", {"stageId": stage.id, "error": stage.error})
                return
            stage.status = "completed"
            stage.summary = result.summary
            stage.output = result.output
            stage.warnings = result.warnings
            stage.artifacts = result.sources
            stage.finishedAt = _now()
            if result.candidates:
                run.candidates = result.candidates[:3]
                self._save_run(run, "candidate_ready", {"stageId": stage.id, "candidates": [item.model_dump(mode="json") for item in run.candidates]})
            if result.finalRecommendation:
                run.finalRecommendation = result.finalRecommendation
            self._save_run(run, "stage_completed", {"stageId": stage.id})
        run.status = "completed"
        run.progress = 100
        run.completedAt = _now()
        self._save_run(run, "run_completed")
        assistant = ChatMessage(
            id=_id("message"),
            conversationId=run.conversationId,
            role="assistant",
            content=run.finalRecommendation or "Pipeline завершён. Выберите вариант для черновика.",
            createdAt=_now(),
            pipelineRunId=run.id,
        )
        self.store.save_message(assistant)
        conversation = self.store.get_conversation(run.conversationId)
        if conversation is not None:
            conversation.updatedAt = _now()
            self.store.save_conversation(conversation)

    def _save_run(self, run: PipelineRun, event_type: str, details: dict[str, Any] | None = None) -> None:
        run.updatedAt = _now()
        run.progress = round(100 * sum(stage.status == "completed" for stage in run.stages) / len(run.stages))
        self.store.save_run(run)
        self._publish(run.id, event_type, {"run": run.model_dump(mode="json"), **(details or {})})

    def _publish(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        for queue in self.subscribers.get(run_id, set()):
            queue.put_nowait({"type": event_type, "data": data})

    def _message(self, message_id: str) -> ChatMessage | None:
        return self.store.messages().get(message_id)

    @staticmethod
    def _prompt(run: PipelineRun, message: str, stage: PipelineStage) -> str:
        completed = [
            {"stage": item.id, "summary": item.summary, "output": item.output, "warnings": item.warnings}
            for item in run.stages
            if item.status == "completed"
        ]
        return json.dumps(
            {
                "stage": stage.id,
                "role": stage.name,
                "operatorMessage": message,
                "language": "Russian unless the operator message is clearly another language",
                "defaultAudience": "expert B2B",
                "previousStages": completed,
                "limits": {"candidateCount": 3, "maxPostCharacters": 280, "maxRevisionCycles": 1},
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _sse(event_type: str, data: dict[str, Any]) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}-{_now().strftime('%Y%m%d-%H%M%S-%f')}"


def _title_from_prompt(content: str) -> str:
    normalized = " ".join(content.split())
    return f"{normalized[:77].rstrip()}…" if len(normalized) > 78 else normalized
