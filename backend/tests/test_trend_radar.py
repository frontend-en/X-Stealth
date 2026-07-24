from __future__ import annotations

import unittest

from src.config import Settings
from src.services.trend_radar import TrendRadarService
from tests.fakes import InMemoryStore


class FakeResearcher:
    def __init__(self, sources=None) -> None:
        self.sources = sources or [
            {"platform": "reddit", "title": "Reddit discussion", "url": "https://www.reddit.com/r/test/1"},
            {"platform": "web", "title": "News context", "url": "https://example.com/news"},
        ]
        self.focus_queries = []

    async def discover(self, profile, window_hours, allowed_domains=None, focus_query=""):
        self.focus_queries.append(focus_query)
        source = "reddit" if allowed_domains else "web"
        return {"candidates": [{"topic": "AI-автоматизация продаж", "keywords": ["AI-автоматизация"], "summary": source}]}

    async def synthesize(self, profile, window_hours, reddit, web, x_signals, focus_query=""):
        return {
            "topic": "AI-автоматизация продаж",
            "summary": "Тема быстро обсуждается в контексте малого бизнеса.",
            "whyItRose": ["Вышли новые доступные инструменты."],
            "precursors": ["Участники обсуждают экономию времени."],
            "moodClusters": [{"label": "Практический интерес", "description": "Ищут понятные сценарии внедрения."}],
            "opportunity": {
                "audience": "Небольшие отделы продаж",
                "offer": "Настройка AI-помощника для первичного разбора лидов",
                "revenueModel": "Разовая настройка и ежемесячное сопровождение",
                "validationSteps": ["Провести 5 интервью", "Предложить пилот двум компаниям"],
                "risks": ["Нужно проверить качество данных клиента"],
            },
            "sources": self.sources,
        }


class FakeXClient:
    async def collect(self, candidates, window_hours):
        return [{"topic": candidates[0]["topic"], "query": "AI lang:ru", "postsCount": 12, "engagement": 80, "sources": []}]


class FailingXClient:
    async def collect(self, candidates, window_hours):
        raise RuntimeError("X API unavailable")


class TrendRadarTests(unittest.IsolatedAsyncioTestCase):
    def _service(self, researcher=None, x_client=None):
        settings = Settings(trend_radar_timezone="Europe/Moscow", x_bearer_token="test-token")
        return TrendRadarService(settings, InMemoryStore(), researcher=researcher or FakeResearcher(), x_client=x_client or FakeXClient())

    async def test_builds_confirmed_report_and_deduplicates_the_day(self):
        service = self._service()
        report = await service.run_today()
        repeated = await service.run_today()

        self.assertEqual(report.status, "completed")
        self.assertEqual(report.confidence, "high")
        self.assertEqual(report.opportunity.audience, "Небольшие отделы продаж")
        self.assertIn("ежемесячное сопровождение", report.pipelineContext)
        self.assertEqual(repeated.id, report.id)
        self.assertEqual(len(service.reports.list()), 1)

    async def test_manual_run_refreshes_existing_daily_report(self):
        service = self._service()
        first = await service.run_today()
        refreshed = await service.run_today(force=True)

        self.assertEqual(refreshed.id, first.id)
        self.assertEqual(len(service.reports.list()), 1)

    async def test_operator_query_is_passed_to_research_and_saved(self):
        researcher = FakeResearcher()
        service = self._service(researcher=researcher)

        report = await service.run_today(force=True, focus_query=" AI-ассистенты для салонов красоты ")

        self.assertEqual(report.focusQuery, "AI-ассистенты для салонов красоты")
        self.assertEqual(researcher.focus_queries, ["AI-ассистенты для салонов красоты", "AI-ассистенты для салонов красоты"])
        self.assertIn("AI-ассистенты для салонов красоты", report.pipelineContext)

    async def test_marks_report_insufficient_without_independent_source(self):
        service = self._service(researcher=FakeResearcher(sources=[
            {"platform": "reddit", "title": "Reddit discussion", "url": "https://www.reddit.com/r/test/1"},
        ]))
        report = await service.run_today()

        self.assertEqual(report.status, "insufficient_data")
        self.assertEqual(report.confidence, "low")
        self.assertTrue(any("Недостаточно" in warning for warning in report.warnings))

    async def test_records_x_api_failure(self):
        service = self._service(x_client=FailingXClient())
        report = await service.run_today()

        self.assertEqual(report.status, "failed")
        self.assertIn("X API unavailable", report.error)


if __name__ == "__main__":
    unittest.main()
