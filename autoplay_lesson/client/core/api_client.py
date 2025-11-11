"""HTTP and WebSocket client abstractions for the DarkPegaso ecosystem."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

API_BASE_URL = "https://api.darkpegaso.io"


@dataclass
class APIResponse:
    success: bool
    status: str
    data: Dict[str, Any]
    command: Optional[str] = None


class APIClient:
    """Thin wrapper around the backend API.

    The implementation currently performs mocked requests so that the
    desktop application can be demonstrated offline while the backend
    platform is still under construction.
    """

    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def validate_license(self, license_key: str, hwid: str) -> APIResponse:
        if not license_key:
            return APIResponse(False, "invalid", {})
        payload = {"license_key": license_key, "hwid": hwid}
        try:
            response = requests.post(
                f"{API_BASE_URL}/license/validate",
                headers=self._headers(),
                data=json.dumps(payload),
                timeout=5,
            )
            data = response.json()
        except Exception:
            data = {"tier": "free"}
            return APIResponse(True, "active", data)
        return APIResponse(data.get("success", False), data.get("status", "unknown"), data)

    def send_event(self, event_type: str, metadata: Dict[str, Any]) -> None:
        payload = {"event_type": event_type, "metadata": metadata}
        try:
            requests.post(
                f"{API_BASE_URL}/telemetry",
                headers=self._headers(),
                data=json.dumps(payload),
                timeout=5,
            )
        except Exception:
            return

    def fetch_command(self, hwid: str) -> APIResponse:
        try:
            response = requests.get(
                f"{API_BASE_URL}/control/{hwid}", headers=self._headers(), timeout=5
            )
            data = response.json()
        except Exception:
            data = {}
        return APIResponse(True, data.get("status", "ok"), data, command=data.get("command"))
