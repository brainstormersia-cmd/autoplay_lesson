"""Live notification stack with neon cards."""

from __future__ import annotations

from typing import Deque
from collections import deque

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


_LEVEL_STYLES = {
    "info": (styles.palette.accent_secondary, styles.palette.text_primary),
    "success": (styles.palette.success, styles.palette.background_primary),
    "warning": (styles.palette.warning, styles.palette.background_primary),
    "error": (styles.palette.error, styles.palette.background_primary),
}


class NotificationStack(ctk.CTkFrame):
    """Compact stack of animated notification cards."""

    MAX_ITEMS = 4

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=16)
        self.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="⚡ Aggiornamenti in tempo reale",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=20,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(18, 8))

        self._container = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_primary,
            corner_radius=12,
        )
        self._container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self._container.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._cards: Deque[_NotificationCard] = deque()

    def push(self, title: str, message: str, *, level: str = "info") -> None:
        """Push a notification card on top of the stack."""

        palette = _LEVEL_STYLES.get(level, _LEVEL_STYLES.get("info"))
        card = _NotificationCard(
            self._container,
            title=title,
            message=message,
            accent_color=palette[0],
            text_color=palette[1],
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
            card.grid(row=index, column=0, sticky="ew", padx=16, pady=(8 if index else 16, 8))


class _NotificationCard(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        title: str,
        message: str,
        accent_color: str,
        text_color: str,
    ) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=14)
        self.columnconfigure(1, weight=1)

        accent = ctk.CTkFrame(self, width=6, fg_color=accent_color, corner_radius=3)
        accent.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(12, 12), pady=16)

        title_label = ctk.CTkLabel(
            self,
            text=title,
            font=styles.typography.primary_semibold,
            text_color=text_color,
            anchor="w",
        )
        title_label.grid(row=0, column=1, sticky="ew", pady=(16, 0))

        message_label = ctk.CTkLabel(
            self,
            text=message,
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            wraplength=420,
            justify="left",
        )
        message_label.grid(row=1, column=1, sticky="ew", pady=(0, 16))


__all__ = ["NotificationStack"]
