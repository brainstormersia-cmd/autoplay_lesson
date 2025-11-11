"""Compatibility module exposing the launch_gui helper."""

from __future__ import annotations

from autoplay_lesson.client.main import run


def launch_gui() -> None:
    """Launch the CustomTkinter DarkPegaso client."""

    run()
