"""License storage and validation."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional, Tuple

from autoplay_lesson.client.core.api_client import APIClient

LICENSE_PATH = Path("license.json")


def _encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


def _decode(value: str) -> str:
    return base64.b64decode(value.encode("utf-8")).decode("utf-8")


class LicenseManager:
    """Simple license persistence with remote validation hooks."""

    @staticmethod
    def load_local_license() -> Tuple[str, str]:
        if not LICENSE_PATH.exists():
            return "", ""
        try:
            payload = json.loads(LICENSE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "", ""
        license_key = _decode(payload.get("license", "")) if payload.get("license") else ""
        hwid = payload.get("hwid", "")
        return license_key, hwid

    @staticmethod
    def save_license(license_key: str, hwid: str) -> None:
        payload = {"license": _encode(license_key), "hwid": hwid}
        LICENSE_PATH.write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def validate_on_startup(api: APIClient) -> Tuple[bool, Optional[str]]:
        license_key, hwid = LicenseManager.load_local_license()
        response = api.validate_license(license_key, hwid)
        if response.status == "active":
            return True, response.data.get("tier", "free")
        if response.status == "suspended":
            return False, None
        if response.status == "expired":
            return False, None
        return bool(response.success), response.data.get("tier")
