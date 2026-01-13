"""Configuration utilities for the autoplay lesson runner."""
from __future__ import annotations

import argparse
import json
import re
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence

try:  # pragma: no cover - optional dependency
    import keyring  # type: ignore
    from keyring.errors import KeyringError  # type: ignore
except Exception:  # pragma: no cover - keyring may be missing
    keyring = None  # type: ignore
    KeyringError = Exception  # type: ignore


DURATION_PATTERN = re.compile(r"\b(?:(?P<h>\d{1,2})\s*:\s*)?(?P<m>\d{1,2})\s*:\s*(?P<s>\d{2})\b")

DEFAULT_USER_DATA_DIR = Path("~/.config/autoplay-lesson/chrome-profile").expanduser()
CONFIG_DIR = Path.home() / ".autoplay_lesson"
CONFIG_FILE = CONFIG_DIR / "config.json"
KEYRING_SERVICE = "autoplay_lesson"


class CourseMode(str, Enum):
    """Operational modes supported by the runner."""

    COMPLETE = "complete"
    COURSES_ONLY = "courses"
    QUIZ_ONLY = "quizzes"

    @property
    def label(self) -> str:
        mapping = {
            CourseMode.COMPLETE: "Corsi completi",
            CourseMode.COURSES_ONLY: "Solo corsi",
            CourseMode.QUIZ_ONLY: "Solo quiz",
        }
        return mapping.get(self, self.value)


