"""Lesson discovery and playback logic."""
from __future__ import annotations

import asyncio
import math
import random
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, Optional

from playwright.async_api import (
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from .config import CourseMode, DURATION_PATTERN, RuntimeConfig
from .quizzes import QuizSolver
from .selectors import LESSON_SELECTORS, OVERLAY_SELECTORS
from .state import LessonState

LS = LESSON_SELECTORS
OS = OVERLAY_SELECTORS

OVERLAY_CANDIDATE_SELECTORS: tuple[str, ...] = (
    "div.fixed.inset-0",
    "div.fixed.top-0.left-0.right-0.bottom-0",
    "div.fixed[class*='z-']",
    "div[class*='bg-black\\/20'][class*='fixed']",
    "div[class*='overlay'][class*='fixed']",
    "div[class*='modal'][class*='fixed']",
)

OVERLAY_BUTTON_LABELS: tuple[str, ...] = (
    "Chiudi",
    "Chiudi X",
    "Close",
    "Ok",
    "OK",
    "Continua",
    "Ho capito",
    "Comprendo",
)


def _selector(config: RuntimeConfig, key: str, default: str) -> str:
    return config.selector_overrides.get(key, default)


def _normalize_label(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _titles_equal(first: str, second: str) -> bool:
    return _normalize_label(first).lower() == _normalize_label(second).lower()


def _is_quiz_title(title: str) -> bool:
    lowered = title.lower()
    return any(keyword in lowered for keyword in LS.quiz_keywords)


def _classify_lesson_href(href: str) -> str:
    lowered = href.lower()
    if "/lecture/" in lowered:
        return "video"
    if "/supplement/" in lowered:
        return "reading"
    if "/discussionprompt/" in lowered:
        return "discussion"
    if "/ungradedlti/" in lowered:
        return "app"
    if "/assignment-submission/" in lowered:
        return "assignment"
    if "/assignment/" in lowered:
        return "quiz"
    return "unknown"


def _extract_chapter_number(title: str) -> Optional[int]:
    match = re.search(r"\b(\d{1,4})\b", title)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _chapter_exact_match(title: str, target: int) -> bool:
    normalized = _normalize_label(title)
    number = re.escape(str(target))
    pattern = re.compile(rf"^(?:capitolo|lezione)?\s*{number}(?:(?=\s)|[.:\-–—]|$)", re.IGNORECASE)
    if pattern.match(normalized):
        return True
    bare = re.compile(rf"^{number}(?:(?=\s)|[.:\-–—]|$)")
    return bool(bare.match(normalized))


def _chapter_contains_number(title: str, target: int) -> bool:
    number = re.escape(str(target))
    return bool(re.search(rf"\b{number}\b", title, re.IGNORECASE))


def _find_start_chapter_index(
    chapters: list["ChapterBounds"], target: int, logger
) -> Optional[int]:
    if 1 <= target <= len(chapters):
        bounds = chapters[target - 1]
        logger.info(
            "Capitolo iniziale %s -> match per indice con '%s'",
            target,
            _chapter_log_label(bounds),
        )
        return target - 1
    exact: list[int] = []
    partial: list[int] = []
    for idx, bounds in enumerate(chapters):
        if bounds.number is not None and bounds.number == target:
            exact.append(idx)
            continue
        if _chapter_exact_match(bounds.title, target):
            exact.append(idx)
            continue
        if _chapter_contains_number(bounds.title, target):
            partial.append(idx)
    if exact:
        label = _chapter_log_label(chapters[exact[0]])
        logger.info(
            "Capitolo iniziale %s -> match diretto con '%s'",
            target,
            label,
        )
        return exact[0]
    if partial:
        label = _chapter_log_label(chapters[partial[0]])
        logger.info(
            "Capitolo iniziale %s -> match parziale con '%s'",
            target,
            label,
        )
        return partial[0]
    logger.warning(
        "Capitolo iniziale %s non trovato nell'elenco: verrà usato il primo disponibile",
        target,
    )
    return None


async def _sleep_with_stop(stop_event: asyncio.Event, seconds: float) -> None:
    if seconds <= 0:
        return
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while not stop_event.is_set():
        remaining = deadline - loop.time()
        if remaining <= 0:
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=min(1.0, remaining))
        except asyncio.TimeoutError:
            continue


def _estimate_remaining_seconds(
    candidate: "LessonCandidate",
    progress: int,
    *,
    base_wait: float,
    default_total: float,
) -> float:
    video_length = candidate.duration_seconds or max(base_wait, default_total)
    remaining = max(0.0, video_length * (100 - progress) / 100.0)
    return max(0.0, remaining)


@dataclass(slots=True)
class ChapterBounds:
    index: int  # 1-based for logging
    title: str
    container: Locator
    click_target: Locator
    y_min: float
    y_max: float
    number: Optional[int]


def _chapter_log_label(bounds: ChapterBounds) -> str:
    prefix = str(bounds.number) if bounds.number is not None else f"#{bounds.index}"
    title = _normalize_label(bounds.title)
    if title.lower().startswith(prefix.lower()):
        return title
    return f"{prefix} - {title}" if title else prefix


@dataclass(slots=True)
class LessonCandidate:
    title: str
    title_raw: str
    duration_label: Optional[str]
    duration_seconds: Optional[int]
    progress: Optional[int]
    locator: Locator
    bounding_box: Optional[dict[str, float]]
    is_quiz: bool
    completion_hint: bool
    skip_reason: Optional[str]

    @property
    def playable(self) -> bool:
        return self.skip_reason is None


@dataclass(slots=True)
class IncompleteLesson:
    chapter_index: int
    chapter_title: str
    lesson_title: str
    progress: int


@dataclass(slots=True)
class VerificationResult:
    total_chapters: int
    total_lessons: int
    completed_lessons: int
    incomplete_lessons: list[IncompleteLesson]
    open_failures: int = 0

    @property
    def missing_count(self) -> int:
        return len(self.incomplete_lessons)

    @property
    def lowest_incomplete(self) -> Optional[IncompleteLesson]:
        if not self.incomplete_lessons:
            return None
        return min(
            self.incomplete_lessons,
            key=lambda item: (item.chapter_index, item.progress, item.lesson_title),
        )


class WatchdogExpired(RuntimeError):
    """Raised when the activity watchdog reaches the configured timeout."""

    def __init__(self, message: str, *, elapsed: Optional[float] = None) -> None:
        super().__init__(message)
        self.elapsed = elapsed


class CourseContextBlocked(RuntimeError):
    """Raised when the course UI becomes unresponsive or blocked by overlays."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ActivityWatchdog:
    """Background watchdog that requests a restart if no activity is recorded."""

    def __init__(self, timeout: float, *, grace: int, logger) -> None:
        self.timeout = max(0.0, timeout)
        self.grace = max(0, grace)
        self.logger = logger
        self._last_ping = time.monotonic()
        self._last_label = "startup"
        self._task: Optional[asyncio.Task[None]] = None
        self._expired = asyncio.Event()
        self._expired_message = ""
        self._elapsed_on_expire = 0.0
        self._grace_used = 0

    def start(self, stop_event: asyncio.Event) -> None:
        if self.timeout <= 0:
            return
        self._last_ping = time.monotonic()
        self._last_label = "startup"
        self._expired.clear()
        self._expired_message = ""
        self._elapsed_on_expire = 0.0
        self._grace_used = 0
        self._task = asyncio.create_task(self._monitor(stop_event))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    def ping(self, label: str) -> None:
        if self.timeout <= 0:
            return
        self._last_ping = time.monotonic()
        self._last_label = label
        self._grace_used = 0

    async def _monitor(self, stop_event: asyncio.Event) -> None:
        interval = max(2.0, self.timeout / 3.0)
        while not stop_event.is_set():
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return
            if stop_event.is_set():
                return
            elapsed = time.monotonic() - self._last_ping
            if elapsed > self.timeout:
                self._grace_used += 1
                log = self.logger.warning if self._grace_used <= self.grace else self.logger.error
                log(
                    "Watchdog inattivo da %.1fs durante '%s' (grace %s/%s)",
                    elapsed,
                    self._last_label,
                    min(self._grace_used, self.grace),
                    self.grace,
                )
                if self._grace_used > self.grace:
                    self._expired_message = (
                        f"Timeout inattività dopo {elapsed:.1f}s (ultimo step: {self._last_label})"
                    )
                    self._elapsed_on_expire = elapsed
                    self._expired.set()
                    return
                self._last_ping = time.monotonic()

    def raise_if_expired(self) -> None:
        if self._expired.is_set():
            raise WatchdogExpired(
                self._expired_message or f"Timeout inattività (ultimo step: {self._last_label})",
                elapsed=self._elapsed_on_expire or None,
            )

    def expired(self) -> bool:
        return self._expired.is_set()

    @property
    def last_label(self) -> str:
        return self._last_label

def _reset_state(state: LessonState, config: RuntimeConfig) -> None:
    state.chapter_index = None
    state.chapter_title = None
    state.lesson_title = None
    state.save(config.state_file)


async def ensure_cookies(page: Page, logger) -> None:
    """Attempt to close cookie overlays if they appear."""

    candidates = ["Accetta", "Chiudi", "Rifiuta", "Accept", "Close"]
    for label in candidates:
        try:
            button = page.locator(f"text={label}")
            if await button.count():
                logger.info("Click overlay button '%s'", label)
                try:
                    await button.first.click(timeout=1000)
                except PlaywrightError:
                    continue
        except PlaywrightError:
            continue


async def dismiss_video_restriction_popup(page: Page, config: RuntimeConfig, logger) -> bool:
    """Automatically close the video restriction popup if it appears."""

    try:
        header = page.locator(
            f"{LS.video_block_header}:has-text('{LS.video_block_header_text}')"
        )
    except PlaywrightError:
        return False
    try:
        if not await header.count():
            return False
    except PlaywrightError:
        return False

    logger.warning("Popup 'Riproduzione del video non consentita' rilevato")

    button = page.locator(
        f"{LS.video_block_confirm}:has-text('OK')"
    )
    try:
        if await button.count():
            try:
                await button.first.click(timeout=int(config.click_timeout * 1000))
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=int(config.navigation_timeout * 1000)
                    )
                except PlaywrightTimeoutError:
                    logger.debug(
                        "Timeout durante l'attesa del reload dopo il popup di blocco video"
                    )
                await page.wait_for_timeout(500)
                return True
            except PlaywrightError as exc:
                logger.error(
                    "Errore durante la chiusura del popup di blocco video: %s", exc
                )
        else:
            logger.error(
                "Bottone 'OK' non trovato nel popup di blocco video"
            )
    except PlaywrightError as exc:
        logger.error(
            "Errore nel rilevamento del bottone del popup di blocco video: %s", exc
        )
    return False


async def _detect_blocking_overlays(page: Page) -> list[Locator]:
    overlays: list[Locator] = []
    for selector in OS.candidates:
        try:
            candidate = page.locator(selector)
        except PlaywrightError:
            continue
        try:
            count = await candidate.count()
        except PlaywrightError:
            continue
        if count:
            overlay = candidate.first
            try:
                bbox = await overlay.bounding_box()
            except PlaywrightError:
                bbox = None
            if bbox and bbox.get("width", 0) <= 20 and bbox.get("height", 0) <= 20:
                continue
            try:
                pointer_enabled = await overlay.evaluate(
                    "el => getComputedStyle(el).pointerEvents !== 'none'"
                )
            except PlaywrightError:
                pointer_enabled = True
            if not pointer_enabled:
                continue
            overlays.append(overlay)
    return overlays


async def _dismiss_blocking_overlay(
    page: Page,
    logger,
    *,
    context: str,
    overlays: Optional[list[Locator]] = None,
) -> bool:
    if overlays is None:
        overlays = await _detect_blocking_overlays(page)
    if not overlays:
        return False
    logger.warning(
        "Overlay bloccante rilevato durante %s: tentativo di chiusura", context
    )

    async def _overlay_active() -> bool:
        detected = await _detect_blocking_overlays(page)
        return bool(detected)

    for overlay in overlays:
        for label in OS.button_labels:
            try:
                button = overlay.locator(f"button:has-text('{label}')").first
                if await button.count():
                    try:
                        await button.click(timeout=1500)
                        await page.wait_for_timeout(300)
                        if not await _overlay_active():
                            logger.info(
                                "Overlay chiuso cliccando il bottone '%s'", label
                            )
                            return True
                    except PlaywrightError:
                        continue
            except PlaywrightError:
                continue
        try:
            role_buttons = overlay.locator("[role='button']")
            count = await role_buttons.count()
        except PlaywrightError:
            count = 0
        for idx in range(count):
            try:
                await role_buttons.nth(idx).click(timeout=1500)
                await page.wait_for_timeout(300)
                if not await _overlay_active():
                    logger.info(
                        "Overlay chiuso tramite elemento role=button durante %s",
                        context,
                    )
                    return True
            except PlaywrightError:
                continue

    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(200)
        if not await _overlay_active():
            logger.info("Overlay chiuso premendo ESC")
            return True
    except PlaywrightError:
        pass

    for overlay in await _detect_blocking_overlays(page):
        try:
            box = await overlay.bounding_box()
        except PlaywrightError:
            box = None
        if not box:
            continue
        try:
            await page.mouse.click(box["x"] + 5, box["y"] + 5)
            await page.wait_for_timeout(200)
        except PlaywrightError:
            continue
        if not await _overlay_active():
            logger.info("Overlay chiuso cliccando sullo sfondo")
            return True

    logger.warning("Overlay bloccante persistente durante %s", context)
    return False


async def _soft_reload_course_page(
    page: Page,
    config: RuntimeConfig,
    logger,
    *,
    stop_event: asyncio.Event,
    watchdog: Optional["ActivityWatchdog"] = None,
) -> bool:
    if stop_event.is_set():
        return False
    logger.info("Recupero corso: reload pagina in corso")
    try:
        await page.reload(
            wait_until="domcontentloaded",
            timeout=int(config.navigation_timeout * 1000),
        )
    except PlaywrightError as exc:
        logger.error("Reload pagina fallito: %s", exc)
        return False
    if stop_event.is_set():
        return False
    try:
        await page.wait_for_timeout(int(config.lesson_render_wait * 1000))
    except PlaywrightError:
        pass
    if watchdog:
        watchdog.ping("reload corso")
    await ensure_cookies(page, logger)
    try:
        await _dismiss_blocking_overlay(page, logger, context="reload corso")
    except PlaywrightError:
        pass
    return True


async def _navigate_to_course_root(
    page: Page,
    config: RuntimeConfig,
    logger,
    *,
    stop_event: asyncio.Event,
    watchdog: Optional["ActivityWatchdog"] = None,
) -> bool:
    if stop_event.is_set():
        return False
    logger.info("Recupero corso: riapertura pagina principale")
    try:
        await page.goto(
            config.url,
            wait_until="domcontentloaded",
            timeout=int(config.navigation_timeout * 1000),
        )
    except PlaywrightError as exc:
        logger.error("Riapertura pagina principale fallita: %s", exc)
        return False
    if stop_event.is_set():
        return False
    try:
        await page.wait_for_timeout(int(config.login_wait * 1000))
    except PlaywrightError:
        pass
    if watchdog:
        watchdog.ping("riapertura corso")
    await ensure_cookies(page, logger)
    try:
        await _dismiss_blocking_overlay(page, logger, context="riapertura corso")
    except PlaywrightError:
        pass
    return True


async def _apply_course_recovery(
    page: Page,
    config: RuntimeConfig,
    logger,
    *,
    reason: str,
    start_step: int,
    stop_event: asyncio.Event,
    watchdog: Optional["ActivityWatchdog"] = None,
) -> tuple[bool, int]:
    steps: tuple[tuple[str, Callable[..., Awaitable[bool]]], ...] = (
        ("reload morbido", _soft_reload_course_page),
        ("riapertura corso", _navigate_to_course_root),
    )
    total = len(steps)
    step_index = max(0, start_step)
    while step_index < total and not stop_event.is_set():
        label, action = steps[step_index]
        logger.warning(
            "Recupero corso step %s/%s (%s) dopo blocco: %s",
            step_index + 1,
            total,
            label,
            reason,
        )
        try:
            recovered = await action(
                page,
                config,
                logger,
                stop_event=stop_event,
                watchdog=watchdog,
            )
        except PlaywrightError as exc:
            logger.error("Recupero step '%s' fallito per errore Playwright: %s", label, exc)
            recovered = False
        if recovered:
            logger.info("Recupero corso step %s completato (%s)", step_index + 1, label)
            return True, step_index + 1
        logger.error("Recupero corso step %s fallito (%s)", step_index + 1, label)
        step_index += 1
    return False, step_index


async def collect_chapter_bounds(page: Page, logger, config: RuntimeConfig) -> list[ChapterBounds]:
    containers = page.locator(
        _selector(config, "chapter_container", LS.chapter_container)
    )
    count = await containers.count()
    results: list[ChapterBounds] = []

    for idx in range(count):
        container = containers.nth(idx)
        header_locator = container.locator(
            _selector(config, "chapter_header", LS.chapter_header)
        )
        header_count = await header_locator.count()
        click_target = header_locator.first if header_count else container
        title_source = header_locator.first if header_count else click_target
        try:
            title = (await title_source.inner_text()).strip()
        except PlaywrightError:
            title = f"Capitolo {idx + 1}"
        try:
            bbox = await container.bounding_box()
        except PlaywrightError:
            bbox = None
        y_min = bbox["y"] if bbox else float("nan")
        y_max = float("inf")
        results.append(
            ChapterBounds(
                index=idx + 1,
                title=title,
                container=container,
                click_target=click_target,
                y_min=y_min,
                y_max=y_max,
                number=_extract_chapter_number(title),
            )
        )

    for idx, current in enumerate(results):
        if idx < len(results) - 1:
            nxt = results[idx + 1]
            next_min = nxt.y_min
            if math.isnan(next_min):
                current.y_max = float("inf")
            else:
                current.y_max = next_min - 15
        else:
            current.y_max = float("inf")
        if not math.isnan(current.y_min):
            if math.isnan(current.y_max):
                current.y_max = float("inf")
            if current.y_max - current.y_min < 200:
                current.y_max = current.y_min + 400
    return results


def _title_skip_reason(
    title: str,
    progress: Optional[int],
    config: RuntimeConfig,
    *,
    is_quiz: bool,
    completion_hint: bool = False,
) -> Optional[str]:
    lowered = title.lower()
    for keyword in LS.title_exclusions:
        if keyword in lowered:
            return f"titolo contiene '{keyword}'"
    if is_quiz:
        if completion_hint and (progress is None or progress >= config.progress_threshold):
            return "quiz già completato (indicatore pagina)"
        if config.course_mode == CourseMode.COURSES_ONLY:
            return "quiz escluso dalla modalità Solo Corsi"
    else:
        if config.course_mode == CourseMode.QUIZ_ONLY:
            return "lezione esclusa dalla modalità Solo Quiz"
    if progress is not None and progress >= config.progress_threshold:
        return f"progress {progress}% >= soglia"
    for pattern in config.blacklist:
        if pattern.search(title):
            return f"blacklist {pattern.pattern}"
    if config.whitelist and not any(pattern.search(title) for pattern in config.whitelist):
        return "non in whitelist"
    return None


async def _extract_percentage(row: Locator, config: RuntimeConfig) -> Optional[int]:
    try:
        cell_locator = row.locator(
            _selector(config, "percentage", LS.percentage)
        )
        for idx in range(await cell_locator.count()):
            try:
                text = (await cell_locator.nth(idx).inner_text(timeout=750)).strip()
            except PlaywrightError:
                continue
            match = re.search(r"(\d{1,3})%", text)
            if match:
                return int(match.group(1))
    except PlaywrightError:
        pass
    try:
        aria_locator = row.locator(
            ":scope [role='progressbar'][aria-valuenow]"
        )
        for idx in range(await aria_locator.count()):
            try:
                value = await aria_locator.nth(idx).get_attribute("aria-valuenow")
            except PlaywrightError:
                continue
            if not value:
                continue
            try:
                return int(value)
            except ValueError:
                continue
    except PlaywrightError:
        pass
    try:
        complete_locator = row.locator(
            _selector(config, "progress_complete", LS.progress_complete)
        )
        if await complete_locator.count():
            return 100
    except PlaywrightError:
        pass
    try:
        width_locator = row.locator(":scope [style*='width']")
        for idx in range(await width_locator.count()):
            try:
                style = await width_locator.nth(idx).get_attribute("style")
            except PlaywrightError:
                continue
            if not style:
                continue
            match = re.search(r"width\s*:\s*(\d{1,3})%", style)
            if match:
                return int(match.group(1))
    except PlaywrightError:
        pass
    text_hint = None
    try:
        text_hint = await row.inner_text(timeout=500)
    except PlaywrightError:
        return None
    if text_hint:
        match = re.search(r"(\d{1,3})%", text_hint)
        if match:
            return int(match.group(1))
    return None


async def _extract_duration(row: Locator, config: RuntimeConfig) -> tuple[Optional[str], Optional[int]]:
    try:
        duration_locator = row.locator(
            _selector(config, "duration", LS.duration)
        )
        for idx in range(await duration_locator.count()):
            try:
                label = (await duration_locator.nth(idx).inner_text(timeout=750)).strip()
            except PlaywrightError:
                continue
            match = DURATION_PATTERN.search(label)
            if not match:
                continue
            return label, _duration_to_seconds(match)
    except PlaywrightError:
        pass
    try:
        label = await row.inner_text(timeout=500)
    except PlaywrightError:
        return None, None
    if not label:
        return None, None
    match = DURATION_PATTERN.search(label)
    if not match:
        return label.strip(), None
    return label.strip(), _duration_to_seconds(match)


def _duration_to_seconds(match: re.Match[str]) -> int:
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m") or 0)
    seconds = int(match.group("s") or 0)
    return hours * 3600 + minutes * 60 + seconds



async def _quiz_completion_hint(row: Locator, config: RuntimeConfig) -> bool:
    try:
        repeat_button = row.locator(":scope button:has-text(\"Ripeti\"), :scope a:has-text(\"Ripeti\"), :scope span:has-text(\"Ripeti\")")
        if await repeat_button.count():
            # Presence of a repeat action is a strong indicator that the quiz was already submitted.
            return True
    except PlaywrightError:
        pass
    try:
        badge = row.locator(":scope span:has-text(\"Completato\"), :scope span:has-text(\"Superato\"), :scope div:has-text(\"Quiz completato\")")
        if await badge.count():
            return True
    except PlaywrightError:
        pass
    try:
        raw_text = (await row.inner_text(timeout=650)).strip().lower()
    except PlaywrightError:
        raw_text = ""
    if not raw_text:
        return False
    if "quiz" in raw_text and any(keyword in raw_text for keyword in ("completato", "superato", "già svolto", "punteggio")):
        return True
    if "ripeti" in raw_text and "quiz" in raw_text:
        return True
    if "punteggio" in raw_text and "100%" in raw_text:
        return True
    return False


async def collect_lessons(page: Page, bounds: ChapterBounds, logger, config: RuntimeConfig) -> list[LessonCandidate]:
    rows = bounds.container.locator(
        _selector(config, "lesson_row", LS.lesson_row)
    )
    results: list[LessonCandidate] = []
    title_matches = 0
    duration_matches = 0
    progress_matches = 0
    count = await rows.count()
    chapter_label = _chapter_log_label(bounds)
    logger.info(
        "Scansione capitolo %s: trovate %s righe candidate (range y %.1f-%.1f)",
        chapter_label,
        count,
        bounds.y_min,
        bounds.y_max,
    )
    for idx in range(count):
        row = rows.nth(idx)
        try:
            bbox = await row.bounding_box()
        except PlaywrightError:
            bbox = None
        # Bounding boxes were previously used to discard lessons that appeared
        # outside the y-range measured when the chapter list was collapsed.
        # Expanding a chapter shifts the layout, making those bounds stale and
        # causing valid lessons to be skipped. Because the lesson locator is
        # already scoped to the current chapter container, we no longer apply
        # coordinate-based filtering; we keep the bounding box only for
        # diagnostic purposes.
        href = ""
        content_type = "unknown"
        try:
            link_locator = row.locator("a[href]").first
            if await link_locator.count():
                href = await link_locator.get_attribute("href") or ""
                if href:
                    content_type = _classify_lesson_href(href)
        except PlaywrightError:
            href = ""
        try:
            title_locator = row.locator(
                _selector(config, "lesson_title", LS.title)
            ).first
            title_raw = (await title_locator.inner_text(timeout=1000)).strip()
        except PlaywrightError:
            title_raw = ""
        if not title_raw:
            try:
                title_raw = (await row.inner_text(timeout=750)).strip()
            except PlaywrightError:
                title_raw = ""
        if title_raw:
            title_matches += 1
        duration_label, duration_seconds = await _extract_duration(row, config)
        if duration_label:
            duration_matches += 1
        progress = await _extract_percentage(row, config)
        try:
            if progress is None:
                completed_icon = row.locator(LS.progress_complete)
                if await completed_icon.count():
                    progress = 100
        except PlaywrightError:
            pass
        if progress is not None:
            progress_matches += 1
        is_quiz = content_type == "quiz" or _is_quiz_title(title_raw)
        completion_hint = await _quiz_completion_hint(row, config) if is_quiz else False
        skip_reason = _title_skip_reason(
            title_raw,
            progress,
            config,
            is_quiz=is_quiz,
            completion_hint=completion_hint,
        )
        if content_type != "video":
            skip_reason = skip_reason or f"contenuto {content_type}"
        if content_type == "assignment":
            skip_reason = skip_reason or "compito valutato: intervento manuale"
        if content_type == "unknown" and href:
            skip_reason = skip_reason or "tipo contenuto non riconosciuto"
        if href:
            logger.debug(
                "Riga lezione '%s': href=%s tipo=%s progress=%s skip=%s",
                title_raw,
                href,
                content_type,
                progress,
                skip_reason,
            )
        candidate = LessonCandidate(
            title=title_raw,
            title_raw=title_raw,
            duration_label=duration_label,
            duration_seconds=duration_seconds,
            progress=progress,
            locator=row,
            bounding_box=bbox,
            is_quiz=is_quiz,
            completion_hint=completion_hint,
            skip_reason=skip_reason,
        )
        results.append(candidate)
    if config.diagnose and count:
        logger.info(
            "Diagnostica selettori capitolo %s: titoli=%s/%s durate=%s progressi=%s",
            chapter_label,
            title_matches,
            count,
            duration_matches,
            progress_matches,
        )
    return results


async def _chapter_is_expanded(bounds: ChapterBounds) -> bool:
    try:
        return bool(
            await bounds.click_target.evaluate(
                "el => {\n"
                "  if (!el) { return false; }\n"
                "  const candidate = el.closest('[aria-expanded]') || el.querySelector('[aria-expanded]');\n"
                "  if (!candidate) { return false; }\n"
                "  return candidate.getAttribute('aria-expanded') === 'true';\n"
                "}\n"
            )
        )
    except PlaywrightError:
        return False


async def _ensure_scroll_into_view(locator: Locator, timeout_ms: int) -> None:
    try:
        await locator.scroll_into_view_if_needed(timeout=timeout_ms)
        return
    except PlaywrightError:
        pass
    try:
        await locator.evaluate(
            "el => el.scrollIntoView({behavior: 'instant', block: 'center', inline: 'nearest'})"
        )
    except PlaywrightError:
        pass


async def _prime_chapter_content(
    page: Page, bounds: ChapterBounds, logger, config: RuntimeConfig
) -> None:
    try:
        label = _chapter_log_label(bounds)
    except Exception:  # pragma: no cover - defensive logging
        label = f"#{bounds.index}"
    logger.debug("Scroll esplorativo capitolo %s", label)
    try:
        await bounds.container.scroll_into_view_if_needed(timeout=750)
    except PlaywrightError:
        pass
    try:
        await bounds.container.evaluate("el => { if (el) el.scrollTop = 0; }")
    except PlaywrightError:
        pass
    lesson_locator = bounds.container.locator(
        _selector(config, "lesson_row", LS.lesson_row)
    )
    last_count = -1
    stable_rounds = 0
    max_attempts = 5
    for attempt in range(max_attempts):
        fraction = (attempt + 1) / max_attempts
        reached_end = False
        try:
            reached_end = await bounds.container.evaluate(
                "(el, fraction) => {\n"
                "  if (!el) { return false; }\n"
                "  const scrollHeight = el.scrollHeight || 0;\n"
                "  const clientHeight = el.clientHeight || 0;\n"
                "  const max = Math.max(scrollHeight - clientHeight, 0);\n"
                "  if (max <= 0) { return false; }\n"
                "  const target = Math.min(max, Math.round(max * fraction));\n"
                "  el.scrollTop = target;\n"
                "  return target >= max - 2;\n"
                "}",
                fraction,
            )
        except PlaywrightError:
            reached_end = False
        if not reached_end:
            try:
                await page.mouse.wheel(0, 600)
            except PlaywrightError:
                pass
        try:
            await page.wait_for_timeout(250)
        except PlaywrightError:
            pass
        try:
            current_count = await lesson_locator.count()
        except PlaywrightError:
            current_count = 0
        if current_count == last_count and current_count != 0:
            stable_rounds += 1
        else:
            stable_rounds = 0
        logger.debug(
            "Scroll capitolo %s tentativo %s/%s: righe=%s stabile=%s",
            label,
            attempt + 1,
            max_attempts,
            current_count,
            stable_rounds,
        )
        last_count = current_count
        if stable_rounds >= 2:
            break
    try:
        await bounds.container.evaluate("el => { if (el) el.scrollTop = 0; }")
    except PlaywrightError:
        pass


async def _refresh_chapter_bounds(
    page: Page, bounds: ChapterBounds, logger, *, padding: float = 300.0
) -> ChapterBounds:
    try:
        label = _chapter_log_label(bounds)
    except Exception:  # pragma: no cover - defensive logging
        label = f"#{bounds.index}"
    try:
        metrics = await bounds.container.evaluate(
            "el => {\n"
            "  if (!el) { return null; }\n"
            "  const rect = el.getBoundingClientRect();\n"
            "  const top = rect.top + window.scrollY;\n"
            "  const height = rect.height;\n"
            "  const scrollHeight = el.scrollHeight || height || 0;\n"
            "  return { top, height, scrollHeight };\n"
            "}"
        )
    except PlaywrightError:
        metrics = None
    new_y_min = bounds.y_min
    new_y_max = bounds.y_max
    if metrics:
        top = metrics.get("top") if isinstance(metrics, dict) else None
        if isinstance(top, (int, float)):
            new_y_min = float(top)
        height = 0.0
        if isinstance(metrics, dict):
            for key in ("scrollHeight", "height"):
                value = metrics.get(key)
                if isinstance(value, (int, float)):
                    height = max(height, float(value))
        if not math.isnan(new_y_min) and height > 0:
            new_y_max = new_y_min + height + padding
    else:
        try:
            bbox = await bounds.container.bounding_box()
        except PlaywrightError:
            bbox = None
        if bbox:
            top = bbox.get("y")
            if isinstance(top, (int, float)):
                new_y_min = float(top)
            height = bbox.get("height")
            if isinstance(height, (int, float)) and not math.isnan(new_y_min):
                new_y_max = new_y_min + float(height) + padding
    bounds.y_min = new_y_min
    if math.isnan(bounds.y_min):
        bounds.y_max = float("inf")
    else:
        if math.isnan(new_y_max) or new_y_max <= bounds.y_min:
            new_y_max = bounds.y_min + 400
        bounds.y_max = new_y_max
    logger.debug(
        "Bounds capitolo %s aggiornati: y_min=%s y_max=%s",
        label,
        bounds.y_min,
        bounds.y_max,
    )
    return bounds


async def _human_like_scroll(
    page: Page, logger, config: RuntimeConfig, *, reason: str
) -> None:
    distance = max(60, int(config.lesson_scroll_distance))
    jitter = max(0, int(config.lesson_scroll_jitter))
    steps = random.randint(1, 3)
    logger.debug("Scroll lezione '%s': passi=%s", reason, steps)
    for step in range(steps):
        offset = distance + random.randint(-jitter, jitter)
        offset = max(40, offset)
        try:
            await page.mouse.wheel(0, offset)
        except PlaywrightError:
            try:
                await page.evaluate(
                    "delta => window.scrollBy({ left: 0, top: delta, behavior: 'smooth' })",
                    offset,
                )
            except PlaywrightError:
                break
        await asyncio.sleep(0.15 + random.random() * 0.25)


async def click_with_retry(
    locator: Locator,
    config: RuntimeConfig,
    logger,
    *,
    description: str,
    page: Optional[Page] = None,
) -> bool:
    timeout_ms = int(config.click_timeout * 1000)
    overlay_detected = False
    for attempt in range(1, config.max_retries + 1):
        try:
            await locator.wait_for(state="attached", timeout=timeout_ms)
        except PlaywrightError:
            pass
        await _ensure_scroll_into_view(locator, timeout_ms)
        try:
            await locator.wait_for(state="visible", timeout=timeout_ms)
        except PlaywrightError:
            pass
        try:
            await locator.click(timeout=config.click_timeout * 1000)
            logger.info("Click %s tentativo %s/%s: OK", description, attempt, config.max_retries)
            return True
        except PlaywrightError as exc:
            delay = config.retry_base_delay * (config.retry_backoff ** (attempt - 1))
            logger.warning(
                "Click %s tentativo %s/%s fallito: %s (retry tra %.1fs)",
                description,
                attempt,
                config.max_retries,
                exc,
                delay,
            )
            if page is not None and "intercepts pointer events" in str(exc).lower():
                try:
                    overlays = await _detect_blocking_overlays(page)
                except PlaywrightError:
                    overlays = []
                if overlays:
                    overlay_detected = True
                    try:
                        closed = await _dismiss_blocking_overlay(
                            page,
                            logger,
                            context=f"click {description}",
                            overlays=overlays,
                        )
                    except PlaywrightError:
                        closed = False
                    if closed:
                        logger.info(
                            "Overlay gestito dopo il fallimento del click %s: nuovo tentativo",
                            description,
                        )
                        await asyncio.sleep(0.2)
                        continue
                else:
                    logger.debug(
                        "Intercettato pointer events senza overlay visibili per %s",
                        description,
                    )
            if page is not None:
                try:
                    await page.wait_for_timeout(150)
                except PlaywrightError:
                    pass
                if attempt < config.max_retries:
                    try:
                        await page.keyboard.press("Home")
                        await page.wait_for_timeout(100)
                    except PlaywrightError:
                        pass
            if attempt < config.max_retries:
                await asyncio.sleep(delay)
    if overlay_detected:
        raise CourseContextBlocked(
            f"Click {description} bloccato da overlay persistente"
        )
    return False


def _parse_duration_label(label: str) -> Optional[int]:
    match = DURATION_PATTERN.search(label)
    if not match:
        return None
    return _duration_to_seconds(match)


async def _read_player_timing(page: Page) -> tuple[Optional[int], Optional[float]]:
    try:
        payload = await page.evaluate(
            "() => {\n"
            "  const video = document.querySelector('video');\n"
            "  if (!video) { return { duration: null, rate: null }; }\n"
            "  const duration = Number.isFinite(video.duration) ? Math.round(video.duration) : null;\n"
            "  const rate = typeof video.playbackRate === 'number' ? video.playbackRate : null;\n"
            "  return { duration, rate };\n"
            "}"
        )
    except PlaywrightError:
        payload = None
    duration = None
    rate = None
    if isinstance(payload, dict):
        raw_duration = payload.get("duration")
        if isinstance(raw_duration, (int, float)):
            duration = int(raw_duration)
        raw_rate = payload.get("rate")
        if isinstance(raw_rate, (int, float)):
            rate = float(raw_rate)
    if duration is not None:
        return duration, rate
    try:
        label = await page.locator("span.duration-display").first.inner_text(timeout=750)
    except PlaywrightError:
        label = ""
    if label:
        parsed = _parse_duration_label(label)
        if parsed is not None:
            return parsed, rate
    return None, rate


async def _read_current_lesson_title(page: Page, config: RuntimeConfig) -> Optional[str]:
    selector = _selector(config, "current_item", LS.current_item)
    try:
        locator = page.locator(selector).first
        if not await locator.count():
            return None
        raw_title = await locator.inner_text(timeout=750)
    except PlaywrightError:
        return None
    title = _normalize_label(raw_title)
    return title or None


async def wait_for_lesson(
    candidate: LessonCandidate,
    config: RuntimeConfig,
    logger,
    stop_event: asyncio.Event,
    page: Page,
    watchdog: Optional[ActivityWatchdog] = None,
) -> bool:
    if candidate.is_quiz:
        return await _solve_quiz(candidate, config, logger, stop_event, page, watchdog)

    base = config.after_play
    active_title = candidate.title

    async def _recalculate_timing(reason: str) -> tuple[float, int]:
        player_duration, playback_rate = await _read_player_timing(page)
        raw_duration = candidate.duration_seconds or player_duration or 0
        effective_rate = playback_rate if playback_rate and playback_rate > 0 else 1.0
        effective_duration = int(round(raw_duration / effective_rate)) if raw_duration else 0
        if effective_duration and effective_rate != 1.0:
            logger.info(
                "Durata player rilevata: %ss con velocità %.2fx (attesa=%ss)",
                raw_duration,
                effective_rate,
                effective_duration,
            )
        residual = max(0, effective_duration - base)
        planned_total = base + residual + config.buffer
        planned_total = min(planned_total, config.max_wait)
        logger.info(
            "Attesa lezione '%s': base=%ss residuo=%ss buffer=%ss (tot=%ss) motivo=%s",
            active_title,
            base,
            residual,
            config.buffer,
            planned_total,
            reason,
        )
        return planned_total, effective_duration

    planned_total, _ = await _recalculate_timing("inizio")
    loop = asyncio.get_running_loop()
    start_time = loop.time()
    absolute_deadline = start_time + config.max_wait
    deadline = min(start_time + planned_total, absolute_deadline)
    if watchdog:
        watchdog.raise_if_expired()
        watchdog.ping(f"attesa {candidate.title}")
    if await dismiss_video_restriction_popup(page, config, logger):
        logger.info(
            "Popup blocco video gestito all'avvio della lezione, attendo il render"
        )
        await asyncio.sleep(config.lesson_render_wait)
    if watchdog:
        watchdog.raise_if_expired()
        watchdog.ping(f"riproduzione {candidate.title}")
    await _sleep_with_stop(stop_event, base)
    if await dismiss_video_restriction_popup(page, config, logger):
        logger.info(
            "Popup blocco video gestito, attendo nuovamente il render della lezione"
        )
        await asyncio.sleep(config.lesson_render_wait)
    if stop_event.is_set():
        logger.info("Attesa interrotta per richiesta di stop")
        return False
    progress = candidate.progress or 0
    progress_observed = candidate.progress is not None
    last_progress_change = loop.time()
    scroll_interval = max(0.0, float(config.lesson_scroll_interval))
    last_scroll = loop.time()
    while not stop_event.is_set():
        if watchdog:
            watchdog.raise_if_expired()
            watchdog.ping(f"monitor {candidate.title}")
        current_title = await _read_current_lesson_title(page, config)
        if current_title and not _titles_equal(current_title, active_title):
            logger.info(
                "Cambio lezione rilevato: '%s' -> '%s', ricalcolo attesa",
                active_title,
                current_title,
            )
            active_title = current_title
            planned_total, _ = await _recalculate_timing("cambio lezione")
            now = loop.time()
            start_time = now
            absolute_deadline = now + config.max_wait
            deadline = min(now + planned_total, absolute_deadline)
            progress = 0
            progress_observed = False
            last_progress_change = now
            continue
        if await _maybe_click_navigation_buttons(page, config, logger):
            logger.info("Navigazione completata tramite pulsanti player")
            return True
        if await _dismiss_blocking_overlay(page, logger, context="attesa lezione"):
            logger.info("Overlay gestito durante l'attesa, riprendo monitoraggio")
            await asyncio.sleep(config.lesson_render_wait)
        now = loop.time()
        if scroll_interval > 0 and now - last_scroll >= scroll_interval:
            try:
                await _human_like_scroll(
                    page,
                    logger,
                    config,
                    reason=f"monitor {candidate.title}",
                )
            except Exception:  # pragma: no cover - best effort
                pass
            last_scroll = loop.time()
        if now >= deadline:
            if not progress_observed:
                break
            if progress >= config.progress_threshold or now >= absolute_deadline:
                break
            remaining_estimate = _estimate_remaining_seconds(
                candidate,
                progress,
                base_wait=base,
                default_total=planned_total - config.buffer,
            )
            extension = max(config.buffer, remaining_estimate + config.buffer)
            deadline = min(absolute_deadline, now + extension)
            if deadline <= now:
                break
            logger.info(
                "Progresso %s%% insufficiente, estensione attesa di %.1fs",
                progress,
                deadline - now,
            )
            continue
        timeout = min(5.0, deadline - now)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=timeout)
            continue
        except asyncio.TimeoutError:
            pass
        current_title = await _read_current_lesson_title(page, config)
        if current_title and not _titles_equal(current_title, active_title):
            logger.info(
                "Cambio lezione rilevato durante il polling: '%s' -> '%s'",
                active_title,
                current_title,
            )
            active_title = current_title
            planned_total, _ = await _recalculate_timing("cambio lezione")
            now = loop.time()
            start_time = now
            absolute_deadline = now + config.max_wait
            deadline = min(now + planned_total, absolute_deadline)
            progress = 0
            progress_observed = False
            last_progress_change = now
            continue
        if await dismiss_video_restriction_popup(page, config, logger):
            logger.info(
                "Popup blocco video gestito durante l'attesa, proseguo dopo il render"
            )
            await asyncio.sleep(config.lesson_render_wait)
            deadline = min(deadline + config.lesson_render_wait, absolute_deadline)
            continue
        if await _dismiss_blocking_overlay(page, logger, context="attesa lezione"):
            logger.info("Overlay gestito durante l'attesa, proseguo dopo il render")
            await asyncio.sleep(config.lesson_render_wait)
            deadline = min(deadline + config.lesson_render_wait, absolute_deadline)
            continue
        if await _maybe_click_navigation_buttons(page, config, logger):
            logger.info("Navigazione completata tramite pulsanti player")
            return True
        current_progress = await _extract_percentage(candidate.locator, config)
        if current_progress is None:
            logger.debug(
                "Progresso non disponibile per '%s', mantengo timer attuale",
                candidate.title,
            )
            progress_observed = False
            continue
        progress_observed = True
        if current_progress >= config.progress_threshold:
            logger.info(
                "Soglia completamento %s%% raggiunta per '%s'",
                current_progress,
                candidate.title,
            )
            progress = current_progress
            break
        if current_progress != progress:
            logger.info(
                "Progresso lezione '%s' aggiornato: %s%%",
                candidate.title,
                current_progress,
            )
            progress = current_progress
            progress_observed = True
            remaining_estimate = _estimate_remaining_seconds(
                candidate,
                progress,
                base_wait=base,
                default_total=planned_total - config.buffer,
            )
            deadline = min(
                absolute_deadline,
                max(deadline, loop.time() + max(config.buffer, remaining_estimate + config.buffer)),
            )
            last_progress_change = loop.time()
            continue
        if config.stall_timeout > 0 and loop.time() - last_progress_change >= config.stall_timeout:
            logger.warning(
                "Nessun avanzamento rilevato in %ss per '%s': interruzione attesa",
                config.stall_timeout,
                candidate.title,
            )
            break
    if stop_event.is_set():
        logger.info("Attesa interrotta per richiesta di stop")
        return False
    if await _maybe_click_navigation_buttons(page, config, logger):
        logger.info("Navigazione completata tramite pulsanti player")
        return True
    return progress >= config.progress_threshold


async def _maybe_click_navigation_buttons(page: Page, config: RuntimeConfig, logger) -> bool:
    candidates = (
        ("mark_complete", LS.mark_complete, "Contrassegna come completato"),
        ("next_item", LS.next_item, "Vai alla voce successiva"),
        ("next_item_secondary", LS.next_item_secondary, "Elemento successivo"),
    )
    timeout_ms = int(config.click_timeout * 1000)
    for key, default, label in candidates:
        selector = _selector(config, key, default)
        try:
            locator = page.locator(selector)
            if not await locator.count():
                continue
            button = locator.first
            try:
                if not await button.is_visible():
                    continue
            except PlaywrightError:
                pass
            await button.click(timeout=timeout_ms)
            logger.info("Click automatico su '%s' (selector=%s)", label, selector)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            except PlaywrightError:
                await page.wait_for_timeout(300)
            return True
        except PlaywrightError:
            continue
    return False




async def _course_view_available(page: Page, config: RuntimeConfig) -> bool:
    try:
        container = page.locator(
            _selector(config, "chapter_container", LS.chapter_container)
        )
        return await container.count() > 0
    except PlaywrightError:
        return False


async def _recover_course_context(
    page: Page, config: RuntimeConfig, logger, *, attempt: int = 1
) -> bool:
    current_url = "<sconosciuto>"
    try:
        current_url = page.url
    except PlaywrightError:
        pass
    if attempt <= 1:
        logger.warning("Schermata del corso non rilevata (URL attuale: %s). Presumo un cambio manuale e provo a ripristinare.", current_url)
    else:
        logger.warning("Ripristino schermata corso tentativo %s (URL attuale: %s)", attempt, current_url)
    target = config.url
    if not target:
        logger.error("URL del corso non configurato: impossibile ripristinare la schermata")
        return False
    try:
        await page.goto(target, wait_until="networkidle", timeout=int(config.navigation_timeout * 1000))
    except PlaywrightTimeoutError:
        logger.warning("Timeout durante il ripristino della pagina corso: proseguo comunque")
    except PlaywrightError as exc:
        logger.error("Errore durante il ripristino della pagina corso: %s", exc)
        return False
    try:
        await page.wait_for_timeout(int(max(config.lesson_render_wait, 0.5) * 1000))
    except PlaywrightError:
        pass
    return await _course_view_available(page, config)


async def _run_course_once(
    page: Page,
    config: RuntimeConfig,
    logger,
    stop_event: asyncio.Event,
    state: LessonState,
    watchdog: Optional[ActivityWatchdog] = None,
) -> bool:
    await ensure_cookies(page, logger)
    chapters: list[ChapterBounds] = []
    recovery_attempt = 0
    while not chapters and recovery_attempt <= 1:
        try:
            chapters = await collect_chapter_bounds(page, logger, config)
        except PlaywrightError:
            chapters = []
        if chapters:
            break
        recovery_attempt += 1
        if watchdog:
            watchdog.ping("ripristino contesto corso")
        if not await _recover_course_context(page, config, logger, attempt=recovery_attempt):
            break
        await ensure_cookies(page, logger)
    if not chapters:
        logger.error("Impossibile individuare i capitoli del corso dopo il ripristino")
        return False
    if recovery_attempt:
        suffix = "i" if recovery_attempt > 1 else "o"
        logger.info("Ripristino schermata corso completato dopo %s tentativ%s", recovery_attempt, suffix)
    logger.info("Rilevati %s capitoli", len(chapters))
    if watchdog:
        watchdog.raise_if_expired()
        watchdog.ping("raccolta capitoli")

    start_index = 0
    blocking_failures = 0
    course_progress = False
    if config.start_chapter is not None:
        matched = _find_start_chapter_index(chapters, config.start_chapter, logger)
        if matched is not None:
            start_index = matched

    resume_chapter_index = state.chapter_index if start_index == 0 else None
    resume_chapter_title = state.chapter_title if start_index == 0 else None
    resume_title = state.lesson_title if start_index == 0 else None
    if resume_chapter_index or resume_chapter_title:
        logger.info(
            "Ripresa attiva: capitolo=%s titolo_capitolo=%s lezione=%s",
            resume_chapter_index or "<sconosciuto>",
            resume_chapter_title or "<nessuno>",
            resume_title or "<nessuna>",
        )

    try:
        for idx, bounds in enumerate(chapters):
            if idx < start_index:
                continue
            chapter_label = _chapter_log_label(bounds)
            if watchdog:
                watchdog.raise_if_expired()
                watchdog.ping(f"capitolo {chapter_label}")
            if stop_event.is_set():
                logger.info("Stop richiesto: uscita prima del capitolo %s", chapter_label)
                return False
            if not config.chapter_in_scope(bounds.index, number=bounds.number):
                continue
            if resume_chapter_title:
                if not _titles_equal(bounds.title, resume_chapter_title):
                    logger.info(
                        "Ripresa: salto capitolo '%s' in attesa di '%s'",
                        bounds.title,
                        resume_chapter_title,
                    )
                    continue
                resume_chapter_title = None
            elif resume_chapter_index and bounds.index < resume_chapter_index:
                logger.info(
                    "Ripresa: salto capitolo %s già completato (target %s)",
                    chapter_label,
                    resume_chapter_index,
                )
                continue
            logger.info("Apri capitolo %s", chapter_label)
            click_desc = f"capitolo {bounds.number or bounds.index}"
            already_open = await _chapter_is_expanded(bounds)
            if not already_open:
                try:
                    await bounds.click_target.evaluate(
                        "el => {\n"
                        "  if (!el) { return; }\n"
                        "  el.scrollIntoView({ behavior: 'smooth', block: 'center' });\n"
                        "  window.scrollBy(0, -120);\n"
                        "}\n"
                    )
                    await asyncio.sleep(0.7)
                except PlaywrightError:
                    if page is not None:
                        try:
                            await page.evaluate(
                                "el => {\n"
                                "  if (!el) { return; }\n"
                                "  el.scrollIntoView({ behavior: 'instant', block: 'center' });\n"
                                "  window.scrollBy(0, -120);\n"
                                "}\n",
                                await bounds.click_target.element_handle(),
                            )
                            await asyncio.sleep(0.3)
                        except PlaywrightError:
                            pass
                try:
                    click_ok = await click_with_retry(
                        bounds.click_target,
                        config,
                        logger,
                        description=click_desc,
                        page=page,
                    )
                except CourseContextBlocked:
                    blocking_failures += 1
                    raise
                if not click_ok:
                    blocking_failures += 1
                    fallback_title = bounds.title.split("-", 1)[-1].strip() or bounds.title.strip()
                    if fallback_title and page is not None:
                        logger.info(
                            "Fallback click capitolo %s usando testo '%s'",
                            chapter_label,
                            fallback_title,
                        )
                        text_locator = page.locator(
                            f"text=/{re.escape(fallback_title)}/i"
                        ).first
                        if await text_locator.count():
                            try:
                                fallback_ok = await click_with_retry(
                                    text_locator,
                                    config,
                                    logger,
                                    description=f"{click_desc} fallback",
                                    page=page,
                                )
                            except CourseContextBlocked:
                                blocking_failures += 1
                                raise
                            if fallback_ok:
                                logger.info(
                                    "Click fallback capitolo %s riuscito",
                                    chapter_label,
                                )
                            else:
                                blocking_failures += 1
                                logger.error(
                                    "Impossibile aprire capitolo %s anche con fallback testo",
                                    chapter_label,
                                )
                                continue
                        else:
                            logger.error(
                                "Fallback testo per capitolo %s non trovato", chapter_label
                            )
                            continue
                    else:
                        logger.error(
                            "Impossibile aprire capitolo %s: click fallito e nessun fallback",
                            chapter_label,
                        )
                        continue
            else:
                logger.info("Capitolo %s già aperto, evito il click", chapter_label)
            await asyncio.sleep(config.lesson_render_wait)
            await _prime_chapter_content(page, bounds, logger, config)
            bounds = await _refresh_chapter_bounds(page, bounds, logger)
            try:
                await page.wait_for_timeout(250)
            except PlaywrightError:
                pass
            attempts: dict[str, int] = {}
            while True:
                if watchdog:
                    watchdog.raise_if_expired()
                    watchdog.ping(f"scan {chapter_label}")
                if stop_event.is_set():
                    logger.info("Stop richiesto: uscita durante la scansione delle lezioni")
                    return False
                lessons = await collect_lessons(page, bounds, logger, config)
                if watchdog:
                    watchdog.ping(f"lezioni {chapter_label}")
                valid = [lesson for lesson in lessons if lesson.playable]
                skipped = [lesson for lesson in lessons if not lesson.playable]
                logged_skips: set[str] = set()
                if lessons:
                    logger.info(
                        "Capitolo %s -> lezioni valide: %s, escluse: %s",
                        chapter_label,
                        len(valid),
                        len(skipped),
                    )
                    for lesson in skipped:
                        if lesson.title not in logged_skips:
                            logger.info(
                                "Skip lezione '%s': durata=%s(%ss) progress=%s%% motivo=%s",
                                lesson.title,
                                lesson.duration_label,
                                lesson.duration_seconds,
                                lesson.progress,
                                lesson.skip_reason,
                            )
                            logged_skips.add(lesson.title)
                        if (
                            resume_chapter_index == bounds.index
                            and resume_title
                            and lesson.title == resume_title
                        ):
                            logger.info(
                                "Ripresa: la lezione registrata '%s' è stata rilevata tra gli skip (motivo: %s)",
                                lesson.title,
                                lesson.skip_reason,
                            )
                            resume_title = None
                            resume_chapter_index = None

                if config.diagnose:
                    if not lessons:
                        logger.warning(
                            "Diagnostica: nessuna lezione trovata nel capitolo %s",
                            chapter_label,
                        )
                    else:
                        for lesson in lessons[:5]:
                            logger.info(
                                "Diagnostica riga '%s' bbox=%s progress=%s durata=%s(%ss) decision=%s",
                                lesson.title,
                                lesson.bounding_box,
                                lesson.progress,
                                lesson.duration_label,
                                lesson.duration_seconds,
                                "PLAY" if lesson.playable else f"SKIP ({lesson.skip_reason})",
                            )
                    logger.info(
                        "Diagnostica capitolo %s: trovate %s righe, %s valide, %s escluse",
                        chapter_label,
                        len(lessons),
                        len(valid),
                        len(skipped),
                    )
                    break

                if not valid:
                    logger.info(
                        "Nessuna lezione da riprodurre nel capitolo %s", chapter_label
                    )
                    break

                progress_made = False
                rescan_requested = False

                for lesson in valid:
                    if watchdog:
                        watchdog.raise_if_expired()
                        watchdog.ping(f"lezione {lesson.title}")
                    exhausted_attempts = attempts.get(lesson.title, 0)
                    if exhausted_attempts >= config.max_lesson_attempts:
                        logger.warning(
                            "Lezione '%s' già tentata %s volte: passo al prossimo elemento",
                            lesson.title,
                            exhausted_attempts,
                        )
                        continue
                    if resume_chapter_title:
                        logger.info(
                            "Ripresa: salto lezione '%s' in attesa del capitolo memorizzato",
                            lesson.title,
                        )
                        continue
                    if resume_chapter_index == bounds.index and resume_title:
                        if lesson.title == resume_title:
                            logger.info(
                                "Ripresa: saltata lezione '%s' già completata", lesson.title
                            )
                            resume_title = None
                            resume_chapter_index = None
                            continue
                        else:
                            logger.info(
                                "Ripresa: salto lezione precedente '%s' in capitolo %s",
                                lesson.title,
                                chapter_label,
                            )
                            continue
                    if stop_event.is_set():
                        logger.info(
                            "Stop richiesto: uscita durante lezione '%s'",
                            lesson.title,
                        )
                        return False
                    logger.info(
                        "Riproduzione lezione '%s' durata=%s(%ss) progress=%s%%",
                        lesson.title,
                        lesson.duration_label,
                        lesson.duration_seconds,
                        lesson.progress,
                    )
                    try:
                        lesson_click = await click_with_retry(
                            lesson.locator,
                            config,
                            logger,
                            description="lezione",
                            page=page,
                        )
                    except CourseContextBlocked:
                        blocking_failures += 1
                        raise
                    if not lesson_click:
                        blocking_failures += 1
                        logger.error("Impossibile click lezione '%s'", lesson.title)
                        continue
                    try:
                        await _human_like_scroll(
                            page,
                            logger,
                            config,
                            reason=f"inizio {lesson.title}",
                        )
                    except Exception:
                        pass
                    state.chapter_index = bounds.index
                    state.chapter_title = bounds.title
                    state.lesson_title = lesson.title
                    state.save(config.state_file)
                    completed = await wait_for_lesson(
                        lesson, config, logger, stop_event, page, watchdog=watchdog
                    )
                    if completed:
                        logger.info("Lezione completata '%s'", lesson.title)
                        attempts.pop(lesson.title, None)
                        progress_made = True
                        course_progress = True
                    else:
                        count = attempts.get(lesson.title, 0) + 1
                        attempts[lesson.title] = count
                        if count < config.max_lesson_attempts:
                            logger.warning(
                                "Lezione '%s' non avanzata, nuova scansione capitolo (tentativo %s/%s)",
                                lesson.title,
                                count,
                                config.max_lesson_attempts,
                            )
                            rescan_requested = True
                            progress_made = True
                            course_progress = True
                            break
                        logger.error(
                            "Lezione '%s' fallita dopo %s tentativi: passo oltre",
                            lesson.title,
                            count,
                        )
                        progress_made = True
                        course_progress = True

                if stop_event.is_set():
                    return False
                if rescan_requested:
                    continue
                if not progress_made:
                    break
            if resume_chapter_index == bounds.index and resume_title:
                logger.warning(
                    "Ripresa: la lezione '%s' non è stata trovata nel capitolo %s, proseguo comunque",
                    resume_title,
                    chapter_label,
                )
                resume_title = None
                resume_chapter_index = None
    finally:
        _reset_state(state, config)
    if stop_event.is_set():
        return False
    if blocking_failures and not course_progress:
        raise CourseContextBlocked(
            "Nessuna lezione riprodotta a causa di errori di click persistenti"
        )
    return True


async def _solve_quiz(
    candidate: LessonCandidate,
    config: RuntimeConfig,
    logger,
    stop_event: asyncio.Event,
    page: Page,
    watchdog: Optional[ActivityWatchdog] = None,
) -> bool:
    logger.info("Avvio risoluzione quiz '%s'", candidate.title)
    solver = QuizSolver(page, logger, config, stop_event, watchdog=watchdog)
    outcome = await solver.solve()
    if outcome.success:
        logger.info(
            "Quiz '%s' completato: %s tentativi, corrette %s/%s",
            candidate.title,
            outcome.attempts,
            outcome.correct_answers,
            outcome.total_questions,
        )
        return True
    logger.error(
        "Quiz '%s' non superato dopo %s tentativi (%s/%s corrette)",
        candidate.title,
        outcome.attempts,
        outcome.correct_answers,
        outcome.total_questions,
    )
    return False


async def _verify_course_completion(
    page: Page,
    config: RuntimeConfig,
    logger,
    stop_event: asyncio.Event,
    watchdog: Optional[ActivityWatchdog] = None,
) -> VerificationResult:
    chapters = await collect_chapter_bounds(page, logger, config)
    if watchdog:
        watchdog.raise_if_expired()
        watchdog.ping("verifica capitoli")
    incomplete: list[IncompleteLesson] = []
    total_lessons = 0
    completed = 0
    open_failures = 0
    for bounds in chapters:
        chapter_label = _chapter_log_label(bounds)
        if watchdog:
            watchdog.raise_if_expired()
            watchdog.ping(f"verifica {chapter_label}")
        if stop_event.is_set():
            logger.info(
                "Verifica finale interrotta prima del capitolo %s per richiesta di stop",
                chapter_label,
            )
            break
        logger.info("Verifica finale: apertura capitolo %s", chapter_label)
        click_desc = f"verifica capitolo {bounds.number or bounds.index}"
        try:
            await bounds.click_target.evaluate(
                "el => {\n"
                "  if (!el) { return; }\n"
                "  el.scrollIntoView({ behavior: 'smooth', block: 'center' });\n"
                "  window.scrollBy(0, -120);\n"
                "}\n"
            )
            await asyncio.sleep(0.5)
        except PlaywrightError:
            pass
        try:
            click_ok = await click_with_retry(
                bounds.click_target,
                config,
                logger,
                description=click_desc,
                page=page,
            )
        except CourseContextBlocked:
            open_failures += 1
            raise
        if not click_ok:
            open_failures += 1
            logger.warning(
                "Verifica finale: impossibile aprire il capitolo %s",
                chapter_label,
            )
            continue
        await asyncio.sleep(config.lesson_render_wait)
        await _prime_chapter_content(page, bounds, logger, config)
        bounds = await _refresh_chapter_bounds(page, bounds, logger)
        lessons = await collect_lessons(page, bounds, logger, config)
        if watchdog:
            watchdog.ping(f"verifica lezioni {chapter_label}")
        for lesson in lessons:
            lowered = lesson.title.lower()
            if any(keyword in lowered for keyword in LS.title_exclusions):
                continue
            if lesson.skip_reason and not lesson.skip_reason.startswith("progress"):
                continue
            progress = lesson.progress if lesson.progress is not None else 0
            total_lessons += 1
            if progress >= config.progress_threshold:
                completed += 1
            else:
                logger.warning(
                    "Verifica finale: capitolo %s lezione '%s' incompleta (%s%%)",
                    chapter_label,
                    lesson.title,
                    progress,
                )
                incomplete.append(
                    IncompleteLesson(
                        chapter_index=bounds.index,
                        chapter_title=bounds.title,
                        lesson_title=lesson.title,
                        progress=progress,
                    )
                )
    return VerificationResult(
        total_chapters=len(chapters),
        total_lessons=total_lessons,
        completed_lessons=completed,
        incomplete_lessons=incomplete,
        open_failures=open_failures,
    )


async def run_course(page: Page, config: RuntimeConfig, logger, stop_event: asyncio.Event, state: LessonState) -> None:
    effective_config = config
    watchdog = ActivityWatchdog(
        config.watchdog_timeout,
        grace=config.watchdog_grace_attempts,
        logger=logger,
    )
    watchdog.start(stop_event)
    recovery_step = 0
    try:
        while not stop_event.is_set():
            try:
                watchdog.raise_if_expired()
                watchdog.ping("passata principale")
                logger.info(
                    "Avvio passata corso con start_chapter=%s",
                    effective_config.start_chapter,
                )
                completed = await _run_course_once(
                    page, effective_config, logger, stop_event, state, watchdog=watchdog
                )
                if not completed:
                    return
                if stop_event.is_set():
                    return
                watchdog.ping("verifica finale")
                logger.info("Passata principale completata, avvio verifica finale")
                verification = await _verify_course_completion(
                    page, effective_config, logger, stop_event, watchdog=watchdog
                )
                if stop_event.is_set():
                    return
                watchdog.raise_if_expired()
                missing = verification.incomplete_lessons
                logger.info(
                    "Lezioni totali trovate: %s | Completate: %s | Mancanti: %s",
                    verification.total_lessons,
                    verification.completed_lessons,
                    verification.total_lessons - verification.completed_lessons,
                )
                if verification.open_failures:
                    raise CourseContextBlocked(
                        "Verifica finale bloccata: capitoli non cliccabili"
                    )
                if (
                    verification.total_chapters > 0
                    and verification.total_lessons == 0
                    and verification.completed_lessons == 0
                ):
                    raise CourseContextBlocked(
                        "Verifica finale senza lezioni rilevate: probabile desincronizzazione"
                    )
                if not missing:
                    logger.info(
                        "Verifica completata: tutte le lezioni sono state svolte (%s capitoli, %s lezioni totali).",
                        verification.total_chapters,
                        verification.total_lessons,
                    )
                    return
                lowest = verification.lowest_incomplete
                if lowest is None:
                    return
                logger.warning(
                    "Verifica completata: lezioni mancanti rilevate (%s capitoli incompleti, %s lezioni da completare). Riavvio dal capitolo più basso con lezione mancante.",
                    len({item.chapter_index for item in missing}),
                    verification.missing_count,
                )
                logger.info(
                    "Riavvio dal capitolo %s ('%s') per riprendere dalla lezione '%s' (%s%%)",
                    lowest.chapter_index,
                    lowest.chapter_title,
                    lowest.lesson_title,
                    lowest.progress,
                )
                effective_config = effective_config.with_overrides(
                    start_chapter=lowest.chapter_index
                )
                recovery_step = 0
            except CourseContextBlocked as exc:
                if stop_event.is_set():
                    return
                recovered, next_step = await _apply_course_recovery(
                    page,
                    effective_config,
                    logger,
                    reason=str(exc),
                    start_step=recovery_step,
                    stop_event=stop_event,
                    watchdog=watchdog,
                )
                recovery_step = next_step
                if recovered:
                    continue
                raise
        logger.info("Stop richiesto durante il loop principale del corso")
    finally:
        await watchdog.stop()
