from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.agent.pipeline import OpenAIStageClient, PipelineOrchestrator, StageResult
from src.api.schemas import PostCandidate
from src.config import Settings
from src.services.queue_service import QueueService


class FakeStageClient:
    async def run(self, stage_id: str, prompt: str, *, use_web_search: bool) -> StageResult:
        candidates = []
        recommendation = ""
        if stage_id == "ghostwriter":
            candidates = [
                PostCandidate(id="candidate-1", text="Почему B2B-воронки теряют спрос: три проверяемых причины.", score=82),
                PostCandidate(id="candidate-2", text="Одна ясная гипотеза лучше пяти случайных правок в воронке.", score=80),
                PostCandidate(id="candidate-3", text="Как найти главный разрыв между обещанием и первым экраном сайта.", score=78),
            ]
        if stage_id == "chief":
            recommendation = "Выбранные варианты готовы к проверке оператором."
        return StageResult(summary=f"{stage_id} completed", candidates=candidates, finalRecommendation=recommendation)


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_normalize_result_truncates_overlong_candidate(self) -> None:
        result = StageResult.model_validate(
            OpenAIStageClient._normalize_result(
                {
                    "summary": "ok",
                    "candidates": [{"id": "candidate-1", "text": "x" * 281, "score": 8}],
                }
            )
        )

        self.assertEqual(len(result.candidates[0].text), 280)
        self.assertIn("Вариант сокращён до лимита X в 280 символов.", result.candidates[0].warnings)
        self.assertEqual(result.candidates[0].score, 80)

    async def test_pipeline_creates_human_gated_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                data_path=root / "tweets.txt",
                agent_queue_path=root / "queue.jsonl",
                pipeline_conversations_path=root / "conversations.jsonl",
                pipeline_messages_path=root / "messages.jsonl",
                pipeline_runs_path=root / "runs.jsonl",
            )
            queue = QueueService(settings.data_path, settings.agent_queue_path)
            orchestrator = PipelineOrchestrator(settings, queue, client=FakeStageClient())
            conversation = orchestrator.create_conversation("Test")
            _, run = orchestrator.start(conversation.id, "Сделай пост о B2B-воронке")

            await orchestrator.tasks[run.id]
            finished = orchestrator.get_run(run.id)

            self.assertIsNotNone(finished)
            self.assertEqual(finished.status, "completed")
            self.assertEqual(finished.progress, 100)
            self.assertEqual(len(finished.candidates), 3)

            draft = orchestrator.create_draft(run.id, "candidate-1")
            self.assertEqual(draft.status, "draft")
            self.assertEqual(queue.get_item(draft.id).text, finished.candidates[0].text)
            self.assertEqual(queue.get_item(draft.id).pillar, "mini_guides")
            self.assertEqual(queue.get_item(draft.id).ctaType, "none")

    async def test_retry_is_limited_to_failed_stage(self) -> None:
        class FailingClient(FakeStageClient):
            def __init__(self) -> None:
                self.failed = False

            async def run(self, stage_id: str, prompt: str, *, use_web_search: bool) -> StageResult:
                if stage_id == "strategy" and not self.failed:
                    self.failed = True
                    raise RuntimeError("temporary error")
                return await super().run(stage_id, prompt, use_web_search=use_web_search)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                data_path=root / "tweets.txt",
                agent_queue_path=root / "queue.jsonl",
                pipeline_conversations_path=root / "conversations.jsonl",
                pipeline_messages_path=root / "messages.jsonl",
                pipeline_runs_path=root / "runs.jsonl",
            )
            orchestrator = PipelineOrchestrator(settings, QueueService(settings.data_path, settings.agent_queue_path), client=FailingClient())
            conversation = orchestrator.create_conversation("Test")
            _, run = orchestrator.start(conversation.id, "Задача")
            await orchestrator.tasks[run.id]
            self.assertEqual(orchestrator.get_run(run.id).status, "failed")

            orchestrator.retry(run.id)
            await orchestrator.tasks[run.id]
            self.assertEqual(orchestrator.get_run(run.id).status, "completed")

    async def test_sessions_receive_numbers_titles_and_history_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                data_path=root / "tweets.txt",
                agent_queue_path=root / "queue.jsonl",
                pipeline_conversations_path=root / "conversations.jsonl",
                pipeline_messages_path=root / "messages.jsonl",
                pipeline_runs_path=root / "runs.jsonl",
            )
            orchestrator = PipelineOrchestrator(settings, QueueService(settings.data_path, settings.agent_queue_path), client=FakeStageClient())
            first = orchestrator.create_conversation("Untitled")
            second = orchestrator.create_conversation("Untitled")

            self.assertEqual(first.sessionNumber, 1)
            self.assertEqual(second.sessionNumber, 2)

            _, run = orchestrator.start(first.id, "Сделай пост о B2B-воронке")
            await orchestrator.tasks[run.id]

            detail = orchestrator.get_conversation_by_number(1)
            self.assertIsNotNone(detail)
            self.assertEqual(detail.title, "Сделай пост о B2B-воронке")
            summaries, total = orchestrator.list_conversations(limit=10, offset=0)
            self.assertEqual(total, 2)
            self.assertEqual(summaries[0].sessionNumber, 1)
            self.assertEqual(summaries[0].lastRunStatus, "completed")
            self.assertTrue(summaries[0].lastMessagePreview)

    async def test_legacy_conversations_are_backfilled_once_in_creation_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conversations_path = root / "conversations.jsonl"
            now = datetime.now(timezone.utc)
            legacy = [
                {"id": "conversation-old", "title": "Old", "createdAt": now.isoformat(), "updatedAt": now.isoformat()},
                {
                    "id": "conversation-new",
                    "title": "New",
                    "createdAt": (now + timedelta(seconds=1)).isoformat(),
                    "updatedAt": now.isoformat(),
                },
            ]
            conversations_path.write_text("\n".join(json.dumps(item) for item in legacy) + "\n", encoding="utf-8")
            settings = Settings(
                data_path=root / "tweets.txt",
                agent_queue_path=root / "queue.jsonl",
                pipeline_conversations_path=conversations_path,
                pipeline_messages_path=root / "messages.jsonl",
                pipeline_runs_path=root / "runs.jsonl",
            )

            orchestrator = PipelineOrchestrator(settings, QueueService(settings.data_path, settings.agent_queue_path), client=FakeStageClient())
            self.assertEqual(orchestrator.get_conversation("conversation-old").sessionNumber, 1)
            self.assertEqual(orchestrator.get_conversation("conversation-new").sessionNumber, 2)

            restarted = PipelineOrchestrator(settings, QueueService(settings.data_path, settings.agent_queue_path), client=FakeStageClient())
            self.assertEqual(restarted.get_conversation_by_number(1).id, "conversation-old")
            self.assertEqual(restarted.get_conversation_by_number(2).id, "conversation-new")

    async def test_deleted_session_is_hidden_and_its_number_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                data_path=root / "tweets.txt",
                agent_queue_path=root / "queue.jsonl",
                pipeline_conversations_path=root / "conversations.jsonl",
                pipeline_messages_path=root / "messages.jsonl",
                pipeline_runs_path=root / "runs.jsonl",
            )
            orchestrator = PipelineOrchestrator(settings, QueueService(settings.data_path, settings.agent_queue_path), client=FakeStageClient())
            first = orchestrator.create_conversation("First")
            second = orchestrator.create_conversation("Second")

            self.assertTrue(orchestrator.delete_conversation(first.id))
            self.assertIsNone(orchestrator.get_conversation(first.id))
            self.assertIsNone(orchestrator.get_conversation_by_number(first.sessionNumber))
            summaries, total = orchestrator.list_conversations(limit=10, offset=0)
            self.assertEqual(total, 1)
            self.assertEqual(summaries[0].id, second.id)

            third = orchestrator.create_conversation("Third")
            self.assertEqual(third.sessionNumber, 3)

            restarted = PipelineOrchestrator(settings, QueueService(settings.data_path, settings.agent_queue_path), client=FakeStageClient())
            self.assertIsNone(restarted.get_conversation_by_number(1))


if __name__ == "__main__":
    unittest.main()
