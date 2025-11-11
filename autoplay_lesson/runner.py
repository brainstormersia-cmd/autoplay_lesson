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
from queue import Queue
import threading

from .config import RuntimeConfig
from .logging_utils import configure_logging
from .lessons import WatchdogExpired, run_course
from .state import LessonState


class AutomationRunner:
    """Adapter used by the CustomTkinter shell.

    The class wraps the asynchronous :class:`Runner` so the GUI can execute
    the autoplay logic from a background thread while pushing feedback to the
    interface via callbacks.
    """

    def __init__(self, log_callback, progress_callback) -> None:
        self._log_callback = log_callback
        self._progress_callback = progress_callback
        self._runner: Runner | None = None
        self._log_queue: Queue[str] = Queue()
        self._drain_event = threading.Event()

    def run(self, config_dict) -> None:
        config = RuntimeConfig.from_dict(config_dict)
        configure_logging(config, log_queue=self._log_queue)
        self._start_drain_thread()
        self._runner = Runner(config)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._runner.run())
        finally:
            loop.close()
            self._stop_drain_thread()

    def request_stop(self) -> None:
        if self._runner is not None:
            self._runner.stop_event.set()

    def _start_drain_thread(self) -> None:
        self._drain_event.clear()

        def drain() -> None:
            while not self._drain_event.is_set() or not self._log_queue.empty():
                try:
                    message = self._log_queue.get(timeout=0.1)
                except Exception:
                    continue
                self._log_callback(message, "default")
                self._log_queue.task_done()

        self._drain_thread = threading.Thread(target=drain, daemon=True)
        self._drain_thread.start()

    def _stop_drain_thread(self) -> None:
        self._drain_event.set()
        if hasattr(self, "_drain_thread") and self._drain_thread.is_alive():
            self._drain_thread.join(timeout=1)


