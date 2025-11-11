"""Animated progress indicator with neon glow."""

from __future__ import annotations

import time
from typing import Iterable, Optional

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class GlowProgressBar(ctk.CTkFrame):
    """Progress bar with smooth animated updates."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_glass,
            corner_radius=24,
            border_width=1,
            border_color=styles.palette.outline,
        )
        self.columnconfigure(0, weight=1)

        self._label = ctk.CTkLabel(
            self,
            text="Progresso lezione · 0%",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=24,
        )
        self._label.grid(row=0, column=0, sticky="ew", pady=(20, 10))

        bar_holder = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_glass_alt,
            corner_radius=16,
            border_width=1,
            border_color=styles.palette.soft_outline,
        )
        bar_holder.grid(row=1, column=0, sticky="ew", padx=24)
        bar_holder.grid_columnconfigure(0, weight=1)

        self._progress = ctk.CTkProgressBar(
            bar_holder,
            progress_color=(styles.palette.accent_primary, styles.palette.accent_secondary),
            fg_color=styles.palette.background_primary,
            height=22,
            corner_radius=12,
            border_width=0,
        )
        self._progress.grid(row=0, column=0, sticky="ew", padx=10, pady=12)

        self._time = ctk.CTkLabel(
            self,
            text="Tempo stimato: --",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=24,
        )
        self._time.grid(row=2, column=0, sticky="ew", pady=(10, 20))

        self._current_value = 0.0
        self._active = False
        self._pulse_id: Optional[str] = None
        self._cycle = styles.glow_cycle()
        self._cycle_index = 0

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
        self._label.configure(text=f"Progresso lezione · {int(value * 100)}%")
        if eta_text:
            self._time.configure(text=f"Tempo stimato: {eta_text}")

    def set_caption(self, caption: str) -> None:
        self._time.configure(text=caption)

    def set_active(self, active: bool) -> None:
        """Toggle the pulsing glow animation."""

        if self._active == active:
            return
        self._active = active
        if active:
            self._animate_glow()
        elif self._pulse_id is not None:
            self.after_cancel(self._pulse_id)
            self._pulse_id = None
            self._progress.configure(progress_color=(styles.palette.accent_primary, styles.palette.accent_secondary))

    def set_cycle(self, colors: Iterable[str]) -> None:
        sequence = tuple(colors)
        if sequence:
            self._cycle = sequence
            self._cycle_index = 0

    def _animate_glow(self) -> None:
        if not self._active:
            return
        color = self._cycle[self._cycle_index % len(self._cycle)]
        secondary = styles.blend(color, styles.palette.accent_secondary, 0.4)
        self._progress.configure(progress_color=(color, secondary))
        self._cycle_index += 1
        self._pulse_id = self.after(480, self._animate_glow)


__all__ = ["GlowProgressBar"]
