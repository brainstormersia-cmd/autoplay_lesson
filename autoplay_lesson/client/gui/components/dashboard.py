"""Dashboard page implementation."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles
from autoplay_lesson.client.gui.components.log_console import LogConsole
from autoplay_lesson.client.gui.components.notification_stack import NotificationStack
from autoplay_lesson.client.gui.components.progress_bar import GlowProgressBar


class Dashboard(ctk.CTkFrame):
    """Main dashboard card layout."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            fg_color="transparent",
        )
        self.columnconfigure(0, weight=1)

        self._status_card = _StatusCard(self)
        self._status_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        self._control = _ControlCard(self)
        self._control.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        self._progress = GlowProgressBar(self)
        self._progress.grid(row=2, column=0, sticky="ew", pady=(0, 14))

        self._notifications = NotificationStack(self)
        self._notifications.grid(row=3, column=0, sticky="ew", pady=(0, 14))

        self._log = LogConsole(self)
        self._log.grid(row=4, column=0, sticky="nsew")
        self.rowconfigure(4, weight=1)

    @property
    def log_console(self) -> LogConsole:
        return self._log

    @property
    def progress_bar(self) -> GlowProgressBar:
        return self._progress

    @property
    def control_card(self) -> "_ControlCard":
        return self._control

    @property
    def status_card(self) -> "_StatusCard":
        return self._status_card

    @property
    def notifications(self) -> NotificationStack:
        return self._notifications


class _StatusCard(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=16)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            self,
            text="⚡ Stato Bot",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=20,
        )
        title.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(18, 6))

        self._indicator = ctk.CTkLabel(
            self,
            text="● Pronto",
            font=styles.typography.primary_semibold,
            text_color=styles.palette.success,
            anchor="w",
            padx=20,
        )
        self._indicator.grid(row=1, column=0, sticky="ew")

        self._lessons = ctk.CTkLabel(
            self,
            text="Lezioni completate: 0",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=20,
        )
        self._lessons.grid(row=2, column=0, sticky="ew", pady=(0, 4))

        self._quizzes = ctk.CTkLabel(
            self,
            text="Quiz superati: 0",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=20,
        )
        self._quizzes.grid(row=3, column=0, sticky="ew", pady=(0, 4))

        self._last_run = ctk.CTkLabel(
            self,
            text="Ultimo evento: --",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=20,
        )
        self._last_run.grid(row=4, column=0, sticky="ew", pady=(0, 18))

        highlight = ctk.CTkLabel(
            self,
            text="Sessione attuale",
            font=styles.typography.primary_semibold,
            text_color=styles.palette.text_primary,
            anchor="e",
            padx=20,
        )
        highlight.grid(row=1, column=1, rowspan=1, sticky="ne")

        self._session_clock = ctk.CTkLabel(
            self,
            text="Durata: 00:00",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="e",
            padx=20,
        )
        self._session_clock.grid(row=2, column=1, sticky="ne")

    def update_status(self, label: str, color: str) -> None:
        self._indicator.configure(text=label, text_color=color)

    def update_counts(self, *, lessons: int, quizzes: int) -> None:
        self._lessons.configure(text=f"Lezioni completate: {lessons}")
        self._quizzes.configure(text=f"Quiz superati: {quizzes}")

    def update_last_run(self, text: str) -> None:
        self._last_run.configure(text=text)

    def update_duration(self, text: str) -> None:
        self._session_clock.configure(text=f"Durata: {text}")


class _ControlCard(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=16)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)

        self._hint = ctk.CTkLabel(
            self,
            text=(
                "Verifica che link, credenziali e capitolo iniziale siano impostati."
                " Premi Avvia per far partire DarkPegaso."
            ),
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            justify="left",
            padx=20,
            wraplength=520,
        )
        self._hint.grid(row=0, column=0, sticky="nw", padx=20, pady=20)

        self._button = ctk.CTkButton(
            self,
            text="🚀  AVVIA AUTOMAZIONE",
            font=styles.typography.primary_semibold,
            height=60,
            corner_radius=18,
            fg_color=styles.palette.accent_primary,
            hover_color=styles.palette.accent_secondary,
            width=240,
        )
        self._button.grid(row=0, column=1, sticky="ne", padx=(0, 20), pady=20)

        self._course_label = ctk.CTkLabel(
            self,
            text="Corso collegato: nessun link impostato",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=20,
        )
        self._course_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 20))

    def configure_command(self, command) -> None:
        self._button.configure(command=command)

    def set_running(self, running: bool) -> None:
        if running:
            self._button.configure(text="⏹️  FERMA BOT", fg_color=styles.palette.error)
        else:
            self._button.configure(text="🚀  AVVIA AUTOMAZIONE", fg_color=styles.palette.accent_primary)

    def set_course(self, url: str) -> None:
        text = url.strip()
        if not text:
            display = "nessun link impostato"
        else:
            display = text if len(text) <= 70 else text[:67] + "…"
        self._course_label.configure(text=f"Corso collegato: {display}")


__all__ = ["Dashboard"]
