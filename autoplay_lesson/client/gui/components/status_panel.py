"""Advanced status view."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles
from autoplay_lesson.client.gui.components.log_console import LogConsole


class StatusPanel(ctk.CTkFrame):
    """Detailed statistics, lesson info, and consolidated logs."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color="transparent")
        self.columnconfigure(0, weight=1)

        stats_card = _StatsCard(self)
        stats_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.stats_card = stats_card

        lesson_card = _LessonCard(self)
        lesson_card.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        self.lesson_card = lesson_card

        log_card = ctk.CTkFrame(self, fg_color=styles.palette.background_secondary, corner_radius=12)
        log_card.grid(row=2, column=0, sticky="nsew")
        log_card.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ctk.CTkLabel(
            log_card,
            text="📜 Log Completo",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        header.grid(row=0, column=0, sticky="ew", pady=(16, 8))

        self.log_console = LogConsole(log_card)
        self.log_console.grid(row=1, column=0, sticky="nsew")
        log_card.rowconfigure(1, weight=1)

        self.export_button = ctk.CTkButton(
            log_card,
            text="Esporta",
            fg_color=styles.palette.accent_primary,
        )
        self.export_button.place(relx=0.95, rely=0.08, anchor="ne")


class _StatsCard(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=12)
        self.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="📊 Statistiche Sessione",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(16, 8))

        self._lessons = self._line("Lezioni completate", "0 / 0", row=1)
        self._quizzes = self._line("Quiz superati", "0 / 0", row=2)
        self._total_time = self._line("Tempo totale", "--", row=3)
        self._avg_time = self._line("Tempo medio per lezione", "--", row=4)
        self._last_activity = self._line("Ultima attività", "--", row=5)

    def _line(self, label: str, value: str, *, row: int) -> ctk.CTkLabel:
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        container.columnconfigure(1, weight=1)

        label_widget = ctk.CTkLabel(
            container,
            text=f"{label}:",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        label_widget.grid(row=0, column=0, sticky="w")

        value_widget = ctk.CTkLabel(
            container,
            text=value,
            font=styles.typography.primary,
            text_color=styles.palette.text_primary,
            anchor="e",
        )
        value_widget.grid(row=0, column=1, sticky="e")
        return value_widget

    def update_values(
        self,
        *,
        lessons: str,
        quizzes: str,
        total_time: str,
        average_time: str,
        last_activity: str,
    ) -> None:
        self._lessons.configure(text=lessons)
        self._quizzes.configure(text=quizzes)
        self._total_time.configure(text=total_time)
        self._avg_time.configure(text=average_time)
        self._last_activity.configure(text=last_activity)


class _LessonCard(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=12)
        self.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="🎯 Lezione Attuale",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(16, 8))

        self._lesson_title = ctk.CTkLabel(
            self,
            text="Titolo: --",
            font=styles.typography.primary,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        self._lesson_title.grid(row=1, column=0, sticky="ew")

        self._progress = ctk.CTkLabel(
            self,
            text="Progresso: 0%",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        self._progress.grid(row=2, column=0, sticky="ew", pady=4)

        self._phase = ctk.CTkLabel(
            self,
            text="Fase: --",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        self._phase.grid(row=3, column=0, sticky="ew", pady=(0, 16))

    def update(self, *, title: str, progress: str, phase: str) -> None:
        self._lesson_title.configure(text=f"Titolo: {title}")
        self._progress.configure(text=f"Progresso: {progress}")
        self._phase.configure(text=f"Fase: {phase}")
