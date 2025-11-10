"""Playwright browser helpers."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from playwright.async_api import BrowserContext, Page, async_playwright

from .config import RuntimeConfig


@asynccontextmanager
async def launch_browser(config: RuntimeConfig) -> AsyncIterator[BrowserContext]:
    """Launch a Chrome-based persistent context based on configuration."""

    playwright = await async_playwright().start()
    user_data_dir: Optional[str] = None
    if config.use_chrome_profile and config.user_data_dir:
        user_data_dir = str(Path(config.user_data_dir).expanduser())

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        channel="chrome",
        headless=config.headless,
        slow_mo=config.slow_mo,
        viewport={"width": 1600, "height": 900},
    )

    try:
        yield context
    finally:
        await context.close()
        await playwright.stop()


async def open_page(context: BrowserContext, url: str, *, timeout: float) -> Page:
    pages = context.pages
    if pages:
        page = pages[0]
    else:
        page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    return page


async def close_context(context: BrowserContext) -> None:
    await context.close()
