"""High level orchestration for autoplay lesson execution."""
from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import BrowserContext

from .browser import launch_browser, open_page
from .config import RuntimeConfig
from .logging_utils import configure_logging
from .lessons import run_course
from .state import LessonState


class Runner:
    def __init__(self, config: RuntimeConfig, *, log_queue=None) -> None:
        self.config = config
        setup = configure_logging(config, log_queue=log_queue)
        self.logger = setup.logger
        self.stop_event = asyncio.Event()
        self.state = LessonState.load(config.state_file)

    async def run(self) -> None:
        self.logger.info("==== Avvio autoplay ====")
        self.logger.info(self.config.to_summary())
        try:
            async with launch_browser(self.config) as context:
                await self._run_with_context(context)
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.exception("Errore durante l'esecuzione: %s", exc)
            raise

    async def _run_with_context(self, context: BrowserContext) -> None:
        page = await open_page(context, self.config.url, timeout=self.config.navigation_timeout * 1000)
        self.logger.info("Pagina corrente: %s", page.url)
        await run_course(page, self.config, self.logger, self.stop_event, self.state)

    def request_stop(self) -> None:
        if not self.stop_event.is_set():
            self.logger.info("Richiesta di stop ricevuta")
            self.stop_event.set()


async def run_from_cli(config: RuntimeConfig) -> None:
    runner = Runner(config)
    await runner.run()
