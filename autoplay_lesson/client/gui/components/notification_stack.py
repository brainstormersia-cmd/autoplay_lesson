"""Glassmorphism notification stack with neon highlights."""

from __future__ import annotations

from collections import deque
from typing import Deque

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


_LEVEL_STYLES = {
    "info": (styles.palette.accent_secondary, styles.palette.text_primary, "🔔"),
    "success": (styles.palette.success, styles.palette.background_primary, "✅"),
    "warning": (styles.palette.warning, styles.palette.background_primary, "⚠️"),
    "error": (styles.palette.error, styles.palette.background_primary, "✖"),
}


class NotificationStack(ctk.CTkFrame):
    """Compact stack of animated notification cards."""

    MAX_ITEMS = 4

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
            text="⚡ Aggiornamenti in tempo reale",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=24,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(20, 10))

        self._container = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_glass_alt,
            corner_radius=18,
            border_width=1,
            border_color=styles.palette.soft_outline,
        )
        self._container.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 22))
        self._container.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._cards: Deque[_NotificationCard] = deque()

    def push(self, title: str, message: str, *, level: str = "info") -> None:
        """Push a notification card on top of the stack."""

        palette = _LEVEL_STYLES.get(level, _LEVEL_STYLES["info"])
        card = _NotificationCard(
            self._container,
            title=title,
            message=message,
            accent_color=palette[0],
            text_color=palette[1],
            icon=palette[2],
        )
        self._cards.appendleft(card)
        self._refresh_grid()
        if len(self._cards) > self.MAX_ITEMS:
            old = self._cards.pop()
            old.destroy()

    def clear(self) -> None:
        while self._cards:
            card = self._cards.pop()
            card.destroy()

    def _refresh_grid(self) -> None:
        for index, card in enumerate(self._cards):
            card.grid(row=index, column=0, sticky="ew", padx=18, pady=(10 if index else 18, 10))


class _NotificationCard(ctk.CTkFrame):
    """Single notification entry with glowing accent strip."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        title: str,
        message: str,
        accent_color: str,
        text_color: str,
        icon: str,
    ) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_glass,
            corner_radius=18,
            border_width=1,
            border_color=styles.blend(accent_color, styles.palette.soft_outline, 0.45),
        )
        self.columnconfigure(1, weight=1)

        glow = ctk.CTkFrame(self, width=8, fg_color=accent_color, corner_radius=4)
        glow.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(14, 16), pady=18)

        icon_label = ctk.CTkLabel(
            self,
            text=icon,
            font=styles.typography.section,
            text_color=accent_color,
            anchor="w",
        )
        icon_label.grid(row=0, column=1, sticky="w", pady=(18, 0))

        title_label = ctk.CTkLabel(
            self,
            text=title,
            font=styles.typography.primary_semibold,
            text_color=text_color,
            anchor="w",
        )
        title_label.grid(row=0, column=1, sticky="w", padx=(36, 18))

        message_label = ctk.CTkLabel(
            self,
            text=message,
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            wraplength=440,
            justify="left",
        )
        message_label.grid(row=1, column=1, sticky="ew", padx=(36, 18), pady=(0, 18))


__all__ = ["NotificationStack"]
