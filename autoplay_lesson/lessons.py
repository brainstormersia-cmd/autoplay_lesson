"""Lesson discovery and playback logic."""
from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from playwright.async_api import (
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from .config import DURATION_PATTERN, RuntimeConfig
from .state import LessonState

TITLE_EXCLUSIONS = ("test di fine lezione", "dispensa", "obiettivi")
LESSON_ROW_SELECTOR = ":scope div.border-t.hover\\:bg-platform-hover-light"
TITLE_SELECTOR = ":scope div.mb-2, :scope span.font-semibold, :scope .text-base .mb-2, :scope div.font-semibold, :scope h3, :scope h4"
DURATION_SELECTOR = ":scope div.text-sm.text-platform-gray, :scope span.text-sm, :scope span.text-xs"
PERCENTAGE_SELECTOR = (
    ":scope div.w-1\\/12.text-xs, :scope div.w-1\\/12.md\\:text-xs, :scope span.text-xs, :scope span.text-sm"
)
PROGRESS_COMPLETE_SELECTOR = ":scope .bg-platform-green[style*='width: 100%'], :scope .bg-platform-primary[style*='width: 100%']"
CHAPTER_CONTAINER_SELECTOR = "div.bg-white.text-base.border.font-sans.font-semibold"
CHAPTER_HEADER_SELECTOR = ":scope div.cursor-pointer, :scope div.flex.items-center.font-medium, :scope button"
VIDEO_BLOCK_HEADER_TEXT = "Riproduzione del video non consentita"
VIDEO_BLOCK_HEADER_SELECTOR = "h3.text-2xl.font-medium.mt-4.whitespace-pre-line"
VIDEO_BLOCK_CONFIRM_SELECTOR = "button.bg-platform-primary.text-white"


def _selector(config: RuntimeConfig, key: str, default: str) -> str:
    return config.selector_overrides.get(key, default)


def _normalize_label(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _titles_equal(first: str, second: str) -> bool:
    return _normalize_label(first).lower() == _normalize_label(second).lower()


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


async def dismiss_video_restriction_popup(page: Page, config: RuntimeConfig, logger) -> bool:
    """Automatically close the video restriction popup if it appears."""

    try:
        header = page.locator(
            f"{VIDEO_BLOCK_HEADER_SELECTOR}:has-text('{VIDEO_BLOCK_HEADER_TEXT}')"
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
        f"{VIDEO_BLOCK_CONFIRM_SELECTOR}:has-text('OK')"
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


async def collect_chapter_bounds(page: Page, logger, config: RuntimeConfig) -> list[ChapterBounds]:
    containers = page.locator(
        _selector(config, "chapter_container", CHAPTER_CONTAINER_SELECTOR)
    )
    count = await containers.count()
    results: list[ChapterBounds] = []

    for idx in range(count):
        container = containers.nth(idx)
        header_locator = container.locator(
            _selector(config, "chapter_header", CHAPTER_HEADER_SELECTOR)
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
            _selector(config, "progress_complete", PROGRESS_COMPLETE_SELECTOR)
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
    rows = bounds.container.locator(
        _selector(config, "lesson_row", LESSON_ROW_SELECTOR)
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
        if title_raw:
            title_matches += 1
        duration_label, duration_seconds = await _extract_duration(row, config)
        if duration_label:
            duration_matches += 1
        progress = await _extract_percentage(row, config)
        if progress is not None:
            progress_matches += 1
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
    page: Page, bounds: ChapterBounds, logger
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
    steps = [600, 600, 600, -600, -600]
    for delta in steps:
        container_scrolled = False
        try:
            container_scrolled = await bounds.container.evaluate(
                "(el, amount) => {\n"
                "  if (!el) { return false; }\n"
                "  const max = (el.scrollHeight || 0) - (el.clientHeight || 0);\n"
                "  if (max <= 0) { return false; }\n"
                "  const next = Math.min(Math.max(el.scrollTop + amount, 0), max);\n"
                "  if (Math.abs(next - el.scrollTop) < 1) {\n"
                "    el.scrollTop = next;\n"
                "    return false;\n"
                "  }\n"
                "  el.scrollTop = next;\n"
                "  return true;\n"
                "}",
                delta,
            )
        except PlaywrightError:
            container_scrolled = False
        if not container_scrolled:
            try:
                await page.mouse.wheel(0, delta)
            except PlaywrightError:
                break
        try:
            await page.wait_for_timeout(200)
        except PlaywrightError:
            break


async def click_with_retry(
    locator: Locator,
    config: RuntimeConfig,
    logger,
    *,
    description: str,
    page: Optional[Page] = None,
) -> bool:
    timeout_ms = int(config.click_timeout * 1000)
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
    return False


async def wait_for_lesson(
    candidate: LessonCandidate,
    config: RuntimeConfig,
    logger,
    stop_event: asyncio.Event,
    page: Page,
) -> bool:
    base = config.after_play
    residual = max(0, (candidate.duration_seconds or 0) - base)
    planned_total = base + residual + config.buffer
    planned_total = min(planned_total, config.max_wait)
    logger.info(
        "Attesa lezione '%s': base=%ss residuo=%ss buffer=%ss (tot=%ss)",
        candidate.title,
        base,
        residual,
        config.buffer,
        planned_total,
    )
    loop = asyncio.get_running_loop()
    start_time = loop.time()
    absolute_deadline = start_time + config.max_wait
    deadline = min(start_time + planned_total, absolute_deadline)
    if await dismiss_video_restriction_popup(page, config, logger):
        logger.info(
            "Popup blocco video gestito all'avvio della lezione, attendo il render"
        )
        await asyncio.sleep(config.lesson_render_wait)
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
    last_progress_change = loop.time()
    while not stop_event.is_set():
        now = loop.time()
        if now >= deadline:
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
        if await dismiss_video_restriction_popup(page, config, logger):
            logger.info(
                "Popup blocco video gestito durante l'attesa, proseguo dopo il render"
            )
            await asyncio.sleep(config.lesson_render_wait)
            deadline = min(deadline + config.lesson_render_wait, absolute_deadline)
            continue
        current_progress = await _extract_percentage(candidate.locator, config)
        if current_progress is None:
            logger.debug(
                "Progresso non disponibile per '%s', mantengo timer attuale",
                candidate.title,
            )
            continue
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
    return progress >= config.progress_threshold


async def run_course(page: Page, config: RuntimeConfig, logger, stop_event: asyncio.Event, state: LessonState) -> None:
    await ensure_cookies(page, logger)
    chapters = await collect_chapter_bounds(page, logger, config)
    logger.info("Rilevati %s capitoli", len(chapters))

    start_index = 0
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
            if stop_event.is_set():
                logger.info("Stop richiesto: uscita prima del capitolo %s", chapter_label)
                return
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
            if not await click_with_retry(
                bounds.click_target,
                config,
                logger,
                description=click_desc,
                page=page,
            ):
                logger.error("Impossibile aprire capitolo %s", chapter_label)
                continue
            logger.info(
                "Attesa %ss per render capitolo %s", config.lesson_render_wait, chapter_label
            )
            await asyncio.sleep(config.lesson_render_wait)
            await _prime_chapter_content(page, bounds, logger)

            attempts: dict[str, int] = {}
            logged_skips: set[str] = set()
            while True:
                lessons = await collect_lessons(page, bounds, logger, config)
                valid = [lesson for lesson in lessons if lesson.playable]
                skipped = [lesson for lesson in lessons if not lesson.playable]
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
                        return
                    logger.info(
                        "Riproduzione lezione '%s' durata=%s(%ss) progress=%s%%",
                        lesson.title,
                        lesson.duration_label,
                        lesson.duration_seconds,
                        lesson.progress,
                    )
                    if not await click_with_retry(
                        lesson.locator,
                        config,
                        logger,
                        description="lezione",
                        page=page,
                    ):
                        logger.error("Impossibile click lezione '%s'", lesson.title)
                        continue
                    state.chapter_index = bounds.index
                    state.chapter_title = bounds.title
                    state.lesson_title = lesson.title
                    state.save(config.state_file)
                    completed = await wait_for_lesson(
                        lesson, config, logger, stop_event, page
                    )
                    if completed:
                        logger.info("Lezione completata '%s'", lesson.title)
                        attempts.pop(lesson.title, None)
                        progress_made = True
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
                            break
                        logger.error(
                            "Lezione '%s' fallita dopo %s tentativi: passo oltre",
                            lesson.title,
                            count,
                        )
                        progress_made = True

                if stop_event.is_set():
                    return
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
        state.chapter_index = None
        state.chapter_title = None
        state.lesson_title = None
        state.save(config.state_file)
    logger.info("Corso completato")
