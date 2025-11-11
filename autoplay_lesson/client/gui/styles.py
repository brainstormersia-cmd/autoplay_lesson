"""Centralised styling constants and helpers for the DarkPegaso Control Center."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from PIL import Image, ImageDraw, ImageFilter

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class Palette:
    """Palette extracted from the DarkPegaso dopaminergic design brief."""

    background_primary: str = "#0B0F1A"
    background_layer: str = "#101630"
    background_glass: str = "#141E33"
    background_glass_alt: str = "#101A2B"
    overlay_glow: str = "#1A2442"
    accent_primary: str = "#4A6CFF"
    accent_secondary: str = "#A64DFF"
    accent_magenta: str = "#FF3BAA"
    success: str = "#43D17B"
    warning: str = "#FFB84A"
    error: str = "#FF4C60"
    info: str = "#4A6CFF"
    text_primary: str = "#E9ECF8"
    text_secondary: str = "#B0B8D0"
    text_muted: str = "#6D7896"
    outline: str = "#1D2B4D"
    soft_outline: str = "#172441"
    glow_primary: str = "#5374FF"
    glow_secondary: str = "#7F5BFF"
    badge_background: str = "#162346"
    canvas_background: str = "#0F1626"


@dataclass(frozen=True)
class Typography:
    """Font declarations used across the application."""

    primary: Tuple[str, int] = ("Outfit", 14)
    primary_semibold: Tuple[str, int] = ("Outfit SemiBold", 16)
    section: Tuple[str, int] = ("Outfit SemiBold", 22)
    title: Tuple[str, int] = ("Outfit SemiBold", 28)
    hero: Tuple[str, int] = ("Outfit SemiBold", 32)
    caption: Tuple[str, int] = ("Outfit", 12)
    numeric: Tuple[str, int] = ("JetBrains Mono", 16)
    numeric_small: Tuple[str, int] = ("JetBrains Mono", 13)
    console: Tuple[str, int] = ("JetBrains Mono", 12)


def hex_to_rgb(value: str) -> Color:
    """Convert a hex string (``#RRGGBB``) into an RGB tuple."""

    value = value.lstrip("#")
    length = len(value)
    if length not in {6, 8}:
        raise ValueError(f"Unexpected hex colour format: {value!r}")
    rgb = tuple(int(value[i : i + 2], 16) for i in range(0, 6, 2))
    return rgb  # type: ignore[return-value]


def rgba(color: str, alpha: int) -> Tuple[int, int, int, int]:
    """Return a RGBA tuple from ``color`` and an alpha value between 0-255."""

    r, g, b = hex_to_rgb(color)
    return (r, g, b, max(0, min(255, alpha)))


def blend(color_a: str, color_b: str, factor: float) -> str:
    """Linearly blend ``color_a`` towards ``color_b`` by ``factor`` (0-1)."""

    ra, ga, ba = hex_to_rgb(color_a)
    rb, gb, bb = hex_to_rgb(color_b)
    factor = max(0.0, min(1.0, factor))
    r = int(ra + (rb - ra) * factor)
    g = int(ga + (gb - ga) * factor)
    b = int(ba + (bb - ba) * factor)
    return f"#{r:02X}{g:02X}{b:02X}"


def build_background_image(size: Tuple[int, int]) -> Image.Image:
    """Generate a blurred neon background with radial glows."""

    width, height = size
    base = Image.new("RGBA", size, palette.background_primary)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Primary bottom glow
    bottom_radius = int(max(width, height) * 0.9)
    bbox = [
        width // 2 - bottom_radius,
        int(height * 0.45),
        width // 2 + bottom_radius,
        height + bottom_radius,
    ]
    draw.ellipse(bbox, fill=rgba(palette.accent_secondary, 170))

    # Top-right accent glow
    accent_radius = int(min(width, height) * 0.65)
    accent_bbox = [
        width - accent_radius * 2,
        -accent_radius // 2,
        width + accent_radius,
        accent_radius * 1,
    ]
    draw.ellipse(accent_bbox, fill=rgba(palette.accent_primary, 150))

    # Side gradient glow
    side_radius = int(min(width, height) * 0.9)
    side_bbox = [
        -side_radius,
        int(height * 0.2),
        side_radius,
        int(height * 1.2),
    ]
    draw.ellipse(side_bbox, fill=rgba(palette.accent_magenta, 120))

    blurred = overlay.filter(ImageFilter.GaussianBlur(radius=220))
    combined = Image.alpha_composite(base, blurred)
    return combined


def glow_cycle(colors: Iterable[str] | None = None) -> Tuple[str, ...]:
    """Return a tuple of glow colours for animated highlights."""

    if colors is None:
        colors = (
            palette.accent_primary,
            palette.glow_primary,
            palette.accent_secondary,
            palette.accent_magenta,
        )
    return tuple(colors)


palette = Palette()
typography = Typography()

LOG_COLORS = {
    "success": palette.success,
    "error": palette.error,
    "warning": palette.warning,
    "action": palette.accent_secondary,
    "info": palette.accent_primary,
    "debug": palette.text_muted,
    "critical": palette.error,
    "default": palette.text_secondary,
}


__all__ = [
    "Color",
    "LOG_COLORS",
    "blend",
    "build_background_image",
    "glow_cycle",
    "hex_to_rgb",
    "palette",
    "rgba",
    "typography",
]