class CourseRecoveryError(RuntimeError):
    """Raised when a full browser relaunch is required to recover the run."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause
        self.cause = cause


class Runner:
    def __init__(self, config: RuntimeConfig, *, log_queue=None) -> None:
        self.config = config
        setup = configure_logging(config, log_queue=log_queue)
        self.logger = setup.logger
        self.stop_event = asyncio.Event()
        loaded_state = LessonState.load(config.state_file)
        if config.start_chapter is not None and (
            loaded_state.chapter_index is not None
            or loaded_state.lesson_title is not None
            or loaded_state.chapter_title is not None
        ):
            self.logger.info(
                "Capitolo iniziale specificato (%s): stato precedente ignorato",
                config.start_chapter,
            )
            loaded_state = LessonState()
            loaded_state.save(config.state_file)
        self.state = loaded_state

    async def run(self) -> None:
        self.logger.info("==== Avvio autoplay ====")
        self.logger.info(self.config.to_summary())
        relaunch_attempt = 0
        while not self.stop_event.is_set():
            try:
                async with launch_browser(self.config) as context:
                    await self._run_with_context(context)
                    return
            except asyncio.CancelledError:
                raise
            except CourseRecoveryError as exc:
                relaunch_attempt += 1
                max_attempts = self.config.browser_restart_attempts
                limit_label = max_attempts or "∞"
                delay = self._browser_restart_delay(relaunch_attempt)
                self.logger.warning(
                    "Richiesto rilancio browser (tentativo %s/%s) dopo errore: %s",
                    relaunch_attempt,
                    limit_label,
                    exc,
                )
                if max_attempts and relaunch_attempt > max_attempts:
                    self.logger.exception(
                        "Raggiunto il limite di rilanci browser (%s): interruzione",
                        max_attempts,
                    )
                    raise exc
                if delay > 0:
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        raise
                continue
            except Exception as exc:  # pragma: no cover - defensive
                relaunch_attempt += 1
                max_attempts = self.config.browser_restart_attempts
                delay = self._browser_restart_delay(relaunch_attempt)
                self.logger.exception(
                    "Errore critico '%s' (tentativo browser %s/%s): %s",
                    exc.__class__.__name__,
                    relaunch_attempt,
                    max_attempts or "∞",
                    exc,
                )
                if max_attempts and relaunch_attempt > max_attempts:
                    raise
                if delay > 0:
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        raise
                continue
        self.logger.info("Stop richiesto prima dell'avvio del browser")

    async def _run_with_context(self, context: BrowserContext) -> None:
        attempt = 0
        page: Optional[Page] = None
        loop = asyncio.get_running_loop()
        page_opened_at: Optional[float] = None
        try:
            while not self.stop_event.is_set():
                try:
                    if page is None:
                        page = await self._open_and_prepare_page(context)
                        page_opened_at = loop.time()
                    else:
                        page_opened_at = getattr(page, "_autoplay_opened_at", None)
                        if not isinstance(page_opened_at, (int, float)):
                            page_opened_at = loop.time()
                            setattr(page, "_autoplay_opened_at", page_opened_at)
                        refresh_interval = self.config.page_refresh_interval
                        if (
                            refresh_interval
                            and loop.time() - page_opened_at >= refresh_interval
                        ):
                            self.logger.info(
                                "Refresh programmato dopo %.0fs: riapertura pagina",
                                loop.time() - page_opened_at,
                            )
                            await self._close_page(page)
                            page = await self._open_and_prepare_page(context)
                            page_opened_at = loop.time()
                    setattr(page, "_autoplay_opened_at", page_opened_at)
                    await run_course(
                        page, self.config, self.logger, self.stop_event, self.state
                    )
                    return
                except (PlaywrightError, WatchdogExpired) as exc:
                    if self.stop_event.is_set():
                        self.logger.info(
                            "Stop richiesto durante la gestione di un errore Playwright"
                        )
                        return
                    attempt += 1
                    if isinstance(exc, WatchdogExpired):
                        label = "Watchdog"
                    elif isinstance(exc, PlaywrightTimeoutError):
                        label = "Timeout"
                    else:
                        label = "Errore"
                    if attempt > self.config.course_restart_attempts:
                        message = (
                            f"{label} Playwright non recuperabile dopo {attempt} tentativi"
                        )
                        self.logger.exception("%s: %s", message, exc)
                        raise CourseRecoveryError(message, cause=exc)
                    delay = self._restart_delay(attempt)
                    self.logger.warning(
                        "%s Playwright rilevato (tentativo %s/%s): %s. Riavvio pagina tra %.1fs",
                        label,
                        attempt,
                        self.config.course_restart_attempts,
                        exc,
                        delay,
                    )
                    await self._close_page(page)
                    page = None
                    page_opened_at = None
                    if delay > 0:
                        await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # pragma: no cover - ultra defensive guard
                    if self.stop_event.is_set():
                        self.logger.info(
                            "Stop richiesto durante la gestione di un errore inaspettato"
                        )
                        return
                    attempt += 1
                    label = exc.__class__.__name__
                    if attempt > self.config.course_restart_attempts:
                        message = (
                            f"Errore inatteso {label} non recuperabile dopo {attempt} tentativi"
                        )
                        self.logger.exception("%s: %s", message, exc)
                        raise CourseRecoveryError(message, cause=exc)
                    delay = self._restart_delay(attempt)
                    self.logger.exception(
                        "Errore inatteso %s (tentativo %s/%s): %s. Riavvio pagina tra %.1fs",
                        label,
                        attempt,
                        self.config.course_restart_attempts,
                        exc,
                        delay,
                    )
                    await self._close_page(page)
                    page = None
                    page_opened_at = None
                    if delay > 0:
                        await asyncio.sleep(delay)
            self.logger.info(
                "Stop richiesto, interruzione del corso prima del prossimo tentativo"
            )
        finally:
            await self._close_page(page)

    async def _open_and_prepare_page(self, context: BrowserContext) -> Page:
        page = await open_page(
            context,
            self.config.url,
            timeout=int(self.config.navigation_timeout * 1000),
        )
        self.logger.info("Pagina corrente: %s", page.url)
        await ensure_logged_in(page, self.config, self.logger)
        return page

    def _restart_delay(self, attempt: int) -> float:
        if attempt <= 0:
            return 0.0
        delay = self.config.course_restart_base_delay * (
            self.config.course_restart_backoff ** (attempt - 1)
        )
        return min(delay, self.config.course_restart_max_delay)

    def _browser_restart_delay(self, attempt: int) -> float:
        if attempt <= 0:
            return 0.0
        delay = self.config.browser_restart_base_delay * (
            self.config.browser_restart_backoff ** (attempt - 1)
        )
        return min(delay, self.config.browser_restart_max_delay)

    async def _close_page(self, page: Optional[Page]) -> None:
        if page is None:
            return
        try:
            await page.close()
        except PlaywrightError as exc:
            self.logger.debug("Errore durante la chiusura della pagina: %s", exc)

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
