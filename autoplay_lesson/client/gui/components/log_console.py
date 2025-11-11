"""Scrollable log console component."""

from __future__ import annotations

from typing import Callable, List

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class LogConsole(ctk.CTkFrame):
    """Display area for log lines with auto-scroll support."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_glass,
            corner_radius=22,
            border_width=1,
            border_color=styles.palette.outline,
        )
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ctk.CTkLabel(
            self,
            text="📋 Log attività",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=24,
        )
        header.grid(row=0, column=0, sticky="ew", pady=(20, 10))

        self._textbox = ctk.CTkTextbox(
            self,
            fg_color=styles.palette.background_glass_alt,
            text_color=styles.palette.text_secondary,
            font=styles.typography.console,
            activate_scrollbars=True,
            corner_radius=16,
            wrap="word",
            border_width=0,
        )
        self._textbox.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self._textbox.configure(state="disabled")

        self._clear_button = ctk.CTkButton(
            self,
            text="☄️ Pulisci log",
            font=styles.typography.caption,
            fg_color=styles.palette.background_glass_alt,
            hover_color=styles.blend(styles.palette.accent_primary, styles.palette.accent_secondary, 0.4),
            text_color=styles.palette.text_secondary,
            command=self.clear,
            border_width=1,
            border_color=styles.palette.soft_outline,
            height=28,
            corner_radius=10,
        )
        self._clear_button.place(relx=0.97, rely=0.14, anchor="ne")

        self._listeners: List[Callable[[str, str], None]] = []

    def add_listener(self, callback: Callable[[str, str], None]) -> None:
        """Register a callback notified whenever a log is appended."""

        self._listeners.append(callback)

    def append(self, message: str, *, category: str = "default") -> None:
        """Append a message to the console with formatting."""

        color = styles.LOG_COLORS.get(category, styles.LOG_COLORS["default"])
        tag_name = f"level-{category}"
        self._textbox.configure(state="normal")
        self._textbox.insert("end", f"{message}\n")
        start_index = "end-2l"
        end_index = "end-1l"
        self._textbox.tag_add(tag_name, start_index, end_index)
        self._textbox.tag_config(tag_name, foreground=color)
        self._textbox.configure(state="disabled")
        self._textbox.see("end")

        for listener in self._listeners:
            listener(message, category)

    def clear(self) -> None:
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")


__all__ = ["LogConsole"]