@dataclass(slots=True)
class RuntimeConfig:
    """Container for CLI or GUI supplied runtime configuration."""

    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    remember_me: bool = True
    after_play: int = 15
    buffer: int = 3
    max_wait: int = 3600
    stall_timeout: float = 120.0
    max_lesson_attempts: int = 2
    headless: bool = False
    start_chapter: Optional[int] = None
    end_chapter: Optional[int] = None
    lesson_render_wait: float = 5.5
    log_file: Optional[Path] = None
    progress_threshold: int = 100
    slow_mo: int = 0
    user_data_dir: Optional[Path] = DEFAULT_USER_DATA_DIR
    use_chrome_profile: bool = True
    diagnose: bool = False
    selectors_json: Optional[Path] = None
    selector_overrides: dict[str, str] = field(default_factory=dict)
    use_gui: bool = False
    cdp_url: Optional[str] = None
    login_wait: float = 8.0
    course_mode: CourseMode = CourseMode.COMPLETE
    detailed_log: bool = False
    fast_mode: bool = False

    whitelist: tuple[re.Pattern[str], ...] = field(default_factory=tuple)
    blacklist: tuple[re.Pattern[str], ...] = field(default_factory=tuple)

    state_file: Path = Path(".state.json")
    max_retries: int = 3
    retry_backoff: float = 2.0
    retry_base_delay: float = 1.0
    click_timeout: float = 3.0
    navigation_timeout: float = 60.0
    page_timeout: float = 30.0
    course_restart_attempts: int = 3
    course_restart_base_delay: float = 15.0
    course_restart_backoff: float = 2.0
    course_restart_max_delay: float = 180.0
    page_refresh_interval: Optional[float] = 9000.0
    lesson_scroll_interval: float = 45.0
    lesson_scroll_distance: int = 420
    lesson_scroll_jitter: int = 120
    watchdog_timeout: float = 300.0
    watchdog_grace_attempts: int = 1
    browser_restart_attempts: int = 0
    browser_restart_base_delay: float = 60.0
    browser_restart_backoff: float = 2.0
    browser_restart_max_delay: float = 900.0

    def to_summary(self) -> str:
        """Return a multi-line summary describing this configuration."""

        whitelist = ", ".join(p.pattern for p in self.whitelist) or "<none>"
        blacklist = ", ".join(p.pattern for p in self.blacklist) or "<none>"
        summary = (
            "Configurazione corrente:\n"
            f"  URL: {self.url}\n"
            f"  Profilo Chrome: {'attivo' if self.use_chrome_profile and self.user_data_dir else 'disattivato'}\n"
            f"  CDP URL: {self.cdp_url or '-'}\n"
            f"  Username: {self.username or '-'}\n"
            f"  Headless: {self.headless}\n"
            f"  Slow motion: {self.slow_mo}ms\n"
            f"  Attesa post play: {self.after_play}s\n"
            f"  Buffer aggiuntivo: {self.buffer}s\n"
            f"  Tempo massimo per lezione: {self.max_wait}s\n"
            f"  Timeout stallo lezione: {self.stall_timeout}s\n"
            f"  Tentativi per lezione: {self.max_lesson_attempts}\n"
            f"  Tentativi riavvio corso: {self.course_restart_attempts}\n"
            f"  Delay riavvio corso: base={self.course_restart_base_delay}s max={self.course_restart_max_delay}s\n"
            f"  Tentativi riavvio browser: {self.browser_restart_attempts or 'illimitati'}\n"
            f"  Delay riavvio browser: base={self.browser_restart_base_delay}s max={self.browser_restart_max_delay}s\n"
            f"  Watchdog inattività: timeout={self.watchdog_timeout}s grace={self.watchdog_grace_attempts}\n"
            f"  Refresh pagina programmato: {self.page_refresh_interval or 'disattivato'}s\n"
            f"  Start chapter: {self.start_chapter or '-'}\n"
            f"  End chapter: {self.end_chapter or '-'}\n"
            f"  Render wait capitolo: {self.lesson_render_wait}s\n"
            f"  Soglia completamento: {self.progress_threshold}%\n"
            f"  File log: {self.log_file or 'solo console'}\n"
            f"  File stato: {self.state_file}\n"
            f"  Diagnostica: {self.diagnose}\n"
            f"  Modalità: {self.course_mode.label}\n"
            f"  Log dettagliato: {self.detailed_log}\n"
            f"  Modalità veloce quiz: {self.fast_mode}\n"
            f"  Whitelist: {whitelist}\n"
            f"  Blacklist: {blacklist}\n"
            f"  Ricordami: {self.remember_me}\n"
        )
        if self.selector_overrides:
            overrides = ", ".join(f"{k}={v}" for k, v in self.selector_overrides.items())
            summary += f"  Override selettori: {overrides}\n"
        return summary

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "RuntimeConfig":
        """Create a :class:`RuntimeConfig` instance from a dictionary."""

        kwargs = {key: value for key, value in data.items() if hasattr(cls, key)}
        course_mode = kwargs.get("course_mode")
        if isinstance(course_mode, str):
            try:
                kwargs["course_mode"] = CourseMode[course_mode.upper()]
            except KeyError:
                kwargs["course_mode"] = CourseMode.COMPLETE
        if "url" not in kwargs:
            kwargs["url"] = "https://www.coursera.org/learn/high-stakes-leadership/lecture/xKTQO/deepwater-horizon-setting-the-stage"
        return cls(**kwargs)

    def chapter_in_scope(self, index: int, *, number: Optional[int] = None) -> bool:
        """Return True if the chapter identified by ``index``/``number`` is in scope."""

        reference = number if number is not None else index
        if self.start_chapter is not None and reference < self.start_chapter:
            return False
        if self.end_chapter is not None and reference > self.end_chapter:
            return False
        return True

    def with_overrides(self, **kwargs) -> "RuntimeConfig":
        return replace(self, **kwargs)


DEFAULTS = RuntimeConfig(
    url="https://www.coursera.org/learn/high-stakes-leadership/lecture/xKTQO/deepwater-horizon-setting-the-stage"
)


def _encode_password(password: str) -> str:
    return urlsafe_b64encode(password.encode("utf-8")).decode("ascii")


