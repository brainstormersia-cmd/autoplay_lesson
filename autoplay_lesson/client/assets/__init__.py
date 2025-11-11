"""Utilities for managing DarkPegaso client assets."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Tuple

from PIL import Image, ImageDraw

DEFAULT_LOGO_NAME = "darkpegaso_logo.png"
PACKAGE_DIR = Path(__file__).resolve().parent
CLIENT_DIR = PACKAGE_DIR.parent
PACKAGE_ROOT = CLIENT_DIR.parent
REPO_ROOT = PACKAGE_ROOT.parent


def _candidate_logo_paths() -> Iterable[Path]:
    """Yield possible locations for the DarkPegaso PNG logo."""

    env_path = os.getenv("DARKPEGASO_LOGO")
    if env_path:
        yield Path(env_path)

    yield PACKAGE_DIR / DEFAULT_LOGO_NAME
    yield REPO_ROOT / "assets" / DEFAULT_LOGO_NAME
    yield Path.cwd() / "assets" / DEFAULT_LOGO_NAME


@lru_cache(maxsize=1)
def _resolve_logo_path() -> Optional[Path]:
    for path in _candidate_logo_paths():
        if path.is_file():
            return path
    return None


def _create_placeholder_image(size: Tuple[int, int]) -> Image.Image:
    """Generate a fallback neon-style logo if no PNG is provided."""

    width, height = size
    background = Image.new("RGBA", (width, height), "#0B0B0F")
    overlay = Image.new("RGBA", (width, height))
    overlay_draw = ImageDraw.Draw(overlay)

    # Neon radial glow
    glow_radius = min(width, height) // 2
    for i in range(glow_radius, 0, -1):
        alpha = int(200 * (i / glow_radius) ** 2)
        color = (106, 0, 255, alpha)
        bbox = [
            width // 2 - i,
            height // 2 - i,
            width // 2 + i,
            height // 2 + i,
        ]
        overlay_draw.ellipse(bbox, fill=color)

    # Stylised pegasus silhouette
    body_color = (0, 255, 136, 230)
    wing_color = (61, 0, 255, 230)
    outline_color = (255, 255, 255, 160)

    draw = ImageDraw.Draw(overlay)
    body = [
        (width * 0.30, height * 0.65),
        (width * 0.55, height * 0.55),
        (width * 0.70, height * 0.70),
        (width * 0.48, height * 0.80),
    ]
    draw.polygon(body, fill=body_color, outline=outline_color)

    wing = [
        (width * 0.45, height * 0.30),
        (width * 0.70, height * 0.20),
        (width * 0.80, height * 0.45),
        (width * 0.60, height * 0.50),
    ]
    draw.polygon(wing, fill=wing_color, outline=outline_color)

    head = [
        (width * 0.25, height * 0.50),
        (width * 0.35, height * 0.45),
        (width * 0.38, height * 0.52),
        (width * 0.30, height * 0.56),
    ]
    draw.polygon(head, fill=body_color, outline=outline_color)

    combined = Image.alpha_composite(background, overlay)
    return combined


@lru_cache(maxsize=8)
def get_logo_image(size: Tuple[int, int] | None = None) -> Image.Image:
    """Return the configured PNG logo as a Pillow image.

    If no external PNG is found, generate a glowing placeholder that
    respects the DarkPegaso palette.
    """

    source = _resolve_logo_path()
    if source:
        with Image.open(source) as image:
            image = image.convert("RGBA")
            if size:
                return image.resize(size, Image.LANCZOS)
            return image.copy()

    size = size or (256, 256)
    return _create_placeholder_image(size)


def export_logo(target: Path, size: Tuple[int, int] | None = None) -> Path:
    """Write the logo (or placeholder) to ``target`` and return the path."""

    target.parent.mkdir(parents=True, exist_ok=True)
    image = get_logo_image(size)
    image.save(target, format="PNG")
    return target


__all__ = ["DEFAULT_LOGO_NAME", "export_logo", "get_logo_image"]
