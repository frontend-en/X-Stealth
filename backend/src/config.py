"""Runtime configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    """Settings loaded from environment variables and optional .env file."""

    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    log_level: str = "INFO"
    cors_origins: str = ""
    dry_run: bool = True
    posting_enabled: bool = False

    x_base_url: str = "https://x.com"
    headless: bool = True
    slow_mo_ms: int = Field(default=0, ge=0, le=1000)
    viewport_width: int = Field(default=1365, ge=800, le=2560)
    viewport_height: int = Field(default=768, ge=600, le=1600)

    auth_state_path: Path = Path("auth.json")
    data_path: Path = Path("data/tweets.txt")
    logs_dir: Path = Path("logs")
    screenshots_dir: Path = Path("screenshots")
    traces_dir: Path = Path("traces")

    min_action_delay_ms: int = Field(default=300, ge=50, le=5000)
    max_action_delay_ms: int = Field(default=1600, ge=100, le=10000)
    min_post_interval_minutes: int = Field(default=180, ge=1, le=10080)
    scheduler_poll_seconds: int = Field(default=30, ge=5, le=3600)
    scheduler_max_publish_attempts: int = Field(default=3, ge=1, le=10)
    warmup_min_scrolls: int = Field(default=2, ge=0, le=20)
    warmup_max_scrolls: int = Field(default=5, ge=0, le=50)
    navigation_timeout_ms: int = Field(default=60000, ge=5000, le=180000)
    post_timeout_ms: int = Field(default=45000, ge=5000, le=180000)

    proxy_url: str | None = None

    agent_enabled: bool = True
    agent_queue_path: Path = Path("data/queue.jsonl")
    agent_events_path: Path = Path("data/agent_events.jsonl")
    agent_publish_requires_approval: bool = True
    agent_require_successful_dry_run_before_publish: bool = True

    openai_api_key: str | None = None
    openai_model: str | None = None
    pipeline_conversations_path: Path = Path("data/conversations.jsonl")
    pipeline_messages_path: Path = Path("data/chat_messages.jsonl")
    pipeline_runs_path: Path = Path("data/pipeline_runs.jsonl")

    @field_validator("max_action_delay_ms")
    @classmethod
    def validate_delay_range(cls, value: int, info) -> int:
        min_value = info.data.get("min_action_delay_ms")
        if min_value is not None and value < min_value:
            raise ValueError("max_action_delay_ms must be greater than or equal to min_action_delay_ms")
        return value

    @field_validator("warmup_max_scrolls")
    @classmethod
    def validate_scroll_range(cls, value: int, info) -> int:
        min_value = info.data.get("warmup_min_scrolls")
        if min_value is not None and value < min_value:
            raise ValueError("warmup_max_scrolls must be greater than or equal to warmup_min_scrolls")
        return value


def load_settings() -> Settings:
    """Load application settings."""
    return Settings()
