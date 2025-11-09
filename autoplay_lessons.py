"""Automated course player using Playwright."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from playwright.async_api import (
    Browser,
    Error as PlaywrightError,
    Frame,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)


# ========================= CONFIG DEFAULTS ========================= #
DEFAULT_CONFIG: Dict[str, Any] = {
    "url": "https://METTI-QUI-LA-PAGINA-DEL-CORSO",
    "after_play": 20,
    "buffer": 5,
    "max_wait": 60 * 60,
    "headless": False,
    "start_chapter": None,
    "end_chapter": None,
    "whitelist": (),
    "blacklist": (),
    "log_file": None,
    "mute": False,
    "selectors": {
        "chapter_title": "div.align-left.flex.items-center.h-full.leading-normal.font-medium",
        "lesson_title": "div.mb-2",
        "duration": "div.text-sm.text-platform-gray",
    },
    "state_file": ".state.json",
    "max_retries": 3,
    "retry_backoff": 2.0,
    "retry_base_delay": 1.0,
    "click_timeout": 3.0,
    "navigation_timeout": 60.0,
    "page_timeout": 30.0,
    "selectors_json": None,
    "progress_threshold": 100,
    "use_gui": False,
    "slow_mo": 0,
    "user_data_dir": None,
    "diagnose_selectors": False,
}

DURATION_PATTERN = re.compile(r"\b(?:(?P<h>\d{1,2})\s*:\s*)?(?P<m>\d{1,2})\s*:\s*(?P<s>\d{2})\b")
DASH_CHARACTERS = "-–—"
NON_BREAKING_SPACES = "\u00a0\u202f"
CHAPTER_PATTERN = re.compile(
    rf"^[\s{NON_BREAKING_SPACES}]*(?P<num>\d+)[\s{NON_BREAKING_SPACES}]*[{DASH_CHARACTERS}][\s{NON_BREAKING_SPACES}]+"
)
PROGRESS_PATTERN = re.compile(r"(?P<value>\d{1,3})\s*%")
WIDTH_PATTERN = re.compile(r"width\s*:\s*(?P<value>\d{1,3})%")


FrameLike = Union[Page, Frame]


@dataclass
class ChapterPlanEntry:
    """Summary information for a chapter used during planning."""

    chapter: int
    lessons: int
    seconds: int


@dataclass
class LessonState:
    """State persisted to disk for resume support."""

    chapter: Optional[int] = None
    lesson_title: Optional[str] = None

    @classmethod
    def load(cls, path: Path) -> "LessonState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(chapter=data.get("chapter"), lesson_title=data.get("lesson_title"))
        except (json.JSONDecodeError, OSError):
            return cls()

    def save(self, path: Path) -> None:
        try:
            path.write_text(
                json.dumps({"chapter": self.chapter, "lesson_title": self.lesson_title}, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError:
            logging.getLogger(__name__).exception("Unable to write state file %s", path)


@dataclass
class RuntimeStats:
    """Collects execution statistics for the final report."""

    total: int = 0
    played: int = 0
    skipped: int = 0
    errors: int = 0
    current_chapter: Optional[int] = None
    current_lesson_index: int = 0
    planned_lessons: int = 0
    planned_seconds: int = 0
    planned_chapters: int = 0

    def new_chapter(self, chapter: int) -> None:
        self.current_chapter = chapter
        self.current_lesson_index = 0

    def next_lesson(self) -> None:
        self.current_lesson_index += 1
        self.total += 1


@dataclass
class Config:
    """Runtime configuration produced by CLI arguments."""

    url: str
    after_play: int
    buffer: int
    max_wait: int
    headless: bool
    start_chapter: Optional[int]
    end_chapter: Optional[int]
    whitelist: Sequence[re.Pattern[str]]
    blacklist: Sequence[re.Pattern[str]]
    log_file: Optional[Path]
    mute: bool
    selectors: Dict[str, str]
    state_file: Path
    max_retries: int
    retry_backoff: float
    retry_base_delay: float
    click_timeout: float
    navigation_timeout: float
    page_timeout: float
    progress_threshold: int
    use_gui: bool
    slow_mo: int
    user_data_dir: Optional[Path]
    diagnose_selectors: bool

    def chapter_in_scope(self, chapter: Optional[int]) -> bool:
        if chapter is None:
            return True
        if self.start_chapter is not None and chapter < self.start_chapter:
            return False
        if self.end_chapter is not None and chapter > self.end_chapter:
            return False
        return True


# ========================= ARGUMENT PARSING ========================= #

def parse_arguments(argv: Optional[Sequence[str]] = None) -> Config:
    parser = argparse.ArgumentParser(description="Autoplay course lessons with Playwright")
    parser.add_argument("--url", default=DEFAULT_CONFIG["url"], help="Course page URL")
    parser.add_argument("--after-play", type=int, default=DEFAULT_CONFIG["after_play"], help="Seconds to wait immediately after clicking play")
    parser.add_argument("--buffer", type=int, default=DEFAULT_CONFIG["buffer"], help="Extra buffer seconds after the detected duration")
    parser.add_argument("--max-wait", type=int, default=DEFAULT_CONFIG["max_wait"], help="Maximum wait in seconds for a single lesson")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--start-chapter", type=int, help="Chapter number to start from (inclusive)")
    parser.add_argument("--end-chapter", type=int, help="Chapter number to stop at (inclusive)")
    parser.add_argument("--whitelist", action="append", default=None, help="Regex for lesson titles to include (can be repeated)")
    parser.add_argument("--blacklist", action="append", default=None, help="Regex for lesson titles to skip (can be repeated)")
    parser.add_argument("--log-file", type=Path, help="Optional log file path")
    parser.add_argument("--mute", action="store_true", help="Mute player if possible")
    parser.add_argument("--selectors-json", type=Path, help="JSON file with selector overrides")
    parser.add_argument("--state-file", type=Path, default=Path(DEFAULT_CONFIG["state_file"]), help="Path to resume state JSON file")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_CONFIG["max_retries"], help="Maximum retries for click actions")
    parser.add_argument("--retry-backoff", type=float, default=DEFAULT_CONFIG["retry_backoff"], help="Backoff multiplier for retries")
    parser.add_argument("--retry-base-delay", type=float, default=DEFAULT_CONFIG["retry_base_delay"], help="Base delay in seconds for retries")
    parser.add_argument("--click-timeout", type=float, default=DEFAULT_CONFIG["click_timeout"], help="Timeout for click operations in seconds")
    parser.add_argument("--navigation-timeout", type=float, default=DEFAULT_CONFIG["navigation_timeout"], help="Navigation timeout in seconds")
    parser.add_argument("--page-timeout", type=float, default=DEFAULT_CONFIG["page_timeout"], help="Generic page wait timeout in seconds")
    parser.add_argument("--progress-threshold", type=int, default=DEFAULT_CONFIG["progress_threshold"], help="Skip lessons whose detected progress is greater or equal to this percentage")
    parser.add_argument("--slow", type=int, default=DEFAULT_CONFIG["slow_mo"], help="Delay in milliseconds applied between Playwright actions")
    parser.add_argument("--user-data-dir", type=Path, default=DEFAULT_CONFIG["user_data_dir"], help="Use an existing Chrome user data directory for persistent login")
    parser.add_argument("--gui", action="store_true", help="Launch a minimal GUI to choose chapter range and start playback")
    parser.add_argument(
        "--diagnose-selectors",
        action="store_true",
        help="Print selector diagnostics after navigation and exit",
    )

    args = parser.parse_args(argv)

    selectors = dict(DEFAULT_CONFIG["selectors"])
    if args.selectors_json:
        try:
            selectors_override = json.loads(Path(args.selectors_json).read_text(encoding="utf-8"))
            selectors.update({k: v for k, v in selectors_override.items() if isinstance(v, str) and v})
        except (json.JSONDecodeError, OSError) as exc:
            raise SystemExit(f"Unable to load selectors from {args.selectors_json}: {exc}")

    whitelist = tuple(re.compile(pattern) for pattern in (args.whitelist or []))
    blacklist = tuple(re.compile(pattern) for pattern in (args.blacklist or []))

    return Config(
        url=args.url,
        after_play=args.after_play,
        buffer=args.buffer,
        max_wait=args.max_wait,
        headless=args.headless,
        start_chapter=args.start_chapter,
        end_chapter=args.end_chapter,
        whitelist=whitelist,
        blacklist=blacklist,
        log_file=args.log_file,
        mute=args.mute,
        selectors=selectors,
        state_file=args.state_file,
        max_retries=args.max_retries,
        retry_backoff=args.retry_backoff,
        retry_base_delay=args.retry_base_delay,
        click_timeout=args.click_timeout,
        navigation_timeout=args.navigation_timeout,
        page_timeout=args.page_timeout,
        progress_threshold=args.progress_threshold,
        use_gui=args.gui,
        slow_mo=max(0, args.slow),
        user_data_dir=args.user_data_dir,
        diagnose_selectors=args.diagnose_selectors,
    )


# ========================= LOGGING SETUP ========================= #

def setup_logging(config: Config) -> None:
    log_level = logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if config.log_file:
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(config.log_file, encoding="utf-8")
        handlers.append(file_handler)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


# ========================= UTILITIES ========================= #

def summarise_config(config: Config) -> str:
    selectors_preview = ", ".join(f"{k}={v}" for k, v in config.selectors.items())
    whitelist = ", ".join(p.pattern for p in config.whitelist) or "<none>"
    blacklist = ", ".join(p.pattern for p in config.blacklist) or "<none>"
    return (
        "Configured run:\n"
        f"  URL: {config.url}\n"
        f"  Headless: {config.headless}\n"
        f"  Wait after play: {config.after_play}s (buffer {config.buffer}s, max {config.max_wait}s)\n"
        f"  Chapter range: {config.start_chapter or '-'} -> {config.end_chapter or '-'}\n"
        f"  Whitelist: {whitelist}\n"
        f"  Blacklist: {blacklist}\n"
        f"  Retries: {config.max_retries} (base delay {config.retry_base_delay}s, backoff {config.retry_backoff})\n"
        f"  Progress threshold: >={config.progress_threshold}% will be skipped\n"
        f"  Selectors: {selectors_preview}\n"
        f"  State file: {config.state_file}\n"
        f"  Slow-mo: {config.slow_mo}ms\n"
        f"  Chrome profile: {config.user_data_dir or '<none>'}\n"
        f"  Diagnose selectors: {config.diagnose_selectors}\n"
        f"  Logging to: {config.log_file or 'console only'}\n"
    )


def format_seconds(total_seconds: int) -> str:
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:d}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes:d}m {seconds:02d}s"
    return f"{seconds:d}s"


def is_placeholder_url(url: str) -> bool:
    return not url or url == DEFAULT_CONFIG["url"]


def maybe_launch_gui(config: Config) -> Config:
    if not config.use_gui:
        return config

    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise SystemExit("Tkinter is required for --gui but is not available") from exc

    root = tk.Tk()
    root.title("Autoplay Lessons")
    root.geometry("420x240")

    tk.Label(root, text="Configurazione rapida", font=("Segoe UI", 11, "bold")).pack(pady=(12, 4))

    form = tk.Frame(root)
    form.pack(pady=4, padx=8, fill="x")
    form.columnconfigure(1, weight=1)

    tk.Label(form, text="URL:").grid(row=0, column=0, padx=4, pady=4, sticky="e")
    url_var = tk.StringVar(value="" if is_placeholder_url(config.url) else config.url)
    tk.Entry(form, textvariable=url_var, width=40).grid(row=0, column=1, padx=4, pady=4, sticky="we")

    tk.Label(form, text="Capitolo iniziale:").grid(row=1, column=0, padx=4, pady=4, sticky="e")
    start_var = tk.StringVar(value="" if config.start_chapter is None else str(config.start_chapter))
    tk.Entry(form, textvariable=start_var, width=12).grid(row=1, column=1, padx=4, pady=4, sticky="w")

    tk.Label(form, text="Capitolo finale:").grid(row=2, column=0, padx=4, pady=4, sticky="e")
    end_var = tk.StringVar(value="" if config.end_chapter is None else str(config.end_chapter))
    tk.Entry(form, textvariable=end_var, width=12).grid(row=2, column=1, padx=4, pady=4, sticky="w")

    tk.Label(
        root,
        text=(
            "Compila l'URL del corso e l'intervallo capitoli (opzionale).\n"
            "Premi Avvia per calcolare la durata stimata."
        ),
        justify="center",
    ).pack(pady=6)

    result = {
        "url": config.url,
        "start": config.start_chapter,
        "end": config.end_chapter,
        "confirmed": False,
    }

    def on_start() -> None:
        try:
            url_value = url_var.get().strip()
            if not url_value:
                raise ValueError("URL richiesto")
            start_value = start_var.get().strip()
            end_value = end_var.get().strip()
            start = int(start_value) if start_value else None
            end = int(end_value) if end_value else None
        except ValueError:
            messagebox.showerror(
                "Valore non valido",
                "Inserisci un URL valido e numeri interi per inizio/fine capitolo",
            )
            return

        if start is not None and end is not None and start > end:
            messagebox.showerror("Intervallo non valido", "Il capitolo iniziale deve essere <= capitolo finale")
            return

        result["url"] = url_value
        result["start"] = start
        result["end"] = end
        result["confirmed"] = True
        root.destroy()

    def on_cancel() -> None:
        result["confirmed"] = False
        root.destroy()

    buttons = tk.Frame(root)
    buttons.pack(pady=10)

    tk.Button(buttons, text="Avvia", command=on_start, width=12).grid(row=0, column=0, padx=6)
    tk.Button(buttons, text="Annulla", command=on_cancel, width=12).grid(row=0, column=1, padx=6)

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    if not result["confirmed"]:
        raise SystemExit("Execution cancelled from GUI")

    return replace(
        config,
        url=result["url"],
        start_chapter=result["start"],
        end_chapter=result["end"],
        use_gui=False,
    )


def prompt_for_missing_url(config: Config) -> Config:
    if not is_placeholder_url(config.url):
        return config
    if not sys.stdin.isatty():
        raise SystemExit("Provide --url when running non-interactively")

    while True:
        try:
            entered = input("Inserisci l'URL del corso: ").strip()
        except EOFError as exc:  # pragma: no cover - interactive guard
            raise SystemExit("URL del corso non fornito") from exc
        if entered:
            return replace(config, url=entered)
        print("L'URL non può essere vuoto.")


def describe_context(context: FrameLike) -> str:
    if isinstance(context, Page):
        return f"page({context.url})"
    name = context.name or "<unnamed>"
    return f"frame {name} ({context.url})"


def iter_contexts(page: Page) -> List[FrameLike]:
    contexts: List[FrameLike] = []
    seen: set[int] = set()
    for context in [page, *page.frames]:
        identifier = id(context)
        if identifier in seen:
            continue
        contexts.append(context)
        seen.add(identifier)
    return contexts


async def log_frame_diagnostics(
    page: Page, selector: str, logger: logging.Logger, label: Optional[str] = None
) -> None:
    heading = label or selector
    logger.info("Selector diagnostic for %s", heading)
    for context in iter_contexts(page):
        context_label = describe_context(context)
        try:
            locator = context.locator(selector)
            count = await locator.count()
        except PlaywrightError as exc:
            logger.info("  %s -> locator error: %s", context_label, exc)
            continue

        logger.info("  %s -> %s matches", context_label, count)
        if not count:
            continue
        try:
            samples = await locator.all_inner_texts()
        except PlaywrightError:
            continue
        if samples:
            preview = ", ".join(text.strip().replace("\n", " ") for text in samples[:3])
            logger.info("    samples: %s", preview)


async def ensure_course_ready(
    page: Page, config: Config, logger: logging.Logger
) -> Optional[FrameLike]:
    """Locate the frame or page containing the chapter list, prompting the user if needed."""

    selector = config.selectors["chapter_title"]
    attempt = 0
    while True:
        attempt += 1
        for context in iter_contexts(page):
            try:
                locator = context.locator(selector)
                count = await locator.count()
            except PlaywrightError as exc:
                logger.debug("Selector check failed in %s: %s", describe_context(context), exc)
                continue
            if count:
                logger.info(
                    "Detected %s chapter headers in %s using %s",
                    count,
                    describe_context(context),
                    selector,
                )
                return context

        logger.warning(
            "No chapters found yet (attempt %s, selector %s, URL %s)",
            attempt,
            selector,
            page.url,
        )
        await log_frame_diagnostics(page, selector, logger)

        if not sys.stdin.isatty():
            return None

        logger.info(
            "If the platform requires login, authenticate in the opened browser window, then press Invio to retry."
        )
        loop = asyncio.get_running_loop()

        def ask() -> str:
            try:
                return input("Premi Invio dopo aver effettuato l'accesso (stop per annullare): ")
            except EOFError:
                return "stop"

        response = await loop.run_in_executor(None, ask)
        if response.strip().lower() == "stop":
            logger.error("Execution stopped while waiting for chapters to appear")
            return None
        logger.info("Retrying chapter detection…")


async def run_selector_diagnostics(
    page: Page, context: FrameLike, config: Config, logger: logging.Logger
) -> None:
    logger.info("Running selector diagnostics (no playback will occur)")
    for key, selector in config.selectors.items():
        await log_frame_diagnostics(page, selector, logger, label=f"{key} -> {selector}")

    heuristics: Tuple[Tuple[str, str], ...] = (
        ("panel heading", "text=Contenuti del Corso"),
        ("progress cell", "css=.w-1/12"),
    )
    for label, selector in heuristics:
        await log_frame_diagnostics(page, selector, logger, label=label)

    try:
        locator = context.locator(config.selectors["chapter_title"])
        texts = await locator.all_inner_texts()
    except PlaywrightError:
        texts = []
    if texts:
        logger.info("First chapter headers detected: %s", "; ".join(t.strip() for t in texts[:3]))


def parse_duration(text: str) -> Optional[int]:
    match = DURATION_PATTERN.search(text)
    if not match:
        return None
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    return hours * 3600 + minutes * 60 + seconds


def normalise_text_spacing(text: str) -> str:
    """Replace non-breaking space variants with regular spaces."""

    for char in NON_BREAKING_SPACES:
        text = text.replace(char, " ")
    return text


def extract_chapter_number(text: str) -> Optional[int]:
    match = CHAPTER_PATTERN.search(normalise_text_spacing(text))
    if match:
        return int(match.group("num"))
    return None


def matches_patterns(patterns: Sequence[re.Pattern[str]], title: str) -> bool:
    return any(pattern.search(title) for pattern in patterns)


async def ensure_visible(locator: Locator) -> None:
    try:
        await locator.scroll_into_view_if_needed(timeout=1000)
    except PlaywrightError:
        pass


async def scroll_with_wheel(
    page: Page, attempts: int = 3, step: int = 600, target: Optional[Locator] = None
) -> None:
    for _ in range(attempts):
        if target is not None:
            try:
                await target.hover()
            except PlaywrightError:
                pass
        await page.mouse.wheel(0, step)
        await page.wait_for_timeout(200)


async def exponential_retry(
    func,
    max_attempts: int,
    base_delay: float,
    backoff: float,
    on_failure,
) -> bool:
    for attempt in range(1, max_attempts + 1):
        try:
            await func()
            return True
        except PlaywrightError as exc:  # Playwright-specific errors
            on_failure(attempt, exc)
        except Exception as exc:  # pragma: no cover - guard against unforeseen errors
            on_failure(attempt, exc)
        if attempt < max_attempts:
            delay = base_delay * (backoff ** (attempt - 1))
            await asyncio.sleep(delay)
    return False


async def take_error_screenshot(page: Page, prefix: str = "error") -> Optional[Path]:
    directory = Path("errors")
    directory.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = directory / f"{prefix}_{timestamp}.png"
    try:
        await page.screenshot(path=str(filepath), full_page=True)
        logging.getLogger(__name__).info("Saved screenshot %s", filepath)
        return filepath
    except PlaywrightError:
        logging.getLogger(__name__).exception("Unable to capture screenshot")
    return None


async def is_completed(row: Locator, threshold: int) -> bool:
    """Return True if the lesson row appears completed.

    This is intentionally conservative; adjust the logic to match the platform.
    TODO: replace generic checks below with a selector specific to the completion badge or icon.
    """

    try:
        text = (await row.inner_text(timeout=1000)).strip()
    except PlaywrightError:
        return False

    for match in PROGRESS_PATTERN.finditer(text):
        if int(match.group("value")) >= threshold:
            return True

    try:
        percentage_cells = row.locator("div.w-1/12.text-xs.md\\:text-xs")
        for index in range(await percentage_cells.count()):
            cell_text = (await percentage_cells.nth(index).inner_text(timeout=500)).strip()
            match = PROGRESS_PATTERN.search(cell_text)
            if match and int(match.group("value")) >= threshold:
                return True
    except PlaywrightError:
        pass

    style = await row.get_attribute("style")
    if style:
        match = WIDTH_PATTERN.search(style)
        if match and int(match.group("value")) >= threshold:
            return True

    # Search for accessible completion cues (e.g., "Completata")
    if "complet" in text.lower():
        return True

    # Progress bar semantics (e.g., aria-valuenow="60")
    progressbars = row.locator("[role='progressbar']")
    for index in range(await progressbars.count()):
        try:
            aria_value = await progressbars.nth(index).get_attribute("aria-valuenow")
        except PlaywrightError:
            continue
        if aria_value and aria_value.isdigit() and int(aria_value) >= threshold:
            return True

    return False


async def try_mute(page: Page) -> None:
    """Attempt to mute the player by clicking a volume button if present."""

    candidates = [
        "button[aria-label*='mute' i]",
        "button[aria-label*='volume' i]",
        "[class*='mute']",
    ]
    for selector in candidates:
        button = page.locator(selector)
        try:
            if await button.count() and await button.first.is_visible():
                await button.first.click(timeout=1000)
                logging.getLogger(__name__).info("Player muted via %s", selector)
                return
        except PlaywrightError:
            continue


# ========================= LESSON PROCESSING ========================= #

async def wait_for_network_idle(page: Page, timeout: float) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout * 1000)
    except PlaywrightTimeout:
        logging.getLogger(__name__).warning("Network idle wait timed out after %.1fs", timeout)


async def locate_chapter(
    context: FrameLike, selectors: Dict[str, str], chapter_number: int
) -> Optional[Locator]:
    pattern = re.compile(
        rf"^[\s{NON_BREAKING_SPACES}]*{chapter_number}[\s{NON_BREAKING_SPACES}]*[{DASH_CHARACTERS}][\s{NON_BREAKING_SPACES}]+",
        re.IGNORECASE,
    )
    locator = context.locator(selectors["chapter_title"]).filter(has_text=pattern)
    if await locator.count():
        return locator.first

    headers = context.locator(selectors["chapter_title"])
    count = await headers.count()
    for index in range(count):
        candidate = headers.nth(index)
        try:
            raw_text = await candidate.inner_text(timeout=1000)
        except PlaywrightError:
            continue
        text = normalise_text_spacing(raw_text)
        if pattern.search(text) or extract_chapter_number(text) == chapter_number:
            return candidate
    return None


async def expand_chapter(
    context: FrameLike,
    page: Page,
    selectors: Dict[str, str],
    chapter_number: int,
    config: Config,
    logger: logging.Logger,
) -> bool:
    async def action() -> None:
        locator = await locate_chapter(context, selectors, chapter_number)
        if locator is None:
            raise RuntimeError(f"Chapter {chapter_number} not found")
        await ensure_visible(locator)
        try:
            container = locator.locator("xpath=ancestor-or-self::*[self::li or self::div][1]")
            panel = container.locator("xpath=following-sibling::*")
            probe = panel.locator(selectors["lesson_title"])
            if await probe.count():
                first = probe.first
                try:
                    visible = await first.evaluate(
                        "el => el && (el.offsetParent !== null || el.getClientRects().length > 0)"
                    )
                except PlaywrightError:
                    visible = await first.is_visible()
                if visible:
                    return
        except PlaywrightError:
            pass
        clickable = locator.locator("xpath=ancestor-or-self::*[self::div][1]")
        target = clickable.first if await clickable.count() else locator
        await target.click(timeout=config.click_timeout * 1000)

    def on_failure(attempt: int, exc: Exception) -> None:
        logger.warning(
            "Chapter %s click attempt %s/%s failed: %s", chapter_number, attempt, config.max_retries, exc
        )

    success = await exponential_retry(
        action,
        config.max_retries,
        config.retry_base_delay,
        config.retry_backoff,
        on_failure,
    )
    if not success:
        await take_error_screenshot(page, prefix=f"chapter_{chapter_number}")
    return success


async def collect_lesson_rows(
    context: FrameLike,
    page: Page,
    selectors: Dict[str, str],
    logger: logging.Logger,
    config: Config,
) -> List[Locator]:
    lessons: List[Locator] = []
    title_nodes = context.locator(selectors["lesson_title"])
    duration_nodes = context.locator(selectors["duration"])

    duration_parents: List[Locator] = []
    for index in range(await duration_nodes.count()):
        node = duration_nodes.nth(index)
        try:
            text = await node.inner_text(timeout=config.page_timeout * 1000)
        except PlaywrightError:
            continue
        if parse_duration(text or "") is not None:
            parent = node.locator("xpath=ancestor-or-self::*[self::li or self::div or self::section][1]")
            duration_parents.append(parent if await parent.count() else node)

    seen_positions: set = set()
    for index in range(await title_nodes.count()):
        title = title_nodes.nth(index)
        row = title.locator("xpath=ancestor-or-self::*[self::li or self::div or self::section][1]")
        if not await row.count():
            row = title

        has_duration = False
        for parent in duration_parents:
            try:
                if await parent.filter(has=row).count() or await row.filter(has=parent).count():
                    has_duration = True
                    break
            except PlaywrightError:
                continue
        if not has_duration:
            try:
                raw_text = await row.inner_text(timeout=config.page_timeout * 1000)
            except PlaywrightError:
                continue
            if parse_duration(raw_text) is None:
                continue

        try:
            bounding_box = await row.bounding_box()
        except PlaywrightError:
            bounding_box = None
        key = (
            round(bounding_box["x"]) if bounding_box else 0,
            round(bounding_box["y"]) if bounding_box else index,
        )
        if key in seen_positions:
            continue
        seen_positions.add(key)
        lessons.append(row)

    if not lessons:
        logger.warning("No lessons detected; attempting scroll")
        anchor: Optional[Locator] = None
        try:
            if await title_nodes.count():
                anchor = title_nodes.first
        except PlaywrightError:
            anchor = None
        await scroll_with_wheel(page, attempts=5, target=anchor)
    return lessons


async def read_lesson_title(row: Locator, config: Config, timeout_ms: float) -> tuple[str, Locator]:
    title_locator = row.locator(config.selectors["lesson_title"]).first
    try:
        if await title_locator.count() == 0:
            raise PlaywrightError("Title locator not found")
        title = (await title_locator.inner_text(timeout=timeout_ms)).strip()
    except PlaywrightError:
        title = (await row.inner_text(timeout=timeout_ms)).strip().splitlines()[0]
        title_locator = row
    return title, title_locator


async def collect_course_plan(
    context: FrameLike,
    page: Page,
    config: Config,
    logger: logging.Logger,
    state: LessonState,
) -> tuple[int, int, int, List[ChapterPlanEntry]]:
    plan_state = LessonState(chapter=state.chapter, lesson_title=state.lesson_title)
    chapter_locators = context.locator(config.selectors["chapter_title"])
    count = await chapter_locators.count()
    planned_lessons = 0
    planned_seconds = 0
    planned_chapters = 0
    entries: List[ChapterPlanEntry] = []

    for index in range(count):
        header = chapter_locators.nth(index)
        try:
            text = (await header.inner_text(timeout=2000)).strip()
        except PlaywrightError:
            continue
        chapter_number = extract_chapter_number(text)
        if chapter_number is None:
            continue
        if not config.chapter_in_scope(chapter_number):
            continue
        if plan_state.chapter and chapter_number < plan_state.chapter:
            continue

        if not await expand_chapter(context, page, config.selectors, chapter_number, config, logger):
            continue
        await page.wait_for_timeout(200)
        rows = await collect_lesson_rows(context, page, config.selectors, logger, config)
        chapter_lessons = 0
        chapter_seconds = 0
        for row in rows:
            timeout_ms = config.page_timeout * 1000
            title, _ = await read_lesson_title(row, config, timeout_ms)
            if config.whitelist and not matches_patterns(config.whitelist, title):
                continue
            if config.blacklist and matches_patterns(config.blacklist, title):
                continue

            if plan_state.chapter == chapter_number and plan_state.lesson_title:
                if plan_state.lesson_title == title:
                    plan_state.chapter = None
                    plan_state.lesson_title = None
                else:
                    continue

            if await is_completed(row, config.progress_threshold):
                continue

            try:
                raw_text = await row.inner_text(timeout=timeout_ms)
            except PlaywrightError:
                continue
            duration_seconds = parse_duration(raw_text)
            if duration_seconds is None:
                continue

            planned_lessons += 1
            planned_seconds += duration_seconds
            chapter_lessons += 1
            chapter_seconds += duration_seconds

        if chapter_lessons:
            planned_chapters += 1
            entries.append(
                ChapterPlanEntry(
                    chapter=chapter_number,
                    lessons=chapter_lessons,
                    seconds=chapter_seconds,
                )
            )

    entries.sort(key=lambda entry: entry.chapter)
    return planned_lessons, planned_seconds, planned_chapters, entries


def summarise_plan_entries(
    entries: Sequence[ChapterPlanEntry],
    start: Optional[int],
    end: Optional[int],
) -> tuple[int, int, int]:
    filtered = [
        entry
        for entry in entries
        if (start is None or entry.chapter >= start)
        and (end is None or entry.chapter <= end)
    ]
    lessons = sum(entry.lessons for entry in filtered)
    seconds = sum(entry.seconds for entry in filtered)
    chapters = len(filtered)
    return lessons, seconds, chapters


async def maybe_prompt_for_chapter_range(
    entries: Sequence[ChapterPlanEntry],
    config: Config,
    logger: logging.Logger,
) -> bool:
    if not entries:
        return False
    if config.start_chapter is not None and config.end_chapter is not None:
        return False
    if not sys.stdin.isatty():
        return False

    available = [entry.chapter for entry in entries]
    min_chapter = min(available)
    max_chapter = max(available)
    default_start = config.start_chapter
    default_end = config.end_chapter

    loop = asyncio.get_running_loop()

    def prompt() -> tuple[Optional[int], Optional[int]]:
        while True:
            print("\n--- Selezione capitoli ---")
            print(
                "Capitoli disponibili:",
                ", ".join(str(chapter) for chapter in available),
            )
            print(
                f"Intervallo attuale: {default_start or min_chapter} -> {default_end or max_chapter}"
            )
            start_prompt = (
                "Capitolo iniziale (invio per tutti i capitoli): "
                if default_start is None
                else f"Capitolo iniziale (invio per {default_start}): "
            )
            end_prompt = (
                "Capitolo finale (invio per tutti i capitoli): "
                if default_end is None
                else f"Capitolo finale (invio per {default_end}): "
            )
            try:
                start_raw = input(start_prompt).strip()
                end_raw = input(end_prompt).strip()
            except EOFError:
                return default_start, default_end
            try:
                start_value = int(start_raw) if start_raw else default_start
                end_value = int(end_raw) if end_raw else default_end
            except ValueError:
                print("Inserisci numeri interi oppure lascia vuoto per usare il default.")
                continue

            if start_value is not None and start_value < min_chapter:
                print(f"Il capitolo iniziale deve essere >= {min_chapter}.")
                continue
            if end_value is not None and end_value > max_chapter:
                print(f"Il capitolo finale deve essere <= {max_chapter}.")
                continue
            if start_value is not None and end_value is not None and start_value > end_value:
                print("Il capitolo iniziale deve essere <= capitolo finale.")
                continue

            return start_value, end_value

    start_value, end_value = await loop.run_in_executor(None, prompt)

    if start_value == config.start_chapter and end_value == config.end_chapter:
        return False

    config.start_chapter = start_value
    config.end_chapter = end_value
    start_label = str(start_value) if start_value is not None else f"{min_chapter} (tutti)"
    end_label = str(end_value) if end_value is not None else f"{max_chapter} (tutti)"
    logger.info("Selected chapters: %s -> %s", start_label, end_label)
    return True


async def play_lesson(
    page: Page,
    row: Locator,
    index: int,
    total: int,
    config: Config,
    logger: logging.Logger,
    stats: RuntimeStats,
    state: LessonState,
) -> None:
    stats.next_lesson()

    timeout_ms = config.page_timeout * 1000
    title, title_locator = await read_lesson_title(row, config, timeout_ms)

    if config.whitelist and not matches_patterns(config.whitelist, title):
        logger.info("Skipping %s (not in whitelist)", title)
        stats.skipped += 1
        return
    if config.blacklist and matches_patterns(config.blacklist, title):
        logger.info("Skipping %s (matches blacklist)", title)
        stats.skipped += 1
        return

    if state.chapter == stats.current_chapter and state.lesson_title:
        if state.lesson_title == title:
            logger.info("Resuming after lesson %s", title)
            state.chapter = None
            state.lesson_title = None
        else:
            logger.info("Skipping %s (before resume point)", title)
            stats.skipped += 1
            return

    if await is_completed(row, config.progress_threshold):
        logger.info("Skipping %s (already completed)", title)
        stats.skipped += 1
        return

    try:
        raw_text = await row.inner_text(timeout=timeout_ms)
    except PlaywrightError:
        raw_text = title
    duration_seconds = parse_duration(raw_text)
    if duration_seconds is None:
        logger.warning("Skipping %s: duration not found", title)
        stats.skipped += 1
        return

    logger.info("[%s/%s] Playing '%s' (%ss)", index, total, title, duration_seconds)

    async def click_action() -> None:
        await ensure_visible(title_locator)
        await title_locator.click(timeout=config.click_timeout * 1000)

    def on_failure(attempt: int, exc: Exception) -> None:
        logger.warning(
            "Click attempt %s/%s failed for '%s': %s",
            attempt,
            config.max_retries,
            title,
            exc,
        )
        asyncio.create_task(page.mouse.wheel(0, 400))

    clicked = await exponential_retry(
        click_action,
        config.max_retries,
        config.retry_base_delay,
        config.retry_backoff,
        on_failure,
    )
    if not clicked:
        logger.error("Unable to click '%s' after retries", title)
        await take_error_screenshot(page, prefix=f"lesson_{stats.current_chapter}_{index}")
        stats.errors += 1
        return

    if config.mute:
        await try_mute(page)

    logger.info("Waiting %ss initial delay", config.after_play)
    await page.wait_for_timeout(config.after_play * 1000)

    remaining = max(0, duration_seconds - config.after_play) + config.buffer
    remaining = min(remaining, config.max_wait)
    if remaining:
        logger.info("Waiting %ss for remaining duration", remaining)
        await page.wait_for_timeout(remaining * 1000)

    logger.info("Completed '%s'", title)
    stats.played += 1
    state.chapter = stats.current_chapter
    state.lesson_title = title
    state.save(config.state_file)


async def process_chapter(
    page: Page,
    context: FrameLike,
    chapter_number: int,
    config: Config,
    logger: logging.Logger,
    stats: RuntimeStats,
    state: LessonState,
) -> bool:
    if not config.chapter_in_scope(chapter_number):
        logger.info("Chapter %s outside configured range; skipping", chapter_number)
        return True

    logger.info("Opening chapter %s", chapter_number)
    if not await expand_chapter(context, page, config.selectors, chapter_number, config, logger):
        logger.warning("Chapter %s could not be opened", chapter_number)
        return False

    stats.new_chapter(chapter_number)

    try:
        await context.wait_for_selector(
            config.selectors["lesson_title"],
            timeout=config.page_timeout * 1000,
        )
    except PlaywrightTimeout:
        logger.warning("Lesson titles did not appear in time for chapter %s", chapter_number)

    await page.wait_for_timeout(500)
    lessons = await collect_lesson_rows(context, page, config.selectors, logger, config)
    if not lessons:
        logger.warning("No lessons in chapter %s", chapter_number)
        return True

    for index, row in enumerate(lessons, start=1):
        try:
            await play_lesson(page, row, index, len(lessons), config, logger, stats, state)
        except Exception as exc:  # pragma: no cover - resilient automation
            logger.exception("Unexpected error on lesson %s/%s in chapter %s: %s", index, len(lessons), chapter_number, exc)
            await take_error_screenshot(page, prefix=f"exception_{chapter_number}_{index}")
            stats.errors += 1
    return True


async def iterate_chapters(
    page: Page,
    context: FrameLike,
    config: Config,
    logger: logging.Logger,
    state: LessonState,
    stats: RuntimeStats,
) -> None:
    chapter_locators = context.locator(config.selectors["chapter_title"])
    count = await chapter_locators.count()
    if not count:
        logger.error("No chapters found with selector %s", config.selectors["chapter_title"])
        return

    for index in range(count):
        header = chapter_locators.nth(index)
        try:
            text = (await header.inner_text(timeout=2000)).strip()
        except PlaywrightError:
            continue
        chapter_number = extract_chapter_number(text)
        if chapter_number is None:
            continue
        if config.start_chapter and chapter_number < config.start_chapter:
            continue
        if config.end_chapter and chapter_number > config.end_chapter:
            break
        if state.chapter and chapter_number < state.chapter:
            logger.info("Skipping chapter %s (before resume state)", chapter_number)
            continue

        if not await process_chapter(page, context, chapter_number, config, logger, stats, state):
            break

    logger.info("Finished iterating chapters")


async def run(config: Config) -> RuntimeStats:
    logger = logging.getLogger(__name__)
    stats = RuntimeStats()
    state = LessonState.load(config.state_file)

    async with async_playwright() as playwright:
        launch_args = ["--start-maximized"]
        if config.user_data_dir:
            launch_args.append(f"--user-data-dir={config.user_data_dir}")

        browser: Browser = await playwright.chromium.launch(
            channel="chrome",
            headless=config.headless,
            slow_mo=config.slow_mo or None,
            args=launch_args,
        )
        context = await browser.new_context(viewport={"width": 1366, "height": 900})
        page = await context.new_page()

        logger.info("Navigating to %s", config.url)
        response = await page.goto(
            config.url,
            wait_until="domcontentloaded",
            timeout=config.navigation_timeout * 1000,
        )
        await wait_for_network_idle(page, config.navigation_timeout)

        logger.info("Current URL after navigation: %s", page.url)

        status = response.status if response else None
        if response and response.ok:
            logger.info("Reached %s successfully (status %s)", config.url, status)
        else:
            logger.warning("Reached %s with status %s", config.url, status or "unknown")

        lesson_context = await ensure_course_ready(page, config, logger)
        if lesson_context is None:
            await browser.close()
            return stats

        if config.diagnose_selectors:
            await run_selector_diagnostics(page, lesson_context, config, logger)
            await browser.close()
            return stats

        logger.info("Scanning chapters to compute estimated duration")
        (
            planned_lessons,
            planned_seconds,
            planned_chapters,
            plan_entries,
        ) = await collect_course_plan(lesson_context, page, config, logger, state)

        stats.planned_lessons = planned_lessons
        stats.planned_seconds = planned_seconds
        stats.planned_chapters = planned_chapters

        if planned_lessons:
            logger.info(
                "Plan: %s lessons across %s chapters (~%s)",
                planned_lessons,
                planned_chapters,
                format_seconds(planned_seconds),
            )
        else:
            logger.warning("Plan found no lessons to play with the current filters")
            logger.warning("If this is unexpected, ensure you are logged in and the page lists the lessons")

        if plan_entries:
            for entry in plan_entries:
                logger.info(
                    "  Chapter %s -> %s lessons (~%s)",
                    entry.chapter,
                    entry.lessons,
                    format_seconds(entry.seconds),
                )

        if await maybe_prompt_for_chapter_range(plan_entries, config, logger):
            filtered_lessons, filtered_seconds, filtered_chapters = summarise_plan_entries(
                plan_entries,
                config.start_chapter,
                config.end_chapter,
            )
            stats.planned_lessons = filtered_lessons
            stats.planned_seconds = filtered_seconds
            stats.planned_chapters = filtered_chapters
            if filtered_lessons:
                logger.info(
                    "Updated plan: %s lessons across %s chapters (~%s)",
                    filtered_lessons,
                    filtered_chapters,
                    format_seconds(filtered_seconds),
                )
            else:
                logger.warning("The selected range contains no lessons to play")

        if state.chapter and state.lesson_title:
            logger.info("Resuming from chapter %s, lesson '%s'", state.chapter, state.lesson_title)
        elif state.chapter:
            logger.info("Resuming from chapter %s", state.chapter)

        await iterate_chapters(page, lesson_context, config, logger, state, stats)

        await browser.close()

    return stats


def print_report(stats: RuntimeStats) -> None:
    logger = logging.getLogger(__name__)
    logger.info(
        "Run summary: total=%s, played=%s, skipped=%s, errors=%s",
        stats.total,
        stats.played,
        stats.skipped,
        stats.errors,
    )
    if stats.planned_lessons:
        logger.info(
            "Planned %s lessons (~%s) across %s chapters",
            stats.planned_lessons,
            format_seconds(stats.planned_seconds),
            stats.planned_chapters,
        )


def main(argv: Optional[Sequence[str]] = None) -> None:
    config = parse_arguments(argv)
    config = maybe_launch_gui(config)
    config = prompt_for_missing_url(config)
    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info("%s", summarise_config(config))

    try:
        stats = asyncio.run(run(config))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return
    print_report(stats)


if __name__ == "__main__":
    main()
