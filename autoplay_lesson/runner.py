"""High level orchestration for autoplay lesson execution."""
from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Locator,
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


PASSWORD_SELECTORS: tuple[str, ...] = ("#password", "input[type='password']")
USERNAME_SELECTORS: tuple[str, ...] = ("#username", "input[name*='user']", "input[id*='user']")
SUBMIT_SELECTORS: tuple[str, ...] = (
    "button:has-text(\"Accedi\")",
    "button[type='submit']",
    "button:has-text('Login')",
)


async def _find_login_form(page: Page) -> tuple[Locator | None, Locator | None, Locator | None]:
    """Return locators for username, password and submit button if a login form is present."""

    frames = [page.main_frame, *[frame for frame in page.frames if frame != page.main_frame]]
    for frame in frames:
        for password_selector in PASSWORD_SELECTORS:
            try:
                password_field = frame.locator(password_selector)
                if not await password_field.count():
                    continue
            except PlaywrightError:
                continue

            username_field: Locator | None = None
            for username_selector in USERNAME_SELECTORS:
                try:
                    candidate = frame.locator(username_selector)
                except PlaywrightError:
                    continue
                try:
                    if await candidate.count():
                        username_field = candidate
                        break
                except PlaywrightError:
                    continue

            submit_button: Locator | None = None
            for button_selector in SUBMIT_SELECTORS:
                try:
                    candidate = frame.locator(button_selector)
                except PlaywrightError:
                    continue
                try:
                    if await candidate.count():
                        submit_button = candidate
                        break
                except PlaywrightError:
                    continue

            return username_field, password_field, submit_button

    return None, None, None


async def ensure_logged_in(page: Page, config: RuntimeConfig, logger) -> None:
    """Ensure the user is authenticated before proceeding."""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + config.page_timeout
    username_field: Locator | None = None
    password_field: Locator | None = None
    submit_button: Locator | None = None

    while loop.time() < deadline:
        username_field, password_field, submit_button = await _find_login_form(page)
        if password_field is not None:
            break
        await page.wait_for_timeout(500)

    if password_field is None:
        logger.debug("Sessione già autenticata, nessun login necessario")
        return

    if not config.username or not config.password:
        logger.warning("Pagina di login rilevata ma credenziali mancanti")
        return

    logger.info("Pagina di login rilevata, avvio autenticazione automatica per %s", config.username)

    if username_field is not None:
        try:
            await username_field.first.fill(config.username)
        except PlaywrightError:
            logger.warning("Impossibile compilare il campo username")
    else:
        logger.warning("Campo username non trovato nella pagina di login")

    try:
        await password_field.first.fill(config.password)
    except PlaywrightError:
        logger.warning("Impossibile compilare il campo password")
        return

    if submit_button is not None:
        try:
            await submit_button.first.click(timeout=int(config.click_timeout * 1000))
        except PlaywrightError as exc:
            logger.warning("Errore durante il click sul bottone di accesso: %s", exc)
            return
    else:
        logger.warning("Bottone di accesso non trovato, invio con Enter")
        try:
            await password_field.first.press("Enter")
        except PlaywrightError:
            logger.warning("Impossibile inviare il form di login")
            return

    await page.wait_for_timeout(int(config.login_wait * 1000))

    try:
        await page.wait_for_load_state("networkidle", timeout=int(config.navigation_timeout * 1000))
    except PlaywrightTimeoutError:
        logger.debug("Timeout durante l'attesa del caricamento post login")

    try:
        await page.goto(
            config.url,
            wait_until="domcontentloaded",
            timeout=int(config.navigation_timeout * 1000),
        )
    except PlaywrightError as exc:
        logger.warning("Impossibile ricaricare la pagina principale dopo il login: %s", exc)
        return

    await page.wait_for_timeout(int(config.login_wait * 1000))
