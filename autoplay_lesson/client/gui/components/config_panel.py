"""Configuration view."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles


class ConfigPanel(ctk.CTkFrame):
    """Manage credential and automation options."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color="transparent")
        self.columnconfigure(0, weight=1)

        creds_card = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_secondary,
            corner_radius=12,
        )
        creds_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        creds_card.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            creds_card,
            text="🔐 Credenziali",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(16, 8))

        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        self.remember_var = ctk.BooleanVar()

        username_entry = ctk.CTkEntry(
            creds_card,
            placeholder_text="Inserisci username",
            textvariable=self.username_var,
        )
        username_entry.grid(row=1, column=0, sticky="ew", padx=16, pady=4)

        password_entry = ctk.CTkEntry(
            creds_card,
            placeholder_text="Inserisci password",
            show="*",
            textvariable=self.password_var,
        )
        password_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=4)

        remember = ctk.CTkCheckBox(
            creds_card,
            text="Ricorda credenziali",
            variable=self.remember_var,
        )
        remember.grid(row=3, column=0, sticky="w", padx=16, pady=(4, 16))

        options_card = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_secondary,
            corner_radius=12,
        )
        options_card.grid(row=1, column=0, sticky="ew")
        options_card.columnconfigure(0, weight=1)

        options_title = ctk.CTkLabel(
            options_card,
            text="⚙️ Opzioni Bot",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        options_title.grid(row=0, column=0, sticky="ew", pady=(16, 8))

        self.mode_var = ctk.StringVar(value="COMPLETE")
        modes = (
            ("QUIZ_ONLY", "○ Solo Quiz"),
            ("COURSES_ONLY", "○ Solo Corsi"),
            ("COMPLETE", "● Corsi + Quiz"),
        )
        for idx, (value, label) in enumerate(modes, start=1):
            radio = ctk.CTkRadioButton(
                options_card,
                text=label,
                variable=self.mode_var,
                value=value,
            )
            radio.grid(row=idx, column=0, sticky="w", padx=16, pady=4)

        slider_label = ctk.CTkLabel(
            options_card,
            text="Velocità esecuzione",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        slider_label.grid(row=4, column=0, sticky="ew", pady=(12, 0))

        self.speed_var = ctk.DoubleVar(value=2.5)
        slider = ctk.CTkSlider(
            options_card,
            from_=1.0,
            to=5.0,
            variable=self.speed_var,
            number_of_steps=8,
        )
        slider.grid(row=5, column=0, sticky="ew", padx=16, pady=4)

        advanced_title = ctk.CTkLabel(
            options_card,
            text="Opzioni avanzate",
            font=styles.typography.primary,
            text_color=styles.palette.text_secondary,
            anchor="w",
            padx=16,
        )
        advanced_title.grid(row=6, column=0, sticky="ew", pady=(12, 0))

        self.verbose_var = ctk.BooleanVar(value=True)
        self.skip_pdf_var = ctk.BooleanVar()
        self.sound_var = ctk.BooleanVar()

        advanced_opts = (
            (self.verbose_var, "Log dettagliato"),
            (self.skip_pdf_var, "Salta dispense PDF"),
            (self.sound_var, "Notifiche sonore"),
        )
        for idx, (var, label) in enumerate(advanced_opts, start=7):
            checkbox = ctk.CTkCheckBox(
                options_card,
                text=label,
                variable=var,
            )
            checkbox.grid(row=idx, column=0, sticky="w", padx=16, pady=4)

        self._save_button = ctk.CTkButton(
            options_card,
            text="💾 Salva Configurazione",
            fg_color=styles.palette.success,
            text_color=styles.palette.background_primary,
        )
        self._save_button.grid(row=10, column=0, sticky="ew", padx=16, pady=(16, 20))

    def set_save_command(self, callback) -> None:
        self._save_button.configure(command=callback)
