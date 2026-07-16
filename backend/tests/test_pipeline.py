from __future__ import annotations

import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
