"""Lesson discovery and playback logic."""
from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from playwright.async_api import Error as PlaywrightError, Locator, Page

from .config import DURATION_PATTERN, RuntimeConfig
from .state import LessonState

TITLE_EXCLUSIONS = ("test di fine lezione", "dispensa")
LESSON_ROW_SELECTOR = "div.border-t.hover\\:bg-platform-hover-light, div.border-t.hover\\:bg-platform-hover-light.bg-platform-hover-light"
TITLE_SELECTOR = ":scope .text-base .mb-2, :scope div.mb-2, :scope span.font-semibold, :scope div.font-semibold"
DURATION_SELECTOR = ":scope .text-sm.text-platform-gray, :scope span.text-sm, :scope span.text-xs"
PERCENTAGE_SELECTOR = ":scope .w-1\\/12.text-xs.md\\:text-xs, :scope span.text-xs, :scope span.text-sm"
PROGRESS_COMPLETE_SELECTOR = ":scope .bg-platform-green[style*='width: 100%'], :scope .bg-platform-primary[style*='width: 100%']"
CHAPTER_HEADER_SELECTOR = "div.bg-white.text-base.border > div.cursor-pointer, div.bg-white.text-base.border div.cursor-pointer, div.flex.items-center.font-medium"


def _selector(config: RuntimeConfig, key: str, default: str) -> str:
    return config.selector_overrides.get(key, default)


@dataclass(slots=True)
class ChapterBounds:
    index: int  # 1-based for logging
    title: str
    locator: Locator
    y_min: float
    y_max: float


@dataclass(slots=True)
class LessonCandidate:
    title: str
    title_raw: str
    duration_label: Optional[str]
    duration_seconds: Optional[int]
    progress: Optional[int]
    locator: Locator
    bounding_box: Optional[dict[str, float]]
    skip_reason: Optional[str]

    @property
    def playable(self) -> bool:
        return self.skip_reason is None


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


async def collect_chapter_bounds(page: Page, logger, config: RuntimeConfig) -> list[ChapterBounds]:
    headers = page.locator(_selector(config, "chapter_header", CHAPTER_HEADER_SELECTOR))
    count = await headers.count()
    results: list[ChapterBounds] = []

    for idx in range(count):
        locator = headers.nth(idx)
        try:
            title = (await locator.inner_text()).strip()
        except PlaywrightError:
            title = f"Capitolo {idx + 1}"
        try:
            bbox = await locator.bounding_box()
        except PlaywrightError:
            bbox = None
        y_min = bbox["y"] if bbox else float("nan")
        y_max = float("inf")
        results.append(
            ChapterBounds(
                index=idx + 1,
                title=title,
                locator=locator,
                y_min=y_min,
                y_max=y_max,
            )
        )

    for current, nxt in zip(results, results[1:]):
        current.y_max = nxt.y_min if not math.isnan(nxt.y_min) else float("inf")

    return results


def _title_skip_reason(title: str, progress: Optional[int], config: RuntimeConfig) -> Optional[str]:
    lowered = title.lower()
    for keyword in TITLE_EXCLUSIONS:
        if keyword in lowered:
            return f"titolo contiene '{keyword}'"
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
        cell_locator = row.locator(_selector(config, "percentage", PERCENTAGE_SELECTOR))
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
        complete_locator = row.locator(
            _selector(config, "progress_complete", PROGRESS_COMPLETE_SELECTOR)
        )
        if await complete_locator.count():
            return 100
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
        duration_locator = row.locator(_selector(config, "duration", DURATION_SELECTOR))
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


async def collect_lessons(page: Page, bounds: ChapterBounds, logger, config: RuntimeConfig) -> list[LessonCandidate]:
    rows = page.locator(_selector(config, "lesson_row", LESSON_ROW_SELECTOR))
    results: list[LessonCandidate] = []
    count = await rows.count()
    logger.info(
        "Scansione capitolo %s: trovate %s righe candidate (range y %.1f-%.1f)",
        bounds.index,
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
        if bbox:
            y = bbox.get("y", float("nan"))
            if not math.isnan(bounds.y_min) and y < bounds.y_min:
                continue
            if y >= bounds.y_max:
                continue
        try:
            title_locator = row.locator(_selector(config, "lesson_title", TITLE_SELECTOR)).first
            title_raw = (await title_locator.inner_text(timeout=1000)).strip()
        except PlaywrightError:
            title_raw = ""
        if not title_raw:
            try:
                title_raw = (await row.inner_text(timeout=750)).strip()
            except PlaywrightError:
                title_raw = ""
        duration_label, duration_seconds = await _extract_duration(row, config)
        progress = await _extract_percentage(row, config)
        skip_reason = _title_skip_reason(title_raw, progress, config)
        candidate = LessonCandidate(
            title=title_raw,
            title_raw=title_raw,
            duration_label=duration_label,
            duration_seconds=duration_seconds,
            progress=progress,
            locator=row,
            bounding_box=bbox,
            skip_reason=skip_reason,
        )
        results.append(candidate)
    return results


async def click_with_retry(locator: Locator, config: RuntimeConfig, logger, *, description: str) -> bool:
    for attempt in range(1, config.max_retries + 1):
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
            if attempt < config.max_retries:
                await asyncio.sleep(delay)
    return False


async def wait_for_lesson(
    candidate: LessonCandidate,
    config: RuntimeConfig,
    logger,
    stop_event: asyncio.Event,
) -> None:
    base = config.after_play
    residual = max(0, (candidate.duration_seconds or 0) - base)
    total = base + residual + config.buffer
    total = min(total, config.max_wait)
    logger.info(
        "Attesa lezione '%s': base=%ss residuo=%ss buffer=%ss (tot=%ss)",
        candidate.title,
        base,
        residual,
        config.buffer,
        total,
    )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + total
    while not stop_event.is_set():
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=min(5.0, remaining))
        except asyncio.TimeoutError:
            continue
    if stop_event.is_set():
        logger.info("Attesa interrotta per richiesta di stop")


