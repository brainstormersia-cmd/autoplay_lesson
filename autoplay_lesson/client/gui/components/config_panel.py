"""Configuration view styled with neon glassmorphism."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


MODE_LABELS = {
    "QUIZ_ONLY": "Solo Quiz",
    "COURSES_ONLY": "Solo Corsi",
    "COMPLETE": "Corsi + Quiz",
}

DISPLAY_TO_MODE = {label: value for value, label in MODE_LABELS.items()}


class ConfigPanel(ctk.CTkFrame):
    """Manage credential and automation options."""

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
            text="🛠️ Configurazione",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=24,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(24, 8))

        helper = ctk.CTkLabel(
            self,
            text=(
                "Definisci parametri e credenziali per orchestrare DarkPegaso."
                " Ogni campo è ottimizzato per l'interfaccia glass con feedback luminosi."
            ),
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            justify="left",
            anchor="w",
            wraplength=520,
            padx=24,
        )
        helper.grid(row=1, column=0, sticky="ew")

        form = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_glass_alt,
            corner_radius=20,
            border_width=1,
            border_color=styles.palette.soft_outline,
        )
        form.grid(row=2, column=0, sticky="ew", padx=24, pady=(14, 24))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        self.url_var = ctk.StringVar()
        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        self.remember_var = ctk.BooleanVar()
        self.start_chapter_var = ctk.StringVar()
        self.mode_var = ctk.StringVar(value="COMPLETE")
        self.verbose_var = ctk.BooleanVar(value=True)
        self.skip_pdf_var = ctk.BooleanVar()
        self.sound_var = ctk.BooleanVar()

        _Field(form, text="Link del corso", row=0, column=0, columnspan=2)
        url_entry = ctk.CTkEntry(
            form,
            placeholder_text="https://lms.pegaso...",
            textvariable=self.url_var,
            fg_color=styles.palette.background_primary,
            border_color=styles.palette.accent_primary,
            border_width=2,
            corner_radius=14,
        )
        url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        _Field(form, text="Username Pegaso", row=2, column=0)
        username_entry = ctk.CTkEntry(
            form,
            placeholder_text="Inserisci username",
            textvariable=self.username_var,
            fg_color=styles.palette.background_primary,
            border_color=styles.palette.accent_secondary,
            border_width=2,
            corner_radius=14,
        )
        username_entry.grid(row=3, column=0, sticky="ew", pady=(4, 12), padx=(0, 10))

        _Field(form, text="Password", row=2, column=1)
        password_entry = ctk.CTkEntry(
            form,
            placeholder_text="Inserisci password",
            textvariable=self.password_var,
            show="*",
            fg_color=styles.palette.background_primary,
            border_color=styles.palette.accent_secondary,
            border_width=2,
            corner_radius=14,
        )
        password_entry.grid(row=3, column=1, sticky="ew", pady=(4, 12), padx=(10, 0))

        self._remember = ctk.CTkSwitch(
            form,
            text="Ricorda credenziali su questo dispositivo",
            variable=self.remember_var,
            fg_color=styles.palette.accent_primary,
            progress_color=styles.palette.success,
            button_color=styles.palette.accent_secondary,
            button_hover_color=styles.palette.accent_magenta,
        )
        self._remember.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 12))

        start_label = ctk.CTkLabel(
            form,
            text="Capitolo iniziale",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        start_label.grid(row=5, column=0, sticky="w", pady=(6, 0))

        start_entry = ctk.CTkEntry(
            form,
            placeholder_text="Es. 5",
            textvariable=self.start_chapter_var,
            fg_color=styles.palette.background_primary,
            border_color=styles.palette.accent_primary,
            border_width=2,
            corner_radius=14,
        )
        start_entry.grid(row=6, column=0, sticky="ew", pady=(4, 12))

        _Field(form, text="Modalità bot", row=5, column=1)
        self._mode_display = ctk.StringVar(value=MODE_LABELS[self.mode_var.get()])
        self._mode_selector = ctk.CTkSegmentedButton(
            form,
            values=list(MODE_LABELS.values()),
            variable=self._mode_display,
            font=styles.typography.primary_semibold,
            command=self._on_mode_selected,
            corner_radius=12,
            fg_color=styles.palette.background_primary,
            selected_color=styles.palette.accent_secondary,
            selected_hover_color=styles.palette.accent_primary,
            unselected_color=styles.palette.background_glass,
            unselected_hover_color=styles.palette.background_layer,
        )
        self._mode_selector.grid(row=6, column=1, sticky="ew", pady=(4, 12))

        advanced_title = ctk.CTkLabel(
            form,
            text="Opzioni avanzate",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        advanced_title.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(10, 4))

        advanced_opts = (
            (self.verbose_var, "Log dettagliato"),
            (self.skip_pdf_var, "Salta dispense PDF"),
            (self.sound_var, "Notifiche sonore"),
        )
        for idx, (var, label) in enumerate(advanced_opts, start=8):
            checkbox = ctk.CTkCheckBox(
                form,
                text=label,
                variable=var,
                fg_color=styles.palette.accent_secondary,
                hover_color=styles.palette.accent_primary,
                border_color=styles.palette.soft_outline,
                text_color=styles.palette.text_secondary,
            )
            checkbox.grid(row=idx, column=0, columnspan=2, sticky="w", pady=4)

        self._save_button = ctk.CTkButton(
            self,
            text="💾 Salva configurazione",
            fg_color=styles.palette.success,
            text_color=styles.palette.background_primary,
            height=52,
            corner_radius=20,
            border_width=2,
            border_color=styles.blend(styles.palette.success, styles.palette.accent_primary, 0.3),
            hover_color=styles.blend(styles.palette.success, styles.palette.accent_secondary, 0.25),
        )
        self._save_button.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 24))

        self.mode_var.trace_add("write", self._sync_mode_selector)
        self._save_cycle = (
            styles.palette.success,
            styles.blend(styles.palette.success, styles.palette.accent_primary, 0.4),
            styles.blend(styles.palette.success, styles.palette.accent_secondary, 0.6),
        )
        self._save_cycle_index = 0
        self._animate_save_button()

    def set_save_command(self, callback) -> None:
        self._save_button.configure(command=callback)

    def _on_mode_selected(self, label: str) -> None:
        value = DISPLAY_TO_MODE.get(label, "COMPLETE")
        self.mode_var.set(value)

    def _sync_mode_selector(self, *_args) -> None:
        label = MODE_LABELS.get(self.mode_var.get(), MODE_LABELS["COMPLETE"])
        if self._mode_display.get() != label:
            self._mode_display.set(label)
            self._mode_selector.set(label)

    def _animate_save_button(self) -> None:
        color = self._save_cycle[self._save_cycle_index % len(self._save_cycle)]
        self._save_cycle_index += 1
        self._save_button.configure(border_color=color)
        self.after(680, self._animate_save_button)


class _Field(ctk.CTkLabel):
    def __init__(self, master: ctk.CTkBaseClass, *, text: str, row: int, column: int, columnspan: int = 1) -> None:
        super().__init__(
            master,
            text=text,
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        self.grid(row=row, column=column, columnspan=columnspan, sticky="w")


__all__ = ["ConfigPanel"]
