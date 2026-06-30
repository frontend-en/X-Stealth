"""Seed example offer posts into the managed JSONL queue."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.config import load_settings
from src.services.queue_service import QueueService


EXAMPLES = [
    {
        "pillar": "errors",
        "cta_type": "checklist",
        "text": (
            "Most landing pages do not fail because of design.\n\n"
            "They fail because visitors cannot tell who it is for, what pain it solves, "
            "why to trust you, or what to do next.\n\nChecklist:"
        ),
    },
    {
        "pillar": "mini_guides",
        "cta_type": "template",
        "text": (
            "A simple hero section test:\n\n"
            "1. Name the audience\n2. Name the painful outcome\n3. Show proof\n"
            "4. Ask for one clear action\n\nTemplate:"
        ),
    },
    {
        "pillar": "cases",
        "cta_type": "case_study",
        "text": (
            "One client had traffic but no calls.\n\n"
            "We changed the offer from vague service copy to a specific audit promise. "
            "Same page, clearer reason to act.\n\nCase study:"
        ),
    },
    {
        "pillar": "breakdowns",
        "cta_type": "audit",
        "text": (
            "If your site gets clicks but no leads, inspect the promise before the colors.\n\n"
            "A weak promise makes every CTA feel expensive.\n\nAudit:"
        ),
    },
    {
        "pillar": "personal_experience",
        "cta_type": "newsletter",
        "text": (
            "The biggest lesson from reviewing landing pages: clarity beats cleverness.\n\n"
            "When the offer gets sharper, design suddenly starts working harder.\n\nNewsletter:"
        ),
    },
]


def main() -> None:
    settings = load_settings()
    service = QueueService(settings.data_path, settings.agent_queue_path)
    target_url = "https://yoursite.com/checklist"

    for index, example in enumerate(EXAMPLES, start=1):
        service.create_item(
            example["text"],
            source="seed",
            pillar=example["pillar"],
            cta_type=example["cta_type"],
            target_url=target_url,
            utm_campaign="landing_audit",
            utm_content=f"seed_{index:03d}",
            notes="Seeded offer-engine example.",
        )

    print(f"Seeded {len(EXAMPLES)} examples into {Path(settings.agent_queue_path)}")


if __name__ == "__main__":
    main()
