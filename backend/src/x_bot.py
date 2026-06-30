"""X.com posting workflow."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from playwright.async_api import Browser, Page, TimeoutError as PlaywrightTimeoutError, async_playwright
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from .config import Settings
from .human_actions import human_mouse_move, human_scroll, human_type, random_delay, random_micro_actions
from .stealth import create_stealth_context


class XBotError(RuntimeError):
    """Base bot error."""


class XAuthError(XBotError):
    """Raised when the session is not authenticated."""


class XPostError(XBotError):
    """Raised when posting fails."""


class XBot:
    """Browser-backed X posting client."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = logger.bind(component="x_bot")

    async def run_once(self, text: str) -> bool:
        """Open a browser and publish one configured post."""
        if self.settings.dry_run or not self.settings.posting_enabled:
            self.log.info(
                "Dry run: posting skipped",
                dry_run=self.settings.dry_run,
                posting_enabled=self.settings.posting_enabled,
                text_length=len(text),
            )
            return True

        async with async_playwright() as p:
            browser = await self._launch_browser(p)
            try:
                context = await create_stealth_context(browser, self.settings)
                if self.settings.traces_dir:
                    self.settings.traces_dir.mkdir(parents=True, exist_ok=True)
                    await context.tracing.start(screenshots=True, snapshots=True, sources=True)

                page = await context.new_page()
                try:
                    await self.warm_up_session(page)
                    result = await self.post_tweet(page, text)
                    return result
                except Exception as exc:
                    await self._capture_failure(page, exc)
                    raise
                finally:
                    if self.settings.traces_dir:
                        trace_path = self.settings.traces_dir / f"trace-{self._timestamp()}.zip"
                        await context.tracing.stop(path=str(trace_path))
                    await context.close()
            finally:
                await browser.close()

    async def warm_up_session(self, page: Page) -> None:
        """Load the home timeline and perform a short, ordinary warm-up."""
        self.log.info("Opening X home timeline")
        await page.goto(f"{self.settings.x_base_url}/home", wait_until="domcontentloaded")
        await self.handle_x_errors(page)
        await self._ensure_authenticated(page)

        scroll_count = self._random_scroll_count()
        self.log.info("Warm-up started", scroll_count=scroll_count)
        for _ in range(scroll_count):
            await human_scroll(page)
        await random_micro_actions(page, count=1)

    @retry(
        retry=retry_if_exception_type((PlaywrightTimeoutError, XPostError)),
        wait=wait_exponential_jitter(initial=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def post_tweet(self, page: Page, text: str) -> bool:
        """Publish a post and verify that the composer completes."""
        if not text.strip():
            raise XPostError("Tweet text is empty")
        if len(text) > 280:
            raise XPostError("Tweet text exceeds 280 characters")

        self.log.info("Opening compose page", text_length=len(text))
        await page.goto(f"{self.settings.x_base_url}/compose/post", wait_until="domcontentloaded")
        await self.handle_x_errors(page)
        await self._ensure_authenticated(page)

        textbox = page.get_by_role("textbox").first
        await textbox.wait_for(state="visible", timeout=self.settings.post_timeout_ms)
        await human_mouse_move(page, textbox, self.settings.min_action_delay_ms, self.settings.max_action_delay_ms)
        await textbox.click()
        await human_type(textbox, text)
        await random_delay(self.settings.min_action_delay_ms, self.settings.max_action_delay_ms)

        post_button = page.get_by_test_id("tweetButton").or_(page.get_by_test_id("tweetButtonInline")).first
        await post_button.wait_for(state="visible", timeout=self.settings.post_timeout_ms)
        if not await post_button.is_enabled():
            raise XPostError("Post button is disabled")

        await human_mouse_move(page, post_button, self.settings.min_action_delay_ms, self.settings.max_action_delay_ms)
        await post_button.click()
        await self._wait_for_post_completion(page)
        self.log.info("Post completed")
        return True

    async def handle_x_errors(self, page: Page) -> None:
        """Detect common visible X errors and stop early with a clear message."""
        body = await page.locator("body").inner_text(timeout=15000)
        normalized = re.sub(r"\s+", " ", body).lower()
        error_markers = {
            "rate limit": "Rate limit message detected",
            "something went wrong": "Generic X error detected",
            "try again later": "Temporary X error detected",
            "account is suspended": "Account suspension message detected",
        }
        for marker, message in error_markers.items():
            if marker in normalized:
                raise XPostError(message)

    async def _launch_browser(self, playwright) -> Browser:
        launch_kwargs: dict[str, object] = {
            "headless": self.settings.headless,
            "slow_mo": self.settings.slow_mo_ms,
        }
        if self.settings.proxy_url:
            launch_kwargs["proxy"] = {"server": self.settings.proxy_url}
        return await playwright.chromium.launch(**launch_kwargs)

    async def _ensure_authenticated(self, page: Page) -> None:
        login_indicators = [
            page.get_by_text("Sign in", exact=True),
            page.get_by_text("Log in", exact=True),
            page.locator('input[name="text"]'),
        ]
        for indicator in login_indicators:
            if await indicator.count() and await indicator.first.is_visible():
                raise XAuthError(
                    f"X session is not authenticated. Create {self.settings.auth_state_path} with an account-owned session."
                )

    async def _wait_for_post_completion(self, page: Page) -> None:
        try:
            await page.get_by_test_id("toast").wait_for(state="visible", timeout=15000)
            return
        except PlaywrightTimeoutError:
            pass

        composer = page.get_by_role("textbox").first
        try:
            await composer.wait_for(state="hidden", timeout=15000)
        except PlaywrightTimeoutError as exc:
            await self.handle_x_errors(page)
            raise XPostError("Post did not complete within timeout") from exc

    async def _capture_failure(self, page: Page, exc: Exception) -> None:
        self.settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.screenshots_dir / f"failure-{self._timestamp()}.png"
        try:
            await page.screenshot(path=str(path), full_page=True)
            self.log.exception("Bot failure captured", screenshot=str(path), error=str(exc))
        except Exception:
            self.log.exception("Bot failure; screenshot capture also failed", error=str(exc))

    def _random_scroll_count(self) -> int:
        import random

        return random.randint(self.settings.warmup_min_scrolls, self.settings.warmup_max_scrolls)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
