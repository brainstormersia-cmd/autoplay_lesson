"""Scrollable log console component."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


LOG_COLORS = {
    "success": styles.palette.success,
    "error": styles.palette.error,
    "warning": styles.palette.warning,
    "action": styles.palette.accent_secondary,
    "info": styles.palette.text_primary,
    "debug": styles.palette.text_secondary,
    "critical": styles.palette.error,
    "default": styles.palette.text_secondary,
}


class LogConsole(ctk.CTkFrame):
    """Display area for log lines with auto-scroll support."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_secondary,
            corner_radius=16,
        )
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ctk.CTkLabel(
            self,
            text="📋 Log Attività",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=20,
        )
        header.grid(row=0, column=0, sticky="ew", pady=(18, 8))

        self._textbox = ctk.CTkTextbox(
            self,
            fg_color=styles.palette.background_primary,
            text_color=styles.palette.text_secondary,
            font=styles.typography.console,
            activate_scrollbars=True,
            corner_radius=12,
            wrap="word",
        )
        self._textbox.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self._textbox.configure(state="disabled")

        self._clear_button = ctk.CTkButton(
            self,
            text="🗑️ Pulisci Log",
            font=styles.typography.primary,
            fg_color="transparent",
            hover_color=styles.palette.accent_primary,
            text_color=styles.palette.text_secondary,
            command=self.clear,
        )
        self._clear_button.place(relx=0.96, rely=0.085, anchor="ne")

    def append(self, message: str, *, category: str = "default") -> None:
        """Append a message to the console with formatting."""

        color = LOG_COLORS.get(category, LOG_COLORS["default"])
        tag_name = f"level-{category}"
        self._textbox.configure(state="normal")
        self._textbox.insert("end", f"{message}\n")
        start_index = "end-2l"
        end_index = "end-1l"
        self._textbox.tag_add(tag_name, start_index, end_index)
        self._textbox.tag_config(tag_name, foreground=color)
        self._textbox.configure(state="disabled")
        self._textbox.see("end")

    def clear(self) -> None:
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")


__all__ = ["LogConsole"]