async def run_course(page: Page, config: RuntimeConfig, logger, stop_event: asyncio.Event, state: LessonState) -> None:
    await ensure_cookies(page, logger)
    chapters = await collect_chapter_bounds(page, logger, config)
    logger.info("Rilevati %s capitoli", len(chapters))

    resume_chapter = state.chapter_index
    resume_title = state.lesson_title
    if resume_chapter:
        logger.info(
            "Ripresa attiva: capitolo=%s titolo=%s",
            resume_chapter,
            resume_title or "<nessuno>",
        )

    for bounds in chapters:
        if stop_event.is_set():
            logger.info("Stop richiesto: uscita prima del capitolo %s", bounds.index)
            return
        if not config.chapter_in_scope(bounds.index):
            continue
        if resume_chapter and bounds.index < resume_chapter:
            logger.info(
                "Ripresa: salto capitolo %s già completato (target %s)",
                bounds.index,
                resume_chapter,
            )
            continue
        logger.info("Apri capitolo %s: %s", bounds.index, bounds.title)
        if not await click_with_retry(bounds.locator, config, logger, description=f"capitolo {bounds.index}"):
            logger.error("Impossibile aprire capitolo %s", bounds.index)
            continue
        logger.info(
            "Attesa %ss per render capitolo %s", config.lesson_render_wait, bounds.index
        )
        await asyncio.sleep(config.lesson_render_wait)

        lessons = await collect_lessons(page, bounds, logger, config)
        valid = [lesson for lesson in lessons if lesson.playable]
        skipped = [lesson for lesson in lessons if not lesson.playable]
        logger.info(
            "Capitolo %s -> lezioni valide: %s, escluse: %s",
            bounds.index,
            len(valid),
            len(skipped),
        )
        for lesson in skipped:
            logger.info(
                "Skip lezione '%s': durata=%s(%ss) progress=%s%% motivo=%s",  # noqa: E501
                lesson.title,
                lesson.duration_label,
                lesson.duration_seconds,
                lesson.progress,
                lesson.skip_reason,
            )
            if resume_chapter == bounds.index and resume_title and lesson.title == resume_title:
                logger.info(
                    "Ripresa: la lezione registrata '%s' è stata rilevata tra gli skip (motivo: %s)",
                    lesson.title,
                    lesson.skip_reason,
                )
                resume_title = None
                resume_chapter = None

        if config.diagnose:
            if not lessons:
                logger.warning("Diagnostica: nessuna lezione trovata nel capitolo %s", bounds.index)
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
                bounds.index,
                len(lessons),
                len(valid),
                len(skipped),
            )
            continue

        for lesson in valid:
            if resume_chapter == bounds.index and resume_title:
                if lesson.title == resume_title:
                    logger.info(
                        "Ripresa: saltata lezione '%s' già completata", lesson.title
                    )
                    resume_title = None
                    resume_chapter = None
                    continue
                else:
                    logger.info(
                        "Ripresa: salto lezione precedente '%s' in capitolo %s",
                        lesson.title,
                        bounds.index,
                    )
                    continue
            if stop_event.is_set():
                logger.info("Stop richiesto: uscita durante lezione '%s'", lesson.title)
                return
            logger.info(
                "Riproduzione lezione '%s' durata=%s(%ss) progress=%s%%",
                lesson.title,
                lesson.duration_label,
                lesson.duration_seconds,
                lesson.progress,
            )
            if not await click_with_retry(lesson.locator, config, logger, description="lezione"):
                logger.error("Impossibile click lezione '%s'", lesson.title)
                continue
            state.chapter_index = bounds.index
            state.lesson_title = lesson.title
            state.save(config.state_file)
            await wait_for_lesson(lesson, config, logger, stop_event)
            logger.info("Lezione completata '%s'", lesson.title)
        if resume_chapter == bounds.index and resume_title:
            logger.warning(
                "Ripresa: la lezione '%s' non è stata trovata nel capitolo %s, proseguo comunque",
                resume_title,
                bounds.index,
            )
            resume_title = None
            resume_chapter = None
    logger.info("Corso completato")
