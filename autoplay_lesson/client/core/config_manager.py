"""Persist configuration locally for DarkPegaso."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path(os.getenv("DARKPEGASO_CONFIG", "config.json"))


class ConfigManager:
    """Simple JSON-based configuration persistence layer."""

    @staticmethod
    def load() -> Dict[str, Any]:
        if not CONFIG_PATH.exists():
            return {}
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def save(**kwargs: Any) -> None:
        data = ConfigManager.load()
        data.update(kwargs)
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