def _decode_password(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


@dataclass(slots=True)
class PersistentSettings:
    """Representation of user supplied preferences stored on disk."""

    url: str = ""
    username: str = ""
    user_data_dir: str = str(DEFAULT_USER_DATA_DIR)
    remember_me: bool = True
    headless: bool = False
    use_chrome_profile: bool = True
    after_play: int = DEFAULTS.after_play
    buffer: int = DEFAULTS.buffer
    slow_mo: int = DEFAULTS.slow_mo
    diagnose: bool = False
    start_chapter: Optional[int] = None
    password_b64: Optional[str] = None
    course_mode: str = CourseMode.COMPLETE.value
    detailed_log: bool = False
    fast_mode: bool = False

    def set_password(self, password: Optional[str]) -> None:
        self.password_b64 = _encode_password(password) if password else None

    def get_password(self) -> Optional[str]:
        return _decode_password(self.password_b64)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "url": self.url,
            "username": self.username,
            "user_data_dir": self.user_data_dir,
            "remember_me": self.remember_me,
            "headless": self.headless,
            "use_chrome_profile": self.use_chrome_profile,
            "after_play": self.after_play,
            "buffer": self.buffer,
            "slow_mo": self.slow_mo,
            "diagnose": self.diagnose,
            "course_mode": self.course_mode,
            "detailed_log": self.detailed_log,
            "fast_mode": self.fast_mode,
        }
        if self.start_chapter is not None:
            data["start_chapter"] = self.start_chapter
        if self.password_b64:
            data["password_b64"] = self.password_b64
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "PersistentSettings":
        start_chapter = data.get("start_chapter")
        if isinstance(start_chapter, str):
            try:
                start_chapter = int(start_chapter)
            except ValueError:
                start_chapter = None
        elif not isinstance(start_chapter, int):
            start_chapter = None
        password_raw = data.get("password_b64")
        password_b64 = str(password_raw) if isinstance(password_raw, str) and password_raw else None

        return cls(
            url=str(data.get("url", "")),
            username=str(data.get("username", "")),
            user_data_dir=str(data.get("user_data_dir", DEFAULT_USER_DATA_DIR)),
            remember_me=bool(data.get("remember_me", True)),
            headless=bool(data.get("headless", False)),
            use_chrome_profile=bool(data.get("use_chrome_profile", True)),
            after_play=int(data.get("after_play", DEFAULTS.after_play)),
            buffer=int(data.get("buffer", DEFAULTS.buffer)),
            slow_mo=int(data.get("slow_mo", DEFAULTS.slow_mo)),
            diagnose=bool(data.get("diagnose", False)),
            start_chapter=start_chapter,
            password_b64=password_b64,
            course_mode=str(data.get("course_mode", CourseMode.COMPLETE.value)),
            detailed_log=bool(data.get("detailed_log", False)),
            fast_mode=bool(data.get("fast_mode", False)),
        )


def _ensure_config_dir() -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover - filesystem errors are non-critical
        pass


def load_persistent_settings() -> PersistentSettings:
    """Load persisted GUI/CLI settings from disk."""

    if not CONFIG_FILE.exists():
        return PersistentSettings()
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # pragma: no cover - corrupted file guard
        return PersistentSettings()
    if not isinstance(raw, dict):
        return PersistentSettings()
    return PersistentSettings.from_dict(raw)


def save_persistent_settings(settings: PersistentSettings) -> None:
    """Persist settings to disk."""

    _ensure_config_dir()
    try:
        CONFIG_FILE.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
    except OSError:  # pragma: no cover - filesystem errors are non-critical
        pass


def clear_persistent_settings() -> None:
    """Remove any persisted settings."""

    try:
        CONFIG_FILE.unlink()
    except FileNotFoundError:
        return
    except OSError:  # pragma: no cover - filesystem errors are non-critical
        pass


def keyring_available() -> bool:
    """Return True if a usable keyring backend is available."""

    return keyring is not None


def load_saved_password(username: str) -> Optional[str]:
    if not username or keyring is None:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, username)
    except KeyringError:  # pragma: no cover - backend specific failures
        return None


