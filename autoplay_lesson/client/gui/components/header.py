"""Header component for the DarkPegaso shell."""

from __future__ import annotations

import datetime as _dt

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class Header(ctk.CTkFrame):
    """Top bar with branding and version."""

    def __init__(self, master: ctk.CTkBaseClass, *, version: str) -> None:
        super().__init__(
            master,
            height=60,
            fg_color=styles.palette.background_primary,
        )
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)

        self._title = ctk.CTkLabel(
            self,
            text="🌟 DarkPegaso",
            font=styles.typography.title,
            text_color=styles.palette.text_primary,
        )
        self._title.grid(row=0, column=0, sticky="w", padx=24)

        self._version = ctk.CTkLabel(
            self,
            text=f"v{version} – Free Edition",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
        )
        self._version.grid(row=0, column=1, sticky="e", padx=24)

    def set_status_text(self, message: str) -> None:
        """Update the header's subtitle with a timestamped message."""

        timestamp = _dt.datetime.now().strftime("%H:%M")
        self._version.configure(text=f"{message} · {timestamp}")
