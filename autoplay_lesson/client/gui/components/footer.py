"""Footer for the DarkPegaso shell."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class Footer(ctk.CTkFrame):
    """Bottom bar with attribution text."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            height=40,
            fg_color=styles.palette.background_primary,
        )
        self.grid_propagate(False)

        label = ctk.CTkLabel(
            self,
            text="⚡ Powered by DarkPegaso AI – Free Edition",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
        )
        label.pack(expand=True)
