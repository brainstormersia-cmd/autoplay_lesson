"""Entry point for the DarkPegaso desktop client."""

from __future__ import annotations

import uuid

from autoplay_lesson.client.core.api_client import APIClient
from autoplay_lesson.client.core.config_manager import ConfigManager
from autoplay_lesson.client.core.license_manager import LicenseManager
from autoplay_lesson.client.gui.app import DarkPegasoApp


def initialise_license() -> None:
    api = APIClient()
    ok, tier = LicenseManager.validate_on_startup(api)
    if not ok:
        return
    config = ConfigManager.load()
    config.setdefault("license_tier", tier or "free")
    ConfigManager.save(**config)


def run() -> None:
    ConfigManager.save(hwid=str(uuid.uuid5(uuid.NAMESPACE_DNS, "darkpegaso")))
    initialise_license()
    app = DarkPegasoApp()
    app.mainloop()


if __name__ == "__main__":
    run()
