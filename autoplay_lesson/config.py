"""Configuration utilities for the autoplay lesson runner."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional, Sequence


DURATION_PATTERN = re.compile(r"\b(?:(?P<h>\d{1,2})\s*:\s*)?(?P<m>\d{1,2})\s*:\s*(?P<s>\d{2})\b")

DEFAULT_USER_DATA_DIR = Path("~/.config/autoplay-lesson/chrome-profile").expanduser()


@dataclass(slots=True)
class RuntimeConfig:
    """Container for CLI or GUI supplied runtime configuration."""

    url: str
    after_play: int = 20
    buffer: int = 5
    max_wait: int = 3600
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

    whitelist: tuple[re.Pattern[str], ...] = field(default_factory=tuple)
    blacklist: tuple[re.Pattern[str], ...] = field(default_factory=tuple)

    state_file: Path = Path(".state.json")
    max_retries: int = 3
    retry_backoff: float = 2.0
    retry_base_delay: float = 1.0
    click_timeout: float = 3.0
    navigation_timeout: float = 60.0
    page_timeout: float = 30.0

    def to_summary(self) -> str:
        """Return a multi-line summary describing this configuration."""

        whitelist = ", ".join(p.pattern for p in self.whitelist) or "<none>"
        blacklist = ", ".join(p.pattern for p in self.blacklist) or "<none>"
        summary = (
            "Configurazione corrente:\n"
            f"  URL: {self.url}\n"
            f"  Profilo Chrome: {'attivo' if self.use_chrome_profile and self.user_data_dir else 'disattivato'}\n"
            f"  Headless: {self.headless}\n"
            f"  Slow motion: {self.slow_mo}ms\n"
            f"  Attesa post play: {self.after_play}s\n"
            f"  Buffer aggiuntivo: {self.buffer}s\n"
            f"  Tempo massimo per lezione: {self.max_wait}s\n"
            f"  Start chapter: {self.start_chapter or '-'}\n"
            f"  End chapter: {self.end_chapter or '-'}\n"
            f"  Render wait capitolo: {self.lesson_render_wait}s\n"
            f"  Soglia completamento: {self.progress_threshold}%\n"
            f"  File log: {self.log_file or 'solo console'}\n"
            f"  File stato: {self.state_file}\n"
            f"  Diagnostica: {self.diagnose}\n"
            f"  Whitelist: {whitelist}\n"
            f"  Blacklist: {blacklist}\n"
        )
        if self.selector_overrides:
            overrides = ", ".join(f"{k}={v}" for k, v in self.selector_overrides.items())
            summary += f"  Override selettori: {overrides}\n"
        return summary

    def chapter_in_scope(self, index: int) -> bool:
        if self.start_chapter is not None and index < self.start_chapter:
            return False
        if self.end_chapter is not None and index > self.end_chapter:
            return False
        return True

    def with_overrides(self, **kwargs) -> "RuntimeConfig":
        return replace(self, **kwargs)


DEFAULTS = RuntimeConfig(url="https://esempio-corso")


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

    args = parser.parse_args(argv)

    whitelist = _compile_patterns(args.whitelist)
    blacklist = _compile_patterns(args.blacklist)

    selectors = parse_selectors(args.selectors_json)

    config = RuntimeConfig(
        url=args.url,
        after_play=args.after_play,
        buffer=args.buffer,
        max_wait=args.max_wait,
        headless=args.headless,
        start_chapter=args.start_chapter,
        end_chapter=args.end_chapter,
        lesson_render_wait=args.lesson_render_wait,
        log_file=args.log_file,
        progress_threshold=args.progress_threshold,
        slow_mo=max(0, args.slow),
        user_data_dir=args.user_data_dir or DEFAULT_USER_DATA_DIR,
        use_chrome_profile=not args.no_chrome_profile,
        diagnose=args.diagnose,
        whitelist=whitelist,
        blacklist=blacklist,
        state_file=args.state_file,
        selectors_json=args.selectors_json,
        selector_overrides=selectors,
        use_gui=args.gui,
    )

    return config


def ensure_url(config: RuntimeConfig, *, prompt: bool = True) -> RuntimeConfig:
    if config.url and not config.url.lower().startswith("http"):
        raise SystemExit("Specificare un URL valido (deve iniziare con http)")
    if config.url == DEFAULTS.url and prompt:
        try:
            entered = input("Inserisci l'URL del corso: ").strip()
        except EOFError as exc:  # pragma: no cover - interattivo
            raise SystemExit("URL non fornito") from exc
        if not entered:
            raise SystemExit("URL non fornito")
        return config.with_overrides(url=entered)
    return config
