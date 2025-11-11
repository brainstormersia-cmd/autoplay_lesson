"""Header bar with branding and status highlights."""

from __future__ import annotations

import datetime as _dt
from typing import Iterable, Optional

import customtkinter as ctk

from autoplay_lesson.client.assets import get_logo_image
from autoplay_lesson.client.gui import styles


class Header(ctk.CTkFrame):
    """Futuristic HUD inspired top bar with live automation indicator."""

    def __init__(self, master: ctk.CTkBaseClass, *, version: str) -> None:
        super().__init__(master, fg_color="transparent")
        self.columnconfigure(0, weight=1)

        container = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_glass,
            corner_radius=28,
            border_width=1,
            border_color=styles.palette.outline,
        )
        container.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 12))
        container.grid_columnconfigure(1, weight=1)
        container.grid_columnconfigure(2, weight=0)

        logo_image = get_logo_image((64, 64))
        self._logo_photo = ctk.CTkImage(
            light_image=logo_image,
            dark_image=logo_image,
            size=(64, 64),
        )

        logo_holder = ctk.CTkFrame(
            container,
            fg_color=styles.palette.overlay_glow,
            corner_radius=32,
            border_width=1,
            border_color=styles.palette.soft_outline,
            width=84,
            height=84,
        )
        logo_holder.grid(row=0, column=0, rowspan=2, padx=(24, 18), pady=20, sticky="w")
        logo_holder.grid_propagate(False)

        logo_label = ctk.CTkLabel(logo_holder, text="", image=self._logo_photo)
        logo_label.place(relx=0.5, rely=0.5, anchor="center")

        title_area = ctk.CTkFrame(container, fg_color="transparent")
        title_area.grid(row=0, column=1, rowspan=2, sticky="nsew")
        title_area.grid_columnconfigure(0, weight=1)

        self._title = ctk.CTkLabel(
            title_area,
            text="⚡ DarkPegaso Control Center",
            font=styles.typography.hero,
            text_color=styles.palette.text_primary,
            anchor="w",
        )
        self._title.grid(row=0, column=0, sticky="w")

        self._reflection = ctk.CTkLabel(
            title_area,
            text="DarkPegaso Holographic HUD",
            font=styles.typography.caption,
            text_color=styles.blend(styles.palette.text_secondary, styles.palette.accent_secondary, 0.5),
            anchor="w",
        )
        self._reflection.grid(row=1, column=0, sticky="w")

        self._status = ctk.CTkLabel(
            title_area,
            text="Sistema inizializzato · {:%H:%M:%S}".format(_dt.datetime.now()),
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        self._status.grid(row=2, column=0, sticky="w", pady=(6, 0))

        self._live_indicator = _LiveIndicator(container)
        self._live_indicator.grid(row=0, column=2, sticky="ne", padx=(12, 24), pady=(20, 4))

        right_stack = ctk.CTkFrame(container, fg_color="transparent")
        right_stack.grid(row=1, column=2, sticky="ne", padx=(12, 24), pady=(0, 24))
        right_stack.grid_columnconfigure(0, weight=1)

        self._timer_label = ctk.CTkLabel(
            right_stack,
            text="Sessione · 00:00",
            font=styles.typography.numeric,
            text_color=styles.palette.text_primary,
            anchor="e",
        )
        self._timer_label.grid(row=0, column=0, sticky="e")

        self._version = ctk.CTkLabel(
            right_stack,
            text=f"v{version} · Free Edition",
            font=styles.typography.caption,
            text_color=styles.palette.text_secondary,
            anchor="e",
        )
        self._version.grid(row=1, column=0, sticky="e", pady=(4, 0))

    def set_status_text(self, message: str) -> None:
        """Update the header's status line with timestamp."""

        timestamp = _dt.datetime.now().strftime("%H:%M:%S")
        self._status.configure(text=f"{message} · {timestamp}")

    def update_session_time(self, text: str) -> None:
        """Refresh the HUD session timer."""

        self._timer_label.configure(text=f"Sessione · {text}")

    def set_live_state(self, running: bool) -> None:
        """Toggle the live automation indicator animation."""

        self._live_indicator.set_active(running)

    def set_glow_cycle(self, colors: Optional[Iterable[str]]) -> None:
        """Override the glow animation colours for the live indicator."""

        if colors is None:
            self._live_indicator.set_cycle(styles.glow_cycle())
        else:
            self._live_indicator.set_cycle(tuple(colors))


class _LiveIndicator(ctk.CTkFrame):
    """Pulsating indicator describing live automation status."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color="transparent")
        self.columnconfigure(1, weight=1)

        self._halo = ctk.CTkFrame(
            self,
            width=24,
            height=24,
            corner_radius=12,
            fg_color=styles.palette.overlay_glow,
            border_width=1,
            border_color=styles.palette.accent_secondary,
        )
        self._halo.grid(row=0, column=0, rowspan=2, sticky="w")
        self._halo.grid_propagate(False)

        self._dot = ctk.CTkFrame(
            self._halo,
            width=14,
            height=14,
            corner_radius=7,
            fg_color=styles.palette.warning,
        )
        self._dot.place(relx=0.5, rely=0.5, anchor="center")

        self._label = ctk.CTkLabel(
            self,
            text="Live Automation",
            font=styles.typography.primary_semibold,
            text_color=styles.palette.text_primary,
            anchor="w",
        )
        self._label.grid(row=0, column=1, sticky="w", padx=(12, 0))

        self._hint = ctk.CTkLabel(
            self,
            text="Monitoraggio in tempo reale",
            font=styles.typography.caption,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        self._hint.grid(row=1, column=1, sticky="w", padx=(12, 0))

        self._cycle = styles.glow_cycle()
        self._cycle_index = 0
        self._active = False
        self._after_id: Optional[str] = None

    def set_cycle(self, colors: Iterable[str]) -> None:
        sequence = tuple(colors)
        if not sequence:
            sequence = styles.glow_cycle()
        self._cycle = sequence
        self._cycle_index = 0

    def set_active(self, active: bool) -> None:
        if active == self._active:
            return
        self._active = active
        if active:
            self._label.configure(text_color=styles.palette.text_primary)
            self._hint.configure(text="Automazione attiva", text_color=styles.palette.text_secondary)
            self._animate()
        else:
            self._label.configure(text_color=styles.palette.text_secondary)
            self._hint.configure(text="In attesa di avvio", text_color=styles.palette.text_muted)
            self._dot.configure(fg_color=styles.palette.text_muted)
            self._halo.configure(border_color=styles.palette.soft_outline)
            if self._after_id is not None:
                self.after_cancel(self._after_id)
                self._after_id = None

    def _animate(self) -> None:
        if not self._active:
            return
        color = self._cycle[self._cycle_index % len(self._cycle)]
        halo_color = styles.blend(color, styles.palette.overlay_glow, 0.5)
        self._dot.configure(fg_color=color)
        self._halo.configure(border_color=color, fg_color=halo_color)
        self._cycle_index += 1
        self._after_id = self.after(520, self._animate)


__all__ = ["Header"]
