"""High level orchestration for autoplay lesson execution."""
from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

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
        await ensure_logged_in(page, self.config, self.logger)
        await run_course(page, self.config, self.logger, self.stop_event, self.state)

    def request_stop(self) -> None:
        if not self.stop_event.is_set():
            self.logger.info("Richiesta di stop ricevuta")
            self.stop_event.set()


async def run_from_cli(config: RuntimeConfig) -> None:
    runner = Runner(config)
    await runner.run()


async def ensure_logged_in(page: Page, config: RuntimeConfig, logger) -> None:
    """Ensure the user is authenticated before proceeding."""

    try:
        password_field = page.locator("#password")
        login_container = page.locator(".flex.flex-col.h-screen.bg-white")
        password_present = await password_field.count() > 0
        container_present = await login_container.count() > 0
    except PlaywrightError:
        logger.debug("Impossibile determinare lo stato di login attuale")
        return

    if not password_present and not container_present:
        logger.debug("Sessione già autenticata, nessun login necessario")
        return

    if not config.username or not config.password:
        logger.warning("Pagina di login rilevata ma credenziali mancanti")
        return

    logger.info("Pagina di login rilevata, avvio autenticazione automatica per %s", config.username)

    try:
        username_field = page.locator("#username")
        if await username_field.count():
            await username_field.first.fill(config.username)
        else:
            logger.warning("Campo username non trovato nella pagina di login")
    except PlaywrightError:
        logger.warning("Impossibile compilare il campo username")

    try:
        if await password_field.count():
            await password_field.first.fill(config.password)
        else:
            logger.warning("Campo password non trovato nella pagina di login")
            return
    except PlaywrightError:
        logger.warning("Impossibile compilare il campo password")
        return

    try:
        login_button = page.locator('button:has-text("Accedi")')
        if await login_button.count():
            await login_button.first.click(timeout=int(config.click_timeout * 1000))
        else:
            logger.warning("Bottone di accesso non trovato")
    except PlaywrightError as exc:
        logger.warning("Errore durante il click sul bottone di accesso: %s", exc)
        return

    await page.wait_for_timeout(int(config.login_wait * 1000))

    try:
        await page.wait_for_load_state("networkidle", timeout=int(config.navigation_timeout * 1000))
    except PlaywrightTimeoutError:
        logger.debug("Timeout durante l'attesa del caricamento post login")

    try:
        await page.goto(config.url, wait_until="domcontentloaded", timeout=int(config.navigation_timeout * 1000))
    except PlaywrightError as exc:
        logger.warning("Impossibile ricaricare la pagina principale dopo il login: %s", exc)
        return

    await page.wait_for_timeout(int(config.login_wait * 1000))
