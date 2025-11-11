"""Entry point for the DarkPegaso desktop client."""

from __future__ import annotations

import uuid

from autoplay_lesson.client.core.config_manager import ConfigManager
from autoplay_lesson.client.gui.app import DarkPegasoApp


def run() -> None:
    ConfigManager.save(hwid=str(uuid.uuid5(uuid.NAMESPACE_DNS, "darkpegaso")))
    app = DarkPegasoApp()
    app.mainloop()


if __name__ == "__main__":
    run()
