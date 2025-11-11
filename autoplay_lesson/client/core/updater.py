"""Self-update helpers for the DarkPegaso desktop client."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import requests


class Updater:
    """Download and stage new releases from the backend CDN."""

    def __init__(self, download_dir: Optional[Path] = None) -> None:
        self._download_dir = download_dir or Path(tempfile.gettempdir()) / "darkpegaso"
        self._download_dir.mkdir(parents=True, exist_ok=True)

    def download(self, url: str) -> Path:
        target = self._download_dir / Path(url).name
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        target.write_bytes(response.content)
        return target

    def install(self, package: Path) -> None:  # pragma: no cover - platform dependent
        os.startfile(str(package))
