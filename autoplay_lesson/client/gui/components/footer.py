"""Footer for the DarkPegaso shell."""

from __future__ import annotations

import math
import tkinter as tk

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
        container.pack(expand=True, fill="both")
        container.grid_columnconfigure(1, weight=1)

        self._orbital = tk.Canvas(
            container,
            width=40,
            height=40,
            bd=0,
            highlightthickness=0,
            background=styles.palette.background_glass,
        )
        self._orbital.grid(row=0, column=0, rowspan=2, padx=(18, 12), pady=(6, 4))
        halo_color = styles.blend(styles.palette.accent_secondary, styles.palette.overlay_glow, 0.3)
        self._halo = self._orbital.create_oval(8, 8, 32, 32, fill=halo_color, outline="")
        self._core = self._orbital.create_oval(16, 16, 24, 24, fill=styles.palette.accent_secondary, outline="")
        self._particle = self._orbital.create_oval(0, 0, 0, 0, fill=styles.palette.accent_primary, outline="")
        self._orbit_angle = 0.0

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
        self._animate_footer()

    def _animate_footer(self) -> None:
        color = self._cycle[self._cycle_index % len(self._cycle)]
        self._cycle_index = (self._cycle_index + 1) % len(self._cycle)
        orbit_radius = 11
        self._orbit_angle = (self._orbit_angle + 8) % 360
        radians = math.radians(self._orbit_angle)
        center = 20
        x = center + orbit_radius * math.cos(radians)
        y = center + orbit_radius * math.sin(radians)
        particle_size = 6
        self._orbital.coords(
            self._particle,
            x - particle_size / 2,
            y - particle_size / 2,
            x + particle_size / 2,
            y + particle_size / 2,
        )
        self._orbital.itemconfigure(self._particle, fill=color)
        self._orbital.itemconfigure(
            self._halo,
            fill=styles.blend(color, styles.palette.overlay_glow, 0.45),
        )
        self._orbital.itemconfigure(self._core, fill=styles.blend(color, styles.palette.accent_secondary, 0.4))
        self.after(160, self._animate_footer)
