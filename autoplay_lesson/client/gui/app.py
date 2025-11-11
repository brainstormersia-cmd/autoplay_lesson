"""DarkPegaso CustomTkinter application shell."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.core.bot_controller import BotController
from autoplay_lesson.client.core.config_manager import ConfigManager
from autoplay_lesson.client.gui import styles
from autoplay_lesson.client.gui.components.config_panel import ConfigPanel
from autoplay_lesson.client.gui.components.dashboard import Dashboard
from autoplay_lesson.client.gui.components.footer import Footer
from autoplay_lesson.client.gui.components.header import Header
from autoplay_lesson.client.gui.components.help_panel import HelpPanel
from autoplay_lesson.client.gui.components.sidebar import Sidebar
from autoplay_lesson.client.gui.components.status_panel import StatusPanel
from autoplay_lesson.client.version import VERSION as APP_VERSION


class DarkPegasoApp(ctk.CTk):
    """Main window orchestrating the different sections."""

    VERSION = APP_VERSION

    def __init__(self) -> None:
        super().__init__()
        self.title("DarkPegaso Control Center")
        self.geometry("1200x720")
        self.minsize(1100, 640)
        ctk.set_appearance_mode("dark")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._header = Header(self, version=self.VERSION)
        self._header.grid(row=0, column=0, columnspan=2, sticky="ew")

        sections = (
            {"id": "dashboard", "label": "Dashboard", "icon": "🏠"},
            {"id": "config", "label": "Configurazione", "icon": "⚙️"},
            {"id": "status", "label": "Stato & Log", "icon": "📊"},
            {"id": "help", "label": "Guida Rapida", "icon": "📖"},
        )
        self._sidebar = Sidebar(
            self,
            on_section_change=self._switch_section,
            sections=sections,
        )
        self._sidebar.grid(row=1, column=0, sticky="nsw")

        self._content = ctk.CTkFrame(self, fg_color=styles.palette.background_primary)
        self._content.grid(row=1, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._dashboard = Dashboard(self._content)
        self._config = ConfigPanel(self._content)
        self._status = StatusPanel(self._content)
        self._help = HelpPanel(self._content)

        self._panels = {
            "dashboard": self._dashboard,
            "config": self._config,
            "status": self._status,
            "help": self._help,
        }
        for panel in self._panels.values():
            panel.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
            panel.grid_remove()

        self._footer = Footer(self)
        self._footer.grid(row=2, column=0, columnspan=2, sticky="ew")

        self._config.set_save_command(self._save_config)
        self._dashboard.control_card.configure_command(self._toggle_bot)
        self.bind("<<darkpegaso-exit>>", lambda _event: self.destroy())

        self._bot = BotController(self._handle_bot_log, self._handle_bot_progress)
        self._load_config()
        self._switch_section("dashboard")

    def _switch_section(self, section_id: str) -> None:
        for identifier, panel in self._panels.items():
            if identifier == section_id:
                panel.grid()
            else:
                panel.grid_remove()
        self._sidebar.select(section_id)

    def _save_config(self) -> None:
        ConfigManager.save(
            username=self._config.username_var.get(),
            password=self._config.password_var.get(),
            remember_me=self._config.remember_var.get(),
            course_mode=self._config.mode_var.get(),
            speed=self._config.speed_var.get(),
            verbose=self._config.verbose_var.get(),
            skip_pdf=self._config.skip_pdf_var.get(),
            sound=self._config.sound_var.get(),
        )
        self._dashboard.log_console.append("✓ Configurazione salvata", category="success")

    def _load_config(self) -> None:
        config = ConfigManager.load()
        if not config:
            return
        self._config.username_var.set(config.get("username", ""))
        self._config.password_var.set(config.get("password", ""))
        self._config.remember_var.set(config.get("remember_me", False))
        self._config.mode_var.set(config.get("course_mode", "COMPLETE"))
        self._config.speed_var.set(config.get("speed", 2.5))
        self._config.verbose_var.set(config.get("verbose", True))
        self._config.skip_pdf_var.set(config.get("skip_pdf", False))
        self._config.sound_var.set(config.get("sound", False))

    def _toggle_bot(self) -> None:
        if self._bot.is_running:
            self._bot.stop()
            self._dashboard.control_card.set_running(False)
            self._dashboard.log_console.append("⏹️ Bot fermato", category="warning")
        else:
            settings = ConfigManager.load()
            if not settings.get("username") or not settings.get("password"):
                self._dashboard.log_console.append("✗ Inserire credenziali valide", category="error")
                return
            self._bot.start(settings)
            self._dashboard.control_card.set_running(True)
            self._dashboard.log_console.append("🚀 Bot avviato", category="action")

    def _handle_bot_log(self, message: str, level: str = "default") -> None:
        self._dashboard.log_console.append(message, category=level)
        self._status.log_console.append(message, category=level)

    def _handle_bot_progress(self, value: float, eta: str | None = None) -> None:
        self._dashboard.progress_bar.set_progress(value, eta_text=eta)


__all__ = ["DarkPegasoApp"]
