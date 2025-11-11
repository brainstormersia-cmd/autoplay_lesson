"""Help view content."""

from __future__ import annotations

import customtkinter as ctk

from autoplay_lesson.client.gui import styles

HELP_TEXT = (
    "1️⃣ Vai in Configurazione\n"
    "   Incolla il link completo del corso Pegaso\n"
    "   Inserisci username e password del portale\n"
    "   Scegli la modalità desiderata\n\n"
    "2️⃣ Torna alla Dashboard\n"
    "   Verifica il riepilogo del corso\n"
    "   Clicca \"Avvia Automazione\"\n\n"
    "3️⃣ Monitora il progresso\n"
    "   Il bot completerà automaticamente\n"
    "   le lezioni secondo le tue impostazioni\n\n"
    "💡 Suggerimenti:\n"
    "• Non chiudere il browser durante l'esecuzione\n"
    "• Verifica il log per eventuali errori\n"
    "• Modalità 'Corsi + Quiz' è consigliata\n\n"
    "⚠️ Disclaimer:\n"
    "Questo software è fornito 'as-is'.\n"
    "L'utente si assume ogni responsabilità."
)


class HelpPanel(ctk.CTkFrame):
    """Static documentation view."""

    def __init__(self, master: ctk.CTkBaseClass) -> None:
        super().__init__(master, fg_color="transparent")
        self.columnconfigure(0, weight=1)

        card = ctk.CTkFrame(
            self,
            fg_color=styles.palette.background_glass,
            corner_radius=20,
            border_width=1,
            border_color=styles.palette.soft_outline,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        title = ctk.CTkLabel(
            card,
            text="📖 Come usare DarkPegaso",
            font=styles.typography.section,
            text_color=styles.palette.text_primary,
            anchor="w",
            padx=16,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(16, 8))

        textbox = ctk.CTkTextbox(
            card,
            fg_color=styles.palette.background_glass_alt,
            text_color=styles.palette.text_secondary,
            font=styles.typography.primary,
            wrap="word",
            corner_radius=14,
            border_width=0,
        )
        textbox.insert("1.0", HELP_TEXT)
        textbox.configure(state="disabled")
        textbox.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        button_frame = ctk.CTkFrame(card, fg_color="transparent")
        button_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        button_frame.columnconfigure((0, 1), weight=1)

        tutorial = ctk.CTkButton(
            button_frame,
            text="📹 Video Tutorial",
            fg_color=styles.palette.accent_primary,
            hover_color=styles.blend(styles.palette.accent_primary, styles.palette.accent_secondary, 0.3),
        )
        tutorial.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        faq = ctk.CTkButton(
            button_frame,
            text="❓ FAQ",
            fg_color=styles.palette.accent_secondary,
            hover_color=styles.blend(styles.palette.accent_secondary, styles.palette.accent_primary, 0.3),
        )
        faq.grid(row=0, column=1, sticky="ew", padx=(8, 0))
