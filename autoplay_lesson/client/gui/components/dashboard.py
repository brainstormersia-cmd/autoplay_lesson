"""Dashboard page implementation with neon glass aesthetic."""

from __future__ import annotations

from collections import deque
import tkinter as tk
from typing import Deque, Iterable, Tuple

import customtkinter as ctk

from autoplay_lesson.client.gui import styles
from autoplay_lesson.client.gui.components.log_console import LogConsole
from autoplay_lesson.client.gui.components.notification_stack import NotificationStack
from autoplay_lesson.client.gui.components.progress_bar import GlowProgressBar


class Dashboard(ctk.CTkFrame):
    """Main dashboard card layout."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color="transparent")
        self.columnconfigure(0, weight=1)

        self._status_card = _StatusCard(self)
        self._status_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))

        self._control = _ControlCard(self)
        self._control.grid(row=1, column=0, sticky="ew", pady=(0, 16))

        self._progress = GlowProgressBar(self)
        self._progress.grid(row=2, column=0, sticky="ew", pady=(0, 16))

        self._metrics = _MetricsBoard(self)
        self._metrics.grid(row=3, column=0, sticky="ew", pady=(0, 16))

        self._notifications = NotificationStack(self)
        self._notifications.grid(row=4, column=0, sticky="ew", pady=(0, 16))

        self._log = LogConsole(self)
        self._log.grid(row=5, column=0, sticky="nsew")
        self.rowconfigure(5, weight=1)

        self._log.add_listener(self._status_card.push_micro_log)
        self._log.add_listener(self._metrics.push_activity)

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

    def update_metrics(self, *, lessons: int, quizzes: int, total_seconds: float) -> None:
        """Refresh the real-time analytics tiles and charts."""

        self._metrics.update(lessons=lessons, quizzes=quizzes, total_seconds=total_seconds)


class _StatusCard(ctk.CTkFrame):
    """Summarises bot status, counters, and a compact activity feed."""

    MAX_MICRO_LOGS = 4

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_glass,
            corner_radius=24,
            border_width=1,
            border_color=styles.palette.outline,
        )
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(20, 6))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        title = ctk.CTkLabel(
            header,
            text="⚡ Stato Bot",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="w")

        self._session_clock = ctk.CTkLabel(
            header,
            text="Runtime · 00:00",
            font=styles.typography.numeric_small,
            text_color=styles.palette.text_secondary,
            anchor="e",
        )
        self._session_clock.grid(row=0, column=1, sticky="e")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 24))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)

        indicator_row = ctk.CTkFrame(left, fg_color="transparent")
        indicator_row.grid(row=0, column=0, sticky="ew")
        indicator_row.grid_columnconfigure(1, weight=1)

        self._indicator = ctk.CTkFrame(
            indicator_row,
            width=16,
            height=16,
            corner_radius=8,
            fg_color=styles.palette.success,
        )
        self._indicator.grid(row=0, column=0, rowspan=2, padx=(0, 12), pady=(4, 0))
        self._indicator.grid_propagate(False)

        self._indicator_label = ctk.CTkLabel(
            indicator_row,
            text="Pronto",
            font=styles.typography.primary_semibold,
            text_color=styles.palette.text_primary,
            anchor="w",
        )
        self._indicator_label.grid(row=0, column=1, sticky="w")

        self._last_run = ctk.CTkLabel(
            indicator_row,
            text="Ultimo evento: --",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        self._last_run.grid(row=1, column=1, sticky="w")

        metrics_row = ctk.CTkFrame(left, fg_color="transparent")
        metrics_row.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        metrics_row.grid_columnconfigure((0, 1), weight=1, uniform="metrics")

        self._lessons_metric = _StatusMetric(metrics_row, "🎓", "Lezioni completate")
        self._lessons_metric.grid(row=0, column=0, padx=(0, 12), sticky="ew")

        self._quizzes_metric = _StatusMetric(metrics_row, "🧠", "Quiz superati")
        self._quizzes_metric.grid(row=0, column=1, sticky="ew")

        right = ctk.CTkFrame(body, fg_color=styles.palette.background_glass_alt, corner_radius=18)
        right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        right.grid_rowconfigure((0, 1, 2, 3), weight=0)
        right.grid_columnconfigure(0, weight=1)

        micro_title = ctk.CTkLabel(
            right,
            text="Terminal Feed",
            font=styles.typography.primary_semibold,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        micro_title.grid(row=0, column=0, sticky="ew", pady=(16, 8))

        self._micro_labels: list[ctk.CTkLabel] = []
        self._micro_buffer: Deque[Tuple[str, str]] = deque(maxlen=self.MAX_MICRO_LOGS)
        for index in range(self.MAX_MICRO_LOGS):
            label = ctk.CTkLabel(
                right,
                text="",
                font=styles.typography.console,
                text_color=styles.palette.text_secondary,
                anchor="w",
                padx=16,
            )
            label.grid(row=index + 1, column=0, sticky="ew", pady=(0 if index else 0, 6))
            self._micro_labels.append(label)

    def update_status(self, label: str, color: str) -> None:
        self._indicator_label.configure(text=label)
        self._indicator.configure(fg_color=color)

    def update_counts(self, *, lessons: int, quizzes: int) -> None:
        self._lessons_metric.set_value(f"{lessons}")
        self._quizzes_metric.set_value(f"{quizzes}")

    def update_last_run(self, text: str) -> None:
        self._last_run.configure(text=text)

    def update_duration(self, text: str) -> None:
        self._session_clock.configure(text=f"Runtime · {text}")

    def push_micro_log(self, message: str, category: str) -> None:
        """Display a compact log history inside the status card."""

        color = styles.LOG_COLORS.get(category, styles.LOG_COLORS["default"])
        trimmed = message.strip().replace("\n", " ")
        if len(trimmed) > 72:
            trimmed = f"{trimmed[:69]}…"
        self._micro_buffer.appendleft((trimmed, color))
        for label, entry in zip(self._micro_labels, self._micro_buffer):
            text, fg = entry
            label.configure(text=text, text_color=fg)
        for index in range(len(self._micro_buffer), len(self._micro_labels)):
            self._micro_labels[index].configure(text="", text_color=styles.palette.text_secondary)


class _StatusMetric(ctk.CTkFrame):
    """Miniature metric badge used inside the status card."""

    def __init__(self, master: ctk.CTkBaseClass, icon: str, label: str) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_glass_alt,
            corner_radius=16,
            border_width=1,
            border_color=styles.palette.soft_outline,
        )
        self.columnconfigure(1, weight=1)

        icon_label = ctk.CTkLabel(
            self,
            text=icon,
            font=styles.typography.section,
            text_color=styles.palette.accent_secondary,
            width=40,
            anchor="center",
        )
        icon_label.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=12)

        text_label = ctk.CTkLabel(
            self,
            text=label,
            font=styles.typography.caption,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        text_label.grid(row=0, column=1, sticky="w", pady=(12, 0))

        self._value = ctk.CTkLabel(
            self,
            text="0",
            font=styles.typography.numeric,
            text_color=styles.palette.text_primary,
            anchor="w",
        )
        self._value.grid(row=1, column=1, sticky="w", pady=(0, 12))

    def set_value(self, value: str) -> None:
        self._value.configure(text=value)


class _MetricsBoard(ctk.CTkFrame):
    """Neon inspired analytics dashboard with sparkline and badges."""

    HISTORY_LENGTH = 18

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_glass,
            corner_radius=24,
            border_width=1,
            border_color=styles.palette.outline,
        )
        self.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="📊 Real-time Dashboard",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=24,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(20, 6))

        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", padx=24)
        metrics.grid_columnconfigure((0, 1, 2), weight=1, uniform="metrics")

        self._lessons_tile = _MetricTile(metrics, "Lezioni", "Completate", styles.palette.accent_primary)
        self._lessons_tile.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        self._quizzes_tile = _MetricTile(metrics, "Quiz", "Superati", styles.palette.accent_secondary)
        self._quizzes_tile.grid(row=0, column=1, sticky="ew", padx=12)

        self._time_tile = _MetricTile(metrics, "Tempo", "Totale", styles.palette.accent_magenta)
        self._time_tile.grid(row=0, column=2, sticky="ew", padx=(12, 0))

        chart_frame = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_glass_alt,
            corner_radius=20,
            border_width=1,
            border_color=styles.palette.soft_outline,
        )
        chart_frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(18, 16))
        chart_frame.grid_columnconfigure(0, weight=1)
        chart_frame.grid_rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            chart_frame,
            background=styles.palette.canvas_background,
            highlightthickness=0,
            borderwidth=0,
            height=160,
        )
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self._canvas.bind("<Configure>", lambda _event: self._draw_chart())

        self._activity = ctk.CTkLabel(
            self,
            text="Ultimo aggiornamento: --",
            font=styles.typography.caption,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=24,
        )
        self._activity.grid(row=3, column=0, sticky="ew", pady=(0, 20))

        self._lesson_history: Deque[int] = deque(maxlen=self.HISTORY_LENGTH)
        self._quiz_history: Deque[int] = deque(maxlen=self.HISTORY_LENGTH)

    def update(self, *, lessons: int, quizzes: int, total_seconds: float) -> None:
        self._lessons_tile.set_value(f"{lessons}")
        self._quizzes_tile.set_value(f"{quizzes}")
        self._time_tile.set_value(self._format_duration(total_seconds))
        self._lesson_history.append(lessons)
        self._quiz_history.append(quizzes)
        self._draw_chart()

    def push_activity(self, message: str, category: str) -> None:
        colour = styles.LOG_COLORS.get(category, styles.LOG_COLORS["default"])
        trimmed = message.strip().replace("\n", " ")
        if len(trimmed) > 90:
            trimmed = f"{trimmed[:87]}…"
        self._activity.configure(text=f"Ultimo aggiornamento: {trimmed}", text_color=colour)

    def _draw_chart(self) -> None:
        if not self._canvas.winfo_exists():
            return
        width = max(int(self._canvas.winfo_width()), 300)
        height = max(int(self._canvas.winfo_height()), 160)
        margin = 22
        self._canvas.delete("all")

        # Grid
        grid_color = styles.blend(styles.palette.text_muted, styles.palette.canvas_background, 0.5)
        for step in range(4):
            y = margin + step * (height - margin * 2) / 3
            self._canvas.create_line(
                margin,
                y,
                width - margin,
                y,
                fill=grid_color,
                width=1,
            )

        max_value = max(self._lesson_history or [1])
        max_value = max(max_value, max(self._quiz_history or [1]) * 1.2)
        if max_value <= 0:
            max_value = 1

        def normalise(values: Iterable[int]) -> list[Tuple[float, float]]:
            values_list = list(values)
            if not values_list:
                return []
            step = (width - margin * 2) / max(1, len(values_list) - 1)
            points: list[Tuple[float, float]] = []
            for index, value in enumerate(values_list):
                x = margin + index * step
                proportion = value / max_value
                y = height - margin - proportion * (height - margin * 2)
                points.append((x, y))
            return points

        lesson_points = normalise(self._lesson_history)
        quiz_points = normalise(self._quiz_history)

        # Quizzes as glowing bars
        for (x, y), value in zip(quiz_points, self._quiz_history):
            bar_top = y
            bar_bottom = height - margin
            self._canvas.create_rectangle(
                x - 6,
                bar_top,
                x + 6,
                bar_bottom,
                fill=styles.blend(styles.palette.accent_secondary, "#000000", 0.2),
                outline="",
            )
            self._canvas.create_rectangle(
                x - 4,
                bar_top,
                x + 4,
                bar_bottom,
                fill=styles.palette.accent_secondary,
                outline="",
            )

        if len(lesson_points) >= 2:
            flattened = [coord for point in lesson_points for coord in point]
            self._canvas.create_line(
                *flattened,
                fill=styles.palette.accent_primary,
                width=3,
                smooth=True,
            )
            for x, y in lesson_points:
                self._canvas.create_oval(
                    x - 4,
                    y - 4,
                    x + 4,
                    y + 4,
                    fill=styles.palette.glow_primary,
                    outline="",
                )

    @staticmethod
    def _format_duration(total_seconds: float) -> str:
        total_seconds = max(0, int(total_seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


class _MetricTile(ctk.CTkFrame):
    """Small glass tile showing a key metric."""

    def __init__(self, master: ctk.CTkBaseClass, label: str, subtitle: str, accent: str) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_glass_alt,
            corner_radius=18,
            border_width=1,
            border_color=styles.blend(accent, styles.palette.soft_outline, 0.6),
        )
        self.columnconfigure(0, weight=1)

        self._label = ctk.CTkLabel(
            self,
            text=label.upper(),
            font=styles.typography.caption,
            text_color=accent,
            anchor="w",
            padx=16,
        )
        self._label.grid(row=0, column=0, sticky="ew", pady=(14, 0))

        self._value = ctk.CTkLabel(
            self,
            text="0",
            font=styles.typography.numeric,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        self._value.grid(row=1, column=0, sticky="ew")

        self._subtitle = ctk.CTkLabel(
            self,
            text=subtitle,
            font=styles.typography.caption,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        self._subtitle.grid(row=2, column=0, sticky="ew", pady=(0, 14))

    def set_value(self, value: str) -> None:
        self._value.configure(text=value)


class _ControlCard(ctk.CTkFrame):
    """Neon primary control for starting/stopping the automation."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_glass,
            corner_radius=24,
            border_width=1,
            border_color=styles.palette.outline,
        )
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)

        self._hint = ctk.CTkLabel(
            self,
            text=(
                "Gestisci le automazioni intelligenti di DarkPegaso."
                " Ricorda di configurare il corso e le credenziali prima di avviare."
            ),
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            justify="left",
            padx=24,
            wraplength=520,
        )
        self._hint.grid(row=0, column=0, sticky="nw", padx=(24, 12), pady=24)

        self._button = ctk.CTkButton(
            self,
            text="🚀 AVVIA BOT",
            font=styles.typography.primary_semibold,
            height=66,
            corner_radius=20,
            fg_color=styles.palette.accent_magenta,
            hover_color=styles.blend(styles.palette.accent_magenta, styles.palette.accent_secondary, 0.3),
            text_color=styles.palette.text_primary,
            border_width=0,
            width=250,
        )
        self._button.grid(row=0, column=1, sticky="ne", padx=(0, 24), pady=24)

        self._course_label = ctk.CTkLabel(
            self,
            text="Corso collegato: nessun link",
            font=styles.typography.numeric_small,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=24,
        )
        self._course_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 22))

    def configure_command(self, command) -> None:
        self._button.configure(command=command)

    def set_running(self, running: bool) -> None:
        if running:
            self._button.configure(
                text="⏹ FERMA BOT",
                fg_color=styles.palette.error,
                hover_color=styles.blend(styles.palette.error, styles.palette.warning, 0.3),
            )
        else:
            self._button.configure(
                text="🚀 AVVIA BOT",
                fg_color=styles.palette.accent_magenta,
                hover_color=styles.blend(styles.palette.accent_magenta, styles.palette.accent_secondary, 0.3),
            )

    def set_course(self, url: str) -> None:
        text = url.strip()
        if not text:
            display = "nessun link"
        else:
            display = text if len(text) <= 68 else f"{text[:65]}…"
        self._course_label.configure(text=f"Corso collegato: {display}")


__all__ = ["Dashboard"]
