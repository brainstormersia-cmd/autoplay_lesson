"""Banner indicating the current license tier."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class LicenseBanner(ctk.CTkFrame):
    """Small status pill to show the activated tier."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=16)
        self.columnconfigure(0, weight=1)

        self._label = ctk.CTkLabel(
            self,
            text="Licenza: Free",
            font=styles.typography.primary,
            text_color=styles.palette.text_primary,
            padx=12,
            pady=4,
        )
        self._label.grid(row=0, column=0)

    def set_tier(self, tier: str) -> None:
        if tier.lower() == "pro":
            text = "Licenza: Pro"
            color = styles.palette.success
        else:
            text = "Licenza: Free"
            color = styles.palette.accent_primary
        self._label.configure(text=text, text_color=color)