def save_password(username: str, password: str) -> bool:
    if not username or not password or keyring is None:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, username, password)
        return True
    except KeyringError:  # pragma: no cover - backend specific failures
        return False


def delete_password(username: str) -> None:
    if not username or keyring is None:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, username)
    except KeyringError:  # pragma: no cover - backend specific failures
        return


def _compile_patterns(values: Optional[Sequence[str]]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in values or ())


def parse_selectors(path: Optional[Path]) -> dict[str, str]:
    if not path:
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - CLI guard
        raise SystemExit(f"Impossibile leggere i selettori da {path}: {exc}") from exc
    return {k: str(v) for k, v in raw.items() if isinstance(v, str)}


def parse_arguments(argv: Optional[Sequence[str]] = None) -> RuntimeConfig:
    parser = argparse.ArgumentParser(description="Riproduce automaticamente le lezioni del corso")
    parser.add_argument("--url", default=DEFAULTS.url, help="URL della pagina corso")
    parser.add_argument("--after-play", type=int, default=DEFAULTS.after_play, help="Attesa iniziale dopo il click play")
    parser.add_argument("--buffer", type=int, default=DEFAULTS.buffer, help="Buffer extra dopo la durata nominale")
    parser.add_argument("--max-wait", type=int, default=DEFAULTS.max_wait, help="Tempo massimo per singola lezione")
    parser.add_argument("--stall-timeout", type=float, default=DEFAULTS.stall_timeout, help="Secondi senza progresso prima di forzare il riavvio")
    parser.add_argument("--lesson-attempts", type=int, default=DEFAULTS.max_lesson_attempts, help="Tentativi massimi per la stessa lezione")
    parser.add_argument("--headless", action="store_true", help="Esegue in modalità headless")
    parser.add_argument("--start-chapter", type=int, help="Capitolo di partenza (1-based)")
    parser.add_argument("--end-chapter", type=int, help="Capitolo di termine (1-based)")
    parser.add_argument("--lesson-render-wait", type=float, default=DEFAULTS.lesson_render_wait, help="Attesa per render capitolo")
    parser.add_argument("--log-file", type=Path, help="Scrive i log anche su file")
    parser.add_argument("--progress-threshold", type=int, default=DEFAULTS.progress_threshold, help="Percentuale >= skip")
    parser.add_argument("--slow", type=int, default=DEFAULTS.slow_mo, help="Delay ms tra azioni Playwright")
    parser.add_argument("--user-data-dir", type=Path, help="Cartella profilo Chrome da usare")
    parser.add_argument("--no-chrome-profile", action="store_true", help="Non usare profilo Chrome persistente")
    parser.add_argument("--diagnose", action="store_true", help="Modalità diagnostica (non riproduce, stampa inventario)")
    parser.add_argument("--gui", action="store_true", help="Avvia l'interfaccia grafica")
    parser.add_argument("--whitelist", action="append", default=None, help="Regex titoli da includere")
    parser.add_argument("--blacklist", action="append", default=None, help="Regex titoli da escludere")
    parser.add_argument("--state-file", type=Path, default=DEFAULTS.state_file, help="File stato ripresa")
    parser.add_argument("--selectors-json", type=Path, help="Override selettori in JSON")
    parser.add_argument("--cdp-url", help="Connette a un browser Chrome esistente via CDP")
    parser.add_argument("--username", help="Username della piattaforma")
    parser.add_argument("--password", help="Password della piattaforma (sconsigliato su CLI)")
    parser.add_argument("--remember", dest="remember_me", action="store_true", help="Salva credenziali e preferenze", default=None)
    parser.add_argument(
        "--no-remember",
        dest="remember_me",
        action="store_false",
        help="Non salvare credenziali e preferenze",
        default=None,
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in CourseMode],
        help="Modalità di esecuzione (complete, courses, quizzes)",
        default=None,
    )
    parser.add_argument(
        "--detailed-log",
        dest="detailed_log",
        action="store_true",
        help="Abilita log dettagliato",
        default=None,
    )
    parser.add_argument(
        "--no-detailed-log",
        dest="detailed_log",
        action="store_false",
        help="Disabilita il log dettagliato",
        default=None,
    )
    parser.add_argument(
        "--fast-mode",
        dest="fast_mode",
        action="store_true",
        help="Riduce i tempi di attesa durante i quiz",
        default=None,
    )
    parser.add_argument(
        "--no-fast-mode",
        dest="fast_mode",
        action="store_false",
        help="Disattiva la modalità veloce per i quiz",
        default=None,
    )

    args = parser.parse_args(argv)

    whitelist = _compile_patterns(args.whitelist)
    blacklist = _compile_patterns(args.blacklist)

    selectors = parse_selectors(args.selectors_json)

    settings = load_persistent_settings()

    url = args.url
    if url == DEFAULTS.url and settings.url:
        url = settings.url

    username = args.username or (settings.username or None)
    remember_me = settings.remember_me if args.remember_me is None else args.remember_me
    mode_value = args.mode or settings.course_mode or CourseMode.COMPLETE.value
    try:
        course_mode = CourseMode(mode_value)
    except ValueError:
        course_mode = CourseMode.COMPLETE
    detailed_log = settings.detailed_log if args.detailed_log is None else args.detailed_log
    fast_mode = settings.fast_mode if args.fast_mode is None else args.fast_mode
    password = args.password
    if not password and username:
        password = load_saved_password(username)
        if not password:
            password = settings.get_password()

    start_chapter = args.start_chapter
    if start_chapter is None:
        start_chapter = settings.start_chapter

    headless = settings.headless or args.headless

    use_chrome_profile = not args.no_chrome_profile
    if not args.no_chrome_profile:
        use_chrome_profile = settings.use_chrome_profile

    user_data_dir: Optional[Path]
    if args.user_data_dir is not None:
        user_data_dir = args.user_data_dir
    else:
        user_data_dir = Path(settings.user_data_dir).expanduser() if settings.user_data_dir else DEFAULT_USER_DATA_DIR

    after_play = args.after_play if args.after_play != DEFAULTS.after_play else settings.after_play
    buffer = args.buffer if args.buffer != DEFAULTS.buffer else settings.buffer
    slow = max(0, args.slow)
    if args.slow == DEFAULTS.slow_mo:
        slow = settings.slow_mo
    diagnose = args.diagnose or settings.diagnose

    config = RuntimeConfig(
        url=url,
        username=username,
        password=password,
        remember_me=remember_me,
        after_play=after_play,
        buffer=buffer,
        max_wait=args.max_wait,
        stall_timeout=max(args.stall_timeout, 0),
        max_lesson_attempts=max(1, args.lesson_attempts),
        headless=headless,
        start_chapter=start_chapter,
        end_chapter=args.end_chapter,
        lesson_render_wait=args.lesson_render_wait,
        log_file=args.log_file,
        progress_threshold=args.progress_threshold,
        slow_mo=slow,
        user_data_dir=user_data_dir,
        use_chrome_profile=use_chrome_profile,
        diagnose=diagnose,
        course_mode=course_mode,
        detailed_log=bool(detailed_log),
        fast_mode=bool(fast_mode),
        whitelist=whitelist,
        blacklist=blacklist,
        state_file=args.state_file,
        selectors_json=args.selectors_json,
        selector_overrides=selectors,
        use_gui=args.gui,
        cdp_url=args.cdp_url,
    )

    return config


def ensure_url(config: RuntimeConfig, *, prompt: bool = True) -> RuntimeConfig:
    if config.url and not config.url.lower().startswith("http"):
        raise SystemExit("Specificare un URL valido (deve iniziare con http)")
    if config.url != DEFAULTS.url:
        return config.with_overrides(url=DEFAULTS.url)
    if config.url == DEFAULTS.url and prompt:
        return config
    return config
