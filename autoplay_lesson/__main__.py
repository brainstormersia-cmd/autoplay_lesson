"""CLI entrypoint for the autoplay lesson runner."""
from __future__ import annotations

import asyncio
import sys

from .config import ensure_url, parse_arguments
from .runner import run_from_cli


def main(argv: list[str] | None = None) -> None:
    config = parse_arguments(argv)
    if config.use_gui:
        from .gui import launch_gui  # Lazy import to avoid Tk dependency when unused
        launch_gui()
        return
    config = ensure_url(config)
    asyncio.run(run_from_cli(config))


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
