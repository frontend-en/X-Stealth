from __future__ import annotations

import unittest
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.agent.pipeline import OpenAIStageClient, PipelineOrchestrator, StageResult
from src.api.schemas import PipelineStage, PostCandidate, TrendReport
from src.config import Settings
from src.services.queue_service import QueueService
from tests.fakes import InMemoryStore


class FakeStageClient:
    async def run(self, stage_id: str, prompt: str, *, use_web_search: bool) -> StageResult:
        candidates = [PostCandidate(id="candidate-1", text="A useful post about a clear B2B offer.", score=82)] if stage_id == "ghostwriter" else []
        recommendation = "Candidate ready for review." if stage_id == "chief" else ""
        return StageResult(summary=f"{stage_id} completed", candidates=candidates, finalRecommendation=recommendation)


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def _orchestrator(self, client: FakeStageClient | None = None, store: InMemoryStore | None = None):
        state = store or InMemoryStore()
        return PipelineOrchestrator(Settings(), QueueService(state), store=state, client=client or FakeStageClient()), state

    async def test_normalize_result_truncates_overlong_candidate(self) -> None:
        result = StageResult.model_validate(
            OpenAIStageClient._normalize_result({"summary": "ok", "candidates": [{"id": "candidate-1", "text": "x" * 281, "score": 8}]})
        )
        self.assertEqual(len(result.candidates[0].text), 280)
        self.assertEqual(result.candidates[0].score, 80)

    async def test_pipeline_persists_a_human_gated_draft(self) -> None:
        orchestrator, _ = self._orchestrator()
        conversation = orchestrator.create_conversation("Test")
        _, run = orchestrator.start(conversation.id, "Draft a B2B post")
        await orchestrator.tasks[run.id]

        finished = orchestrator.get_run(run.id)
        self.assertIsNotNone(finished)
        self.assertEqual(finished.status, "completed")
        self.assertEqual(finished.progress, 100)

        draft = orchestrator.create_draft(run.id, "candidate-1")
        self.assertEqual(draft.status, "draft")
        self.assertEqual(orchestrator.queue_service.get_item(draft.id).text, finished.candidates[0].text)

    async def test_retry_is_limited_to_the_failed_stage(self) -> None:
        class FailingClient(FakeStageClient):
            def __init__(self) -> None:
                self.failed = False

            async def run(self, stage_id: str, prompt: str, *, use_web_search: bool) -> StageResult:
                if stage_id == "strategy" and not self.failed:
                    self.failed = True
                    raise RuntimeError("temporary error")
                return await super().run(stage_id, prompt, use_web_search=use_web_search)

        orchestrator, _ = self._orchestrator(FailingClient())
        conversation = orchestrator.create_conversation("Test")
        _, run = orchestrator.start(conversation.id, "Draft a post")
        await orchestrator.tasks[run.id]
        self.assertEqual(orchestrator.get_run(run.id).status, "failed")

        orchestrator.retry(run.id)
        await orchestrator.tasks[run.id]
        self.assertEqual(orchestrator.get_run(run.id).status, "completed")

    async def test_sessions_remain_durable_after_restart(self) -> None:
        store = InMemoryStore()
        orchestrator, _ = self._orchestrator(store=store)
        first = orchestrator.create_conversation("First")
        second = orchestrator.create_conversation("Second")
        self.assertEqual((first.sessionNumber, second.sessionNumber), (1, 2))

        self.assertTrue(orchestrator.delete_conversation(first.id))
        restarted, _ = self._orchestrator(store=store)
        self.assertIsNone(restarted.get_conversation_by_number(first.sessionNumber))
        third = restarted.create_conversation("Third")
        self.assertEqual(third.sessionNumber, 3)

    async def test_pipeline_prompt_contains_fresh_trend_radar_context(self) -> None:
        orchestrator, _ = self._orchestrator()
        now = datetime.now(timezone.utc)
        report = TrendReport(
            id="trend-today",
            reportDate=now.astimezone(ZoneInfo(orchestrator.settings.trend_radar_timezone)).date().isoformat(),
            status="completed",
            topic="AI-автоматизация",
            summary="Свежий проверенный контекст.",
            pipelineContext=json.dumps({"topic": "AI-автоматизация", "sources": []}),
            createdAt=now,
            updatedAt=now,
        )
        orchestrator.trend_reports.save(report)
        conversation = orchestrator.create_conversation("Test")
        _, run = orchestrator.start(conversation.id, "Draft a post")
        await orchestrator.tasks[run.id]

        prompt = json.loads(orchestrator._prompt(run, "Draft a post", PipelineStage(id="chief", name="Chief", role="Chief")))
        self.assertTrue(prompt["trendRadar"]["available"])
        self.assertEqual(prompt["trendRadar"]["topic"], "AI-автоматизация")


if __name__ == "__main__":
    unittest.main()
