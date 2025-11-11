"""Header component for the DarkPegaso shell."""

from __future__ import annotations

import datetime as _dt

import customtkinter as ctk

from autoplay_lesson.client.assets import get_logo_image
from autoplay_lesson.client.gui import styles


class Header(ctk.CTkFrame):
    """Top bar with branding and version."""

    def __init__(self, master: ctk.CTkBaseClass, *, version: str) -> None:
        super().__init__(
            master,
            height=60,
            fg_color=styles.palette.header_background,
            border_width=0,
        )
        self.grid_propagate(False)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=0)

        logo_image = get_logo_image((44, 44))
        self._logo_photo = ctk.CTkImage(
            light_image=logo_image,
            dark_image=logo_image,
            size=(44, 44),
        )
        self._logo = ctk.CTkLabel(
            self,
            image=self._logo_photo,
            text="",
        )
        self._logo.grid(row=0, column=0, padx=(24, 12), pady=8, sticky="w")

        title_frame = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        title_frame.grid(row=0, column=1, sticky="w")
        title_frame.columnconfigure(0, weight=1)

        self._title = ctk.CTkLabel(
            title_frame,
            text="DarkPegaso",
            font=styles.typography.title,
            text_color=styles.palette.text_primary,
        )
        self._title.grid(row=0, column=0, sticky="w")

        subtitle = ctk.CTkLabel(
            title_frame,
            text="Control Center",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
        )
        subtitle.grid(row=1, column=0, sticky="w")

        self._version = ctk.CTkLabel(
            self,
            text=f"v{version} – Free Edition",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
        )
        self._version.grid(row=0, column=2, sticky="e", padx=24)

        self._accent = ctk.CTkFrame(
            self,
            height=2,
            fg_color=styles.palette.accent_primary,
        )
        self._accent.grid(row=1, column=0, columnspan=3, sticky="ew")

    def set_status_text(self, message: str) -> None:
        """Update the header's subtitle with a timestamped message."""

        timestamp = _dt.datetime.now().strftime("%H:%M")
        self._version.configure(text=f"{message} · {timestamp}")
