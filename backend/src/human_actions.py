"""Interaction helpers for Playwright.

These helpers add small randomized waits and ordinary UI interactions for
reliability. They are not intended to bypass platform detection or policies.
"""

from __future__ import annotations

import asyncio
import random

from playwright.async_api import Locator, Page


async def random_delay(min_ms: int = 300, max_ms: int = 1600) -> None:
    """Sleep for a random duration in milliseconds."""
    if max_ms < min_ms:
        max_ms = min_ms
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


async def human_mouse_move(page: Page, locator: Locator, min_ms: int = 300, max_ms: int = 1600) -> None:
    """Move to a locator before interacting with it."""
    await locator.scroll_into_view_if_needed()
    await random_delay(min_ms, max_ms)
    box = await locator.bounding_box()
    if box is None:
        return
    x = box["x"] + random.uniform(box["width"] * 0.25, box["width"] * 0.75)
    y = box["y"] + random.uniform(box["height"] * 0.25, box["height"] * 0.75)
    await page.mouse.move(x, y, steps=random.randint(8, 18))
    await random_delay(min_ms, max_ms)


async def human_type(locator: Locator, text: str, min_ms: int = 35, max_ms: int = 120) -> None:
    """Type text with variable key delay."""
    for char in text:
        await locator.type(char, delay=random.randint(min_ms, max_ms))
        if char in ".!?,\n" and random.random() < 0.35:
            await random_delay(120, 500)


async def human_scroll(page: Page, min_distance: int = 250, max_distance: int = 900) -> None:
    """Scroll the page by a random vertical distance."""
    distance = random.randint(min_distance, max_distance)
    if random.random() < 0.15:
        distance *= -1
    await page.mouse.wheel(0, distance)
    await random_delay(500, 1800)


async def random_micro_actions(page: Page, count: int = 2) -> None:
    """Perform a few harmless page-level actions."""
    for _ in range(max(0, count)):
        if random.random() < 0.75:
            await human_scroll(page)
        else:
            await random_delay(700, 2200)
