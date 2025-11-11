"""Footer for the DarkPegaso shell."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class Footer(ctk.CTkFrame):
    """Bottom bar with attribution text and subtle glow."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            height=48,
            fg_color=styles.palette.background_glass,
            border_width=1,
            border_color=styles.palette.soft_outline,
        )
        self.grid_propagate(False)

        container = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        container.pack(expand=True)
        container.grid_columnconfigure(1, weight=1)

        self._orb = ctk.CTkFrame(
            container,
            width=16,
            height=16,
            corner_radius=8,
            fg_color=styles.palette.accent_secondary,
        )
        self._orb.grid(row=0, column=0, padx=(12, 10))
        self._orb.grid_propagate(False)

        label = ctk.CTkLabel(
            container,
            text="Powered by DarkPegaso AI",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        label.grid(row=0, column=1, sticky="w")

        badge = ctk.CTkLabel(
            container,
            text="Control Center",
            font=styles.typography.caption,
            text_color=styles.palette.accent_primary,
            anchor="w",
        )
        badge.grid(row=1, column=1, sticky="w")

        self._cycle = styles.glow_cycle()
        self._cycle_index = 0
        self._animate_orb()

    def _animate_orb(self) -> None:
        color = self._cycle[self._cycle_index % len(self._cycle)]
        self._cycle_index += 1
        self._orb.configure(fg_color=color)
        self.after(720, self._animate_orb)
