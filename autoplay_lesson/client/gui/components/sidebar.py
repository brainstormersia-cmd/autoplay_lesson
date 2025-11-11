"""Sidebar navigation for the DarkPegaso desktop shell."""

from __future__ import annotations

from typing import Callable, Dict, Iterable

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class Sidebar(ctk.CTkFrame):
    """Vertical navigation rail with section buttons."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        width: int = 200,
        on_section_change: Callable[[str], None],
        sections: Iterable[Dict[str, str]],
    ) -> None:
        super().__init__(
            master,
            fg_color=styles.palette.background_secondary,
            width=width,
            corner_radius=0,
        )
        self._buttons: Dict[str, ctk.CTkButton] = {}
        self._current: str | None = None
        self._callback = on_section_change

        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            self,
            text="DarkPegaso",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        header.grid(row=0, column=0, sticky="ew", pady=(24, 16))

        for idx, section in enumerate(sections, start=1):
            identifier = section["id"]
            button = ctk.CTkButton(
                self,
                text=f"{section['icon']}  {section['label']}",
                fg_color="transparent",
                hover_color=styles.palette.accent_primary,
                text_color=styles.palette.text_secondary,
                anchor="w",
                font=styles.typography.primary,
                command=lambda ident=identifier: self._handle_click(ident),
            )
            button.grid(row=idx, column=0, sticky="ew", padx=12, pady=4)
            self._buttons[identifier] = button

        self.rowconfigure(len(self._buttons) + 1, weight=1)

        exit_button = ctk.CTkButton(
            self,
            text="❌  Esci",
            fg_color="transparent",
            hover_color=styles.palette.error,
            text_color=styles.palette.text_secondary,
            anchor="w",
            font=styles.typography.primary,
            command=self._request_exit,
        )
        exit_button.grid(row=len(self._buttons) + 2, column=0, sticky="ew", padx=12, pady=(16, 24))

    def select(self, identifier: str) -> None:
        """Highlight the provided section."""

        if identifier == self._current:
            return

        if self._current and self._current in self._buttons:
            previous = self._buttons[self._current]
            previous.configure(
                fg_color="transparent",
                text_color=styles.palette.text_secondary,
            )

        current = self._buttons[identifier]
        current.configure(
            fg_color=styles.palette.accent_primary,
            text_color=styles.palette.text_primary,
        )
        self._current = identifier

    def _handle_click(self, identifier: str) -> None:
        self.select(identifier)
        self._callback(identifier)

    def _request_exit(self) -> None:
        self.winfo_toplevel().event_generate("<<darkpegaso-exit>>")
