"""Browser context creation.

The original specification requested fingerprint spoofing and stealth patches.
This implementation intentionally does not include anti-detection code. It
creates a regular Playwright Chromium context suitable for explicit,
rate-limited automation controlled by the account owner.
"""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Browser, BrowserContext

from .config import Settings


async def apply_extra_stealth(context: BrowserContext) -> None:
    """Compatibility hook kept for the spec's module shape.

    No stealth or fingerprint spoofing scripts are injected here.
    """
    return None


async def create_stealth_context(browser: Browser, settings: Settings) -> BrowserContext:
    """Create a normal browser context using configured storage state when available."""
    storage_state = (
        settings.auth_state_path
        if settings.auth_state_path.is_file() and settings.auth_state_path.stat().st_size > 0
        else None
    )
    context = await browser.new_context(
        viewport={"width": settings.viewport_width, "height": settings.viewport_height},
        storage_state=str(storage_state) if storage_state else None,
        locale="en-US",
        timezone_id="UTC",
    )
    context.set_default_timeout(settings.navigation_timeout_ms)
    await apply_extra_stealth(context)
    return context
