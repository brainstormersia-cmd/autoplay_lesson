"""Telemetry helpers for DarkPegaso."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from autoplay_lesson.client.core.api_client import APIClient


class Telemetry:
    """Utility wrapper to ship structured telemetry events."""

    def __init__(self, api_client: APIClient) -> None:
        self._api = api_client

    def send_event(self, event_type: str, metadata: Dict[str, Any]) -> None:
        payload = {"timestamp": datetime.utcnow().isoformat(), **metadata}
        self._api.send_event(event_type, payload)
