"""DarkPegaso CustomTkinter application shell."""

from __future__ import annotations

import re
import time

import customtkinter as ctk

from autoplay_lesson.client.core.bot_controller import BotController
from autoplay_lesson.client.core.config_manager import ConfigManager
from autoplay_lesson.client.gui import styles
from autoplay_lesson.client.gui.components.config_panel import ConfigPanel
from autoplay_lesson.client.gui.components.dashboard import Dashboard
from autoplay_lesson.client.gui.components.footer import Footer
from autoplay_lesson.client.gui.components.header import Header
from autoplay_lesson.client.version import VERSION as APP_VERSION


class DarkPegasoApp(ctk.CTk):
    """Main window orchestrating the different sections."""

    VERSION = APP_VERSION

    def __init__(self) -> None:
        super().__init__()
        self.title("DarkPegaso Control Center")
        self.geometry("1280x780")
        self.minsize(1180, 680)
        ctk.set_appearance_mode("dark")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._header = Header(self, version=self.VERSION)
        self._header.grid(row=0, column=0, sticky="ew")

        self._content = ctk.CTkScrollableFrame(
            self,
            fg_color=styles.palette.background_primary,
            corner_radius=0,
        )
        self._content.grid(row=1, column=0, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_columnconfigure(1, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

        self._dashboard = Dashboard(self._content)
        self._dashboard.grid(row=0, column=0, sticky="nsew", padx=(28, 16), pady=24)

        self._config = ConfigPanel(self._content)
        self._config.grid(row=0, column=1, sticky="nsew", padx=(16, 28), pady=24)

        self._footer = Footer(self)
        self._footer.grid(row=2, column=0, sticky="ew")

        self._config.set_save_command(self._save_config)
        self._dashboard.control_card.configure_command(self._toggle_bot)
        self.bind("<<darkpegaso-exit>>", lambda _event: self.destroy())

        self._bot = BotController(self._handle_bot_log, self._handle_bot_progress)
        self._session_start: float | None = None
        self._lessons_completed = 0
        self._quizzes_completed = 0

        self._load_config()
        self._switch_idle_state()

    def _switch_idle_state(self) -> None:
        self._dashboard.status_card.update_status("● Pronto", styles.palette.success)
        self._dashboard.status_card.update_counts(lessons=self._lessons_completed, quizzes=self._quizzes_completed)
        self._dashboard.status_card.update_duration("00:00")
        self._dashboard.status_card.update_last_run("Ultimo evento: --")

    def _save_config(self) -> None:
        url_value = self._config.url_var.get().strip()
        start_value = self._config.start_chapter_var.get().strip()
        start_chapter, error = self._parse_start_chapter(start_value)
        if error:
            self._dashboard.log_console.append(error, category="warning")
        ConfigManager.save(
            url=url_value,
            username=self._config.username_var.get(),
            password=self._config.password_var.get(),
            remember_me=self._config.remember_var.get(),
            course_mode=self._config.mode_var.get(),
            verbose=self._config.verbose_var.get(),
            skip_pdf=self._config.skip_pdf_var.get(),
            sound=self._config.sound_var.get(),
            start_chapter=start_chapter,
        )
        self._dashboard.control_card.set_course(url_value)
        self._dashboard.log_console.append("✓ Configurazione salvata", category="success")

    def _load_config(self) -> None:
        config = ConfigManager.load()
        if not config:
            return
        self._config.url_var.set(config.get("url", ""))
        self._config.username_var.set(config.get("username", ""))
        self._config.password_var.set(config.get("password", ""))
        self._config.remember_var.set(config.get("remember_me", False))
        self._config.mode_var.set(config.get("course_mode", "COMPLETE"))
        self._config.verbose_var.set(config.get("verbose", True))
        self._config.skip_pdf_var.set(config.get("skip_pdf", False))
        self._config.sound_var.set(config.get("sound", False))
        if config.get("start_chapter") is not None:
            self._config.start_chapter_var.set(str(config.get("start_chapter")))
        self._dashboard.control_card.set_course(config.get("url", ""))

    def _toggle_bot(self) -> None:
        if self._bot.is_running:
            self._bot.stop()
            self._dashboard.control_card.set_running(False)
            self._dashboard.log_console.append("⏹️ Bot fermato", category="warning")
            self._dashboard.notifications.push("Bot fermato", "Automazione interrotta manualmente", level="warning")
            self._header.set_status_text("Automazione in pausa")
            return

        current_values = {
            "url": self._config.url_var.get().strip(),
            "username": self._config.username_var.get(),
            "password": self._config.password_var.get(),
            "remember_me": self._config.remember_var.get(),
            "course_mode": self._config.mode_var.get(),
            "verbose": self._config.verbose_var.get(),
            "skip_pdf": self._config.skip_pdf_var.get(),
            "sound": self._config.sound_var.get(),
        }

        if not current_values["url"]:
            self._dashboard.log_console.append(
                "✗ Incolla il link completo del corso nella Configurazione",
                category="error",
            )
            self._dashboard.notifications.push(
                "URL mancante",
                "Inserisci il link del corso prima di avviare il bot",
                level="warning",
            )
            return
        if not current_values["username"] or not current_values["password"]:
            self._dashboard.log_console.append(
                "✗ Inserisci username e password del portale",
                category="error",
            )
            self._dashboard.notifications.push(
                "Credenziali mancanti",
                "Fornisci username e password del portale Pegaso",
                level="warning",
            )
            return

        start_value = self._config.start_chapter_var.get().strip()
        start_chapter, error = self._parse_start_chapter(start_value)
        if error:
            self._dashboard.log_console.append(error, category="warning")
        current_values["start_chapter"] = start_chapter

        ConfigManager.save(**current_values)
        self._dashboard.control_card.set_course(current_values["url"])
        settings = ConfigManager.load()
        self._reset_session_metrics()
        self._bot.start(settings)
        self._dashboard.control_card.set_running(True)
        self._dashboard.status_card.update_status("● In esecuzione", styles.palette.accent_primary)
        self._dashboard.log_console.append("🚀 Bot avviato", category="action")
        self._dashboard.notifications.push("Bot in esecuzione", "DarkPegaso ha iniziato l'automazione", level="info")
        self._header.set_status_text("Automazione in corso")

    def _reset_session_metrics(self) -> None:
        self._session_start = time.monotonic()
        self._lessons_completed = 0
        self._quizzes_completed = 0
        self._dashboard.status_card.update_counts(lessons=0, quizzes=0)
        self._dashboard.status_card.update_duration("00:00")

    def _handle_bot_log(self, message: str, level: str = "default") -> None:
        category = self._extract_category(message)
        self._dashboard.log_console.append(message, category=category)
        self._dashboard.status_card.update_last_run(self._trim_message(message))
        if self._session_start is not None:
            duration = self._format_duration(time.monotonic() - self._session_start)
            self._dashboard.status_card.update_duration(duration)
        self._header.set_status_text(self._trim_message(message))

        lowered = message.lower()
        if "lezione completata" in lowered:
            self._lessons_completed += 1
            self._dashboard.status_card.update_counts(
                lessons=self._lessons_completed, quizzes=self._quizzes_completed
            )
            self._dashboard.notifications.push(
                "Lezione completata",
                self._trim_message(message),
                level="success",
            )
        elif "quiz" in lowered and "corrette" in lowered and "quiz" in lowered:
            self._quizzes_completed += 1
            self._dashboard.status_card.update_counts(
                lessons=self._lessons_completed, quizzes=self._quizzes_completed
            )
            self._dashboard.notifications.push(
                "Quiz completato",
                self._trim_message(message),
                level="success",
            )
        elif "watchdog" in lowered or "timeout" in lowered:
            self._dashboard.notifications.push(
                "Attenzione",
                self._trim_message(message),
                level="warning",
            )
        elif "errore" in lowered or category in {"error", "critical"}:
            self._dashboard.notifications.push(
                "Errore",
                self._trim_message(message),
                level="error",
            )

        if "==== avvio autoplay" in lowered:
            self._reset_session_metrics()
            self._dashboard.notifications.push(
                "Sessione avviata",
                "L'autoplay è stato avviato",
                level="info",
            )
        if not self._bot.is_running and self._session_start is not None:
            self._dashboard.control_card.set_running(False)
            self._dashboard.status_card.update_status("● Pronto", styles.palette.success)
            self._header.set_status_text("Automazione completata")
            self._dashboard.notifications.push("Sessione terminata", "Il bot è tornato in attesa", level="info")
            self._session_start = None

    def _handle_bot_progress(self, value: float, eta: str | None = None) -> None:
        if eta:
            self._dashboard.progress_bar.set_caption(f"Tempo stimato: {eta}")
        self._dashboard.progress_bar.set_progress(value, eta_text=eta)

    @staticmethod
    def _trim_message(message: str) -> str:
        if "]" in message:
            return message.split("]", 1)[-1].strip()
        return message.strip()

    @staticmethod
    def _extract_category(message: str) -> str:
        match = re.search(r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]", message)
        if not match:
            return "info"
        level = match.group(1).upper()
        mapping = {
            "DEBUG": "debug",
            "INFO": "info",
            "WARNING": "warning",
            "ERROR": "error",
            "CRITICAL": "critical",
        }
        return mapping.get(level, "info")

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def _parse_start_chapter(value: str) -> tuple[int | None, str | None]:
        if not value:
            return None, None
        try:
            parsed = int(value)
        except ValueError:
            return None, "⚠️ Capitolo iniziale non valido: inserisci un numero intero"
        if parsed <= 0:
            return None, "⚠️ Capitolo iniziale deve essere maggiore di zero"
        return parsed, None


__all__ = ["DarkPegasoApp"]
