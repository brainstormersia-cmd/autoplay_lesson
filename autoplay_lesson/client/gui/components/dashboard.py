"""Dashboard page implementation."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles
from autoplay_lesson.client.gui.components.log_console import LogConsole
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
        self._status_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self._control = _ControlCard(self)
        self._control.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        self._progress = GlowProgressBar(self)
        self._progress.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        self._log = LogConsole(self)
        self._log.grid(row=3, column=0, sticky="nsew")
        self.rowconfigure(3, weight=1)

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


class _StatusCard(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=12)
        self.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="⚡ Stato Bot",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(16, 8))

        self._indicator = ctk.CTkLabel(
            self,
            text="● Pronto",
            font=styles.typography.primary,
            text_color=styles.palette.success,
            anchor="w",
            padx=16,
        )
        self._indicator.grid(row=1, column=0, sticky="ew")

        self._last_run = ctk.CTkLabel(
            self,
            text="Ultima esecuzione: --",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        self._last_run.grid(row=2, column=0, sticky="ew", pady=4)

        self._stats = ctk.CTkLabel(
            self,
            text="Lezioni completate oggi: 0",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        self._stats.grid(row=3, column=0, sticky="ew", pady=(0, 16))

    def update_status(self, label: str, color: str) -> None:
        self._indicator.configure(text=label, text_color=color)

    def update_last_run(self, text: str) -> None:
        self._last_run.configure(text=text)

    def update_stats(self, text: str) -> None:
        self._stats.configure(text=text)


class _ControlCard(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=12)
        self.columnconfigure(0, weight=1)

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)

        self._hint = ctk.CTkLabel(
            self,
            text=(
                "Verifica che link, username e password siano compilati poi avvia il bot."
            ),
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            justify="left",
            padx=16,
            wraplength=520,
        )
        self._hint.grid(row=0, column=0, sticky="nw", padx=16, pady=16)

        self._button = ctk.CTkButton(
            self,
            text="🚀  AVVIA AUTOMAZIONE",
            font=styles.typography.primary_semibold,
            height=56,
            corner_radius=16,
            fg_color=styles.palette.accent_primary,
            hover_color=styles.palette.accent_secondary,
            width=220,
        )
        self._button.grid(row=0, column=1, sticky="ne", padx=(0, 16), pady=16)

        self._course_label = ctk.CTkLabel(
            self,
            text="Corso collegato: nessun link impostato",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        self._course_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 16))

    def configure_command(self, command) -> None:
        self._button.configure(command=command)

    def set_running(self, running: bool) -> None:
        if running:
            self._button.configure(text="⏹️  FERMA BOT")
        else:
            self._button.configure(text="🚀  AVVIA AUTOMAZIONE")

    def set_course(self, url: str) -> None:
        text = url.strip()
        if not text:
            display = "nessun link impostato"
        else:
            display = text if len(text) <= 70 else text[:67] + "…"
        self._course_label.configure(text=f"Corso collegato: {display}")
