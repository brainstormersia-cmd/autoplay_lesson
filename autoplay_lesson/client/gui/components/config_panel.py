"""Configuration view."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class ConfigPanel(ctk.CTkFrame):
    """Manage credential and automation options."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color=styles.palette.background_secondary, corner_radius=16)
        self.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="🛠️ Configurazione",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=24,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(24, 12))

        helper = ctk.CTkLabel(
            self,
            text=(
                "Inserisci i dati del corso Pegaso e scegli da quale capitolo ripartire. "
                "I campi con il lucchetto vengono salvati in locale solo se attivi Ricorda."
            ),
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            justify="left",
            anchor="w",
            padx=24,
            wraplength=520,
        )
        helper.grid(row=1, column=0, sticky="ew")

        form = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_primary,
            corner_radius=14,
        )
        form.grid(row=2, column=0, sticky="ew", padx=24, pady=(12, 24))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        self.url_var = ctk.StringVar()
        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        self.remember_var = ctk.BooleanVar()
        self.start_chapter_var = ctk.StringVar()

        _Field(form, text="Link del corso", row=0, column=0, columnspan=2)
        url_entry = ctk.CTkEntry(
            form,
            placeholder_text="https://lms.pegaso...",
            textvariable=self.url_var,
        )
        url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 10))

        _Field(form, text="Username Pegaso", row=2, column=0)
        username_entry = ctk.CTkEntry(
            form,
            placeholder_text="Inserisci username",
            textvariable=self.username_var,
        )
        username_entry.grid(row=3, column=0, sticky="ew", pady=(4, 10), padx=(0, 10))

        _Field(form, text="Password", row=2, column=1)
        password_entry = ctk.CTkEntry(
            form,
            placeholder_text="Inserisci password",
            textvariable=self.password_var,
            show="*",
        )
        password_entry.grid(row=3, column=1, sticky="ew", pady=(4, 10), padx=(10, 0))

        self._remember = ctk.CTkCheckBox(
            form,
            text="🔒 Ricorda credenziali su questo dispositivo",
            variable=self.remember_var,
        )
        self._remember.grid(row=4, column=0, columnspan=2, sticky="w")

        start_label = ctk.CTkLabel(
            form,
            text="Capitolo iniziale",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
        )
        start_label.grid(row=5, column=0, sticky="w", pady=(14, 0))

        start_entry = ctk.CTkEntry(
            form,
            placeholder_text="Es. 5",
            textvariable=self.start_chapter_var,
        )
        start_entry.grid(row=6, column=0, sticky="ew", pady=(4, 10))

        self.mode_var = ctk.StringVar(value="COMPLETE")
        _Field(form, text="Modalità bot", row=5, column=1)
        modes = (
            ("QUIZ_ONLY", "Solo Quiz"),
            ("COURSES_ONLY", "Solo Corsi"),
            ("COMPLETE", "Corsi + Quiz"),
        )
        for idx, (value, label) in enumerate(modes, start=6):
            radio = ctk.CTkRadioButton(
                form,
                text=label,
                variable=self.mode_var,
                value=value,
            )
            radio.grid(row=idx, column=1, sticky="w", pady=2)

        advanced_title = ctk.CTkLabel(
            form,
            text="Opzioni avanzate",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=0,
        )
        advanced_title.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(18, 4))

        self.verbose_var = ctk.BooleanVar(value=True)
        self.skip_pdf_var = ctk.BooleanVar()
        self.sound_var = ctk.BooleanVar()

        advanced_opts = (
            (self.verbose_var, "Log dettagliato"),
            (self.skip_pdf_var, "Salta dispense PDF"),
            (self.sound_var, "Notifiche sonore"),
        )
        for idx, (var, label) in enumerate(advanced_opts, start=10):
            checkbox = ctk.CTkCheckBox(
                form,
                text=label,
                variable=var,
            )
            checkbox.grid(row=idx, column=0, columnspan=2, sticky="w", pady=4)

        self._save_button = ctk.CTkButton(
            self,
            text="💾 Salva configurazione",
            fg_color=styles.palette.success,
            text_color=styles.palette.background_primary,
            height=48,
            corner_radius=16,
        )
        self._save_button.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 24))

    def set_save_command(self, callback) -> None:
        self._save_button.configure(command=callback)


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
