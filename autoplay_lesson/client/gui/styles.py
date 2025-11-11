"""Centralised styling constants for the DarkPegaso desktop shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class Palette:
    """Primary palette extracted from the DarkPegaso design brief."""

    background_primary: str = "#0B0B0F"
    background_secondary: str = "#16161D"
    accent_primary: str = "#6A00FF"
    accent_secondary: str = "#3D00FF"
    success: str = "#00FF88"
    error: str = "#FF0055"
    warning: str = "#FFB800"
    text_primary: str = "#FFFFFF"
    text_secondary: str = "#B4B4C8"
    glow: str = "#6A00FF"


@dataclass(frozen=True)
class Typography:
    """Font declarations used across the application."""

    primary: Tuple[str, int] = ("Inter", 14)
    primary_semibold: Tuple[str, int] = ("Inter SemiBold", 16)
    section: Tuple[str, int] = ("Inter SemiBold", 18)
    title: Tuple[str, int] = ("Inter SemiBold", 24)
    console: Tuple[str, int] = ("JetBrains Mono", 12)


palette = Palette()
typography = Typography()
