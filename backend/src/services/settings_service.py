"""Public settings projection."""

from __future__ import annotations

from src.api.schemas import PublicSettingsResponse, WarmupScrollRange
from src.config import Settings


def get_public_settings(settings: Settings) -> PublicSettingsResponse:
    """Return non-sensitive settings for the dashboard."""
    return PublicSettingsResponse(
        dryRun=settings.dry_run,
        postingEnabled=settings.posting_enabled,
        headless=settings.headless,
        xBaseUrl=settings.x_base_url,
        dataPath=settings.data_path.as_posix(),
        logsDir=settings.logs_dir.as_posix(),
        screenshotsDir=settings.screenshots_dir.as_posix(),
        tracesDir=settings.traces_dir.as_posix(),
        minPostIntervalMinutes=settings.min_post_interval_minutes,
        warmupScrollRange=WarmupScrollRange(min=settings.warmup_min_scrolls, max=settings.warmup_max_scrolls),
        hasAuthState=settings.auth_state_path.exists(),
        hasProxyConfigured=bool(settings.proxy_url),
    )
