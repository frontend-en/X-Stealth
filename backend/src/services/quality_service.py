"""Quality gate for offer-engine posts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from src.api.schemas import CtaType, PostPillar, QualityResult, QueueItem
from src.config import BACKEND_ROOT
from src.services.funnel_service import build_utm_url
from src.services.queue_service import validate_post_text

DEFAULT_PILLARS: set[str] = {"cases", "errors", "breakdowns", "mini_guides", "personal_experience"}
DEFAULT_CTA_TYPES: set[str] = {"checklist", "audit", "consultation", "template", "case_study", "newsletter", "none"}
CTA_WORDS = ("checklist", "audit", "template", "case", "newsletter", "разбор", "чеклист", "шаблон", "ссылка")


class QualityService:
    """Score posts and enforce required offer-engine metadata."""

    def __init__(self, config_dir: Path = BACKEND_ROOT / "config") -> None:
        self.config_dir = config_dir
        self.pillars = self._load_ids("pillars.json", "pillars", DEFAULT_PILLARS)
        self.cta_types = self._load_ids("cta_templates.json", "ctaTypes", DEFAULT_CTA_TYPES)

    def evaluate(self, item: QueueItem, existing_items: list[QueueItem] | None = None) -> QualityResult:
        validation = validate_post_text(item.text)
        errors = list(validation.errors)
        warnings = list(validation.warnings)
        is_editorial_ai_draft = item.source.startswith("ai_studio:") and item.ctaType == "none"

        if item.pillar is None:
            errors.append("Post pillar is required.")
        elif item.pillar not in self.pillars:
            errors.append("Post pillar is not configured.")

        if item.ctaType is None:
            errors.append("CTA type is required.")
        elif item.ctaType == "none" and is_editorial_ai_draft:
            warnings.append("Editorial AI Studio draft has no external CTA or tracking URL.")
        elif item.ctaType == "none":
            errors.append("CTA type is required.")
        elif item.ctaType not in self.cta_types:
            errors.append("CTA type is not configured.")

        if is_editorial_ai_draft:
            pass
        elif not item.targetUrl:
            errors.append("Target URL is required.")
        elif not self._looks_like_url(item.targetUrl):
            errors.append("Target URL must be an absolute http(s) URL.")

        if not item.utmCampaign:
            warnings.append("UTM campaign is missing; default campaign will be used.")
        if not item.utmContent:
            warnings.append("UTM content is missing; queue item id will be used.")

        if not self._has_cta_signal(item.text) and (not item.targetUrl or item.targetUrl not in item.text):
            warnings.append("Post may not contain a clear CTA.")

        if not self._has_value_signal(item.text):
            warnings.append("Post may not deliver enough value before the CTA.")

        if existing_items and self._has_duplicate(item, existing_items):
            errors.append("Post appears to duplicate another queued item.")

        score = self._score(validation.textLength, errors, warnings, item)
        utm_url = None
        if item.targetUrl and self._looks_like_url(item.targetUrl):
            utm_url = build_utm_url(
                item.targetUrl,
                campaign=item.utmCampaign or item.pillar or "offer_engine",
                content=item.utmContent or item.id,
            )

        return QualityResult(
            valid=not errors,
            textLength=validation.textLength,
            errors=errors,
            warnings=warnings,
            qualityScore=score,
            pillar=item.pillar,
            ctaType=item.ctaType,
            utmUrl=utm_url,
        )

    def _load_ids(self, filename: str, key: str, fallback: set[str]) -> set[str]:
        path = self.config_dir / filename
        if not path.exists():
            return fallback
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return fallback
        loaded = {str(item["id"]) for item in raw.get(key, []) if isinstance(item, dict) and item.get("id")}
        return loaded or fallback

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _has_cta_signal(text: str) -> bool:
        normalized = text.lower()
        return any(word in normalized for word in CTA_WORDS) or "http://" in normalized or "https://" in normalized

    @staticmethod
    def _has_value_signal(text: str) -> bool:
        normalized = text.lower()
        value_markers = ("because", "why", "how", "step", "mistake", "fix", "почему", "как", "ошибка", "исправ")
        return "\n" in text or any(marker in normalized for marker in value_markers)

    @staticmethod
    def _has_duplicate(item: QueueItem, existing_items: list[QueueItem]) -> bool:
        current = QualityService._normalize(item.text)
        for existing in existing_items:
            if existing.id == item.id:
                continue
            if QualityService._normalize(existing.text) == current:
                return True
        return False

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\W+", "", text.lower())

    @staticmethod
    def _score(text_length: int, errors: list[str], warnings: list[str], item: QueueItem) -> int:
        score = 100
        score -= len(errors) * 30
        score -= len(warnings) * 8
        if text_length < 80:
            score -= 12
        if text_length > 260:
            score -= 8
        if item.targetUrl and item.targetUrl in item.text:
            score += 4
        if "\n" in item.text:
            score += 4
        return max(0, min(100, score))
