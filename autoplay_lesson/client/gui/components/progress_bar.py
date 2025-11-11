"""Animated progress indicator."""

from __future__ import annotations

import time
from typing import Callable

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class GlowProgressBar(ctk.CTkFrame):
    """Progress bar with smooth animated updates."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_secondary,
            corner_radius=12,
        )
        self.columnconfigure(0, weight=1)

        self._label = ctk.CTkLabel(
            self,
            text="Progresso Lezione: 0%",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        self._label.grid(row=0, column=0, sticky="ew", pady=(16, 8))

        self._progress = ctk.CTkProgressBar(
            self,
            progress_color=styles.palette.accent_primary,
            fg_color=styles.palette.background_primary,
            height=20,
            border_color=styles.palette.accent_secondary,
            corner_radius=10,
        )
        self._progress.grid(row=1, column=0, sticky="ew", padx=16)

        self._time = ctk.CTkLabel(
            self,
            text="Tempo stimato: --",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        self._time.grid(row=2, column=0, sticky="ew", pady=(8, 16))

        self._current_value = 0.0

    def set_progress(self, value: float, *, eta_text: str | None = None, duration_ms: int = 300) -> None:
        """Animate the bar to the requested percentage."""

        value = max(0.0, min(1.0, value))
        start = self._current_value
        delta = value - start
        if duration_ms <= 0 or abs(delta) < 1e-6:
            self._progress.set(value)
        else:
            steps = max(1, duration_ms // 16)
            for idx in range(1, steps + 1):
                fraction = idx / steps
                eased = start + delta * fraction
                self._progress.set(eased)
                self.update_idletasks()
                time.sleep(duration_ms / steps / 1000.0)
        self._current_value = value
        self._label.configure(text=f"Progresso Lezione: {int(value * 100)}%")
        if eta_text:
            self._time.configure(text=f"Tempo stimato: {eta_text}")

    def set_caption(self, caption: str) -> None:
        self._time.configure(text=caption)
