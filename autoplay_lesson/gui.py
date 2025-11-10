"""Tkinter based GUI for the autoplay lesson runner."""
from __future__ import annotations

import asyncio
import threading
import queue
import tkinter as tk
from tkinter import messagebox, scrolledtext
from typing import Optional

from pathlib import Path

from .config import (
    DEFAULT_USER_DATA_DIR,
    PersistentSettings,
    RuntimeConfig,
    clear_persistent_settings,
    delete_password,
    keyring_available,
    load_persistent_settings,
    load_saved_password,
    save_password,
    save_persistent_settings,
)
from .runner import Runner


class AutoplayApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Autoplay Lesson")
        self.root.geometry("640x520")

        self._runner: Optional[Runner] = None
        self._thread: Optional[threading.Thread] = None
        self._log_queue: "queue.Queue[str]" = queue.Queue(maxsize=500)

        self._settings = load_persistent_settings()
        self._stored_username = self._settings.username
        self._stored_password = load_saved_password(self._settings.username) if self._settings.remember_me else None

        self._build_form()
        self._build_log()
        self._poll_log_queue()

    def _build_form(self) -> None:
        frame = tk.LabelFrame(self.root, text="Configurazione")
        frame.pack(fill="x", padx=10, pady=10)
        for column in range(2):
            frame.columnconfigure(column, weight=1)

        self.url_var = tk.StringVar(value=self._settings.url)
        self.username_var = tk.StringVar(value=self._settings.username)
        self.password_var = tk.StringVar(value=self._stored_password or "")
        self.start_var = tk.StringVar(value=str(self._settings.start_chapter or ""))
        self.headless_var = tk.BooleanVar(value=self._settings.headless)
        self.after_play_var = tk.IntVar(value=self._settings.after_play)
        self.buffer_var = tk.IntVar(value=self._settings.buffer)
        self.slow_var = tk.IntVar(value=self._settings.slow_mo)
        self.chrome_profile_var = tk.BooleanVar(value=self._settings.use_chrome_profile)
        self.profile_path_var = tk.StringVar(value=self._settings.user_data_dir or str(DEFAULT_USER_DATA_DIR))
        self.diagnose_var = tk.BooleanVar(value=self._settings.diagnose)
        self.remember_var = tk.BooleanVar(value=self._settings.remember_me)

        self._add_labeled_entry(frame, "URL", self.url_var, row=0)
        self._add_labeled_entry(frame, "Username", self.username_var, row=1)
        self._add_labeled_entry(frame, "Password", self.password_var, row=2, show="*")
        self._add_labeled_entry(frame, "Capitolo iniziale", self.start_var, row=3)

        tk.Label(frame, text="Headless").grid(row=0, column=2, padx=6, pady=4, sticky="w")
        tk.Checkbutton(frame, variable=self.headless_var).grid(row=0, column=3, sticky="w")

        tk.Label(frame, text="Usa profilo Chrome").grid(row=1, column=2, padx=6, pady=4, sticky="w")
        tk.Checkbutton(frame, variable=self.chrome_profile_var, command=self._toggle_profile_entry).grid(row=1, column=3, sticky="w")

        tk.Label(frame, text="Ricordami").grid(row=2, column=2, padx=6, pady=4, sticky="w")
        tk.Checkbutton(frame, variable=self.remember_var).grid(row=2, column=3, sticky="w")

        self._add_labeled_spin(frame, "After-play (s)", self.after_play_var, row=4)
        self._add_labeled_spin(frame, "Buffer (s)", self.buffer_var, row=5)
        self._add_labeled_spin(frame, "Slow (ms)", self.slow_var, row=6, step=50, max_value=2000)

        tk.Label(frame, text="Diagnostica").grid(row=3, column=2, padx=6, pady=4, sticky="w")
        tk.Checkbutton(frame, variable=self.diagnose_var).grid(row=3, column=3, sticky="w")

        tk.Label(frame, text="Cartella profilo Chrome").grid(row=7, column=0, padx=6, pady=4, sticky="w")
        self.profile_entry = tk.Entry(frame, textvariable=self.profile_path_var)
        self.profile_entry.grid(row=7, column=1, columnspan=3, padx=6, pady=4, sticky="we")
        self._toggle_profile_entry()

        buttons = tk.Frame(self.root)
        buttons.pack(fill="x", padx=10)
        self.start_button = tk.Button(buttons, text="Start", command=self.start)
        self.start_button.pack(side=tk.LEFT, padx=6, pady=4)
        self.stop_button = tk.Button(buttons, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=6, pady=4)

    def _toggle_profile_entry(self) -> None:
        state = tk.NORMAL if self.chrome_profile_var.get() else tk.DISABLED
        self.profile_entry.configure(state=state)

    def _add_labeled_entry(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        *,
        row: int,
        show: Optional[str] = None,
    ) -> None:
        tk.Label(parent, text=label).grid(row=row, column=0, padx=6, pady=4, sticky="w")
        entry = tk.Entry(parent, textvariable=variable, show=show)
        entry.grid(row=row, column=1, padx=6, pady=4, sticky="we")

    def _add_labeled_spin(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.IntVar,
        *,
        row: int,
        min_value: int = 0,
        max_value: int = 600,
        step: int = 1,
    ) -> None:
        tk.Label(parent, text=label).grid(row=row, column=0, padx=6, pady=4, sticky="w")
        spin = tk.Spinbox(parent, textvariable=variable, from_=min_value, to=max_value, increment=step, width=8)
        spin.grid(row=row, column=1, padx=6, pady=4, sticky="w")

    def _build_log(self) -> None:
        log_frame = tk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_widget = scrolledtext.ScrolledText(log_frame, state=tk.DISABLED, wrap=tk.WORD)
        self.log_widget.pack(fill="both", expand=True, padx=6, pady=6)

    def _poll_log_queue(self) -> None:
        try:
            while True:
                message = self._log_queue.get_nowait()
                self._append_log(message)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_log_queue)

    def _append_log(self, message: str) -> None:
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, message + "\n")
        self.log_widget.see(tk.END)
        self.log_widget.configure(state=tk.DISABLED)

    def start(self) -> None:
        if self._runner is not None:
            messagebox.showinfo("Autoplay", "Esecuzione già in corso")
            return
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Autoplay", "Inserisci un URL valido")
            return
        try:
            start_chapter = int(self.start_var.get()) if self.start_var.get() else None
        except ValueError:
            messagebox.showerror("Autoplay", "Capitolo iniziale deve essere un numero")
            return

        username = self.username_var.get().strip()
        password = self.password_var.get()
        remember_me = self.remember_var.get()
        profile_path = self.profile_path_var.get().strip()

        config = RuntimeConfig(
            url=url,
            username=username or None,
            password=password or None,
            remember_me=remember_me,
            headless=self.headless_var.get(),
            start_chapter=start_chapter,
            after_play=self.after_play_var.get(),
            buffer=self.buffer_var.get(),
            slow_mo=self.slow_var.get(),
            use_chrome_profile=self.chrome_profile_var.get(),
            user_data_dir=Path(profile_path) if profile_path else DEFAULT_USER_DATA_DIR,
            diagnose=self.diagnose_var.get(),
        )

        self._persist_preferences(config, password)

        self._runner = Runner(config, log_queue=self._log_queue)
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        assert self._runner is not None
        try:
            asyncio.run(self._runner.run())
        except Exception as exc:  # pragma: no cover - UI guard
            self._log_queue.put(f"Errore: {exc}")
        finally:
            self.root.after(0, self._reset_buttons)
            self._runner = None

    def _reset_buttons(self) -> None:
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)

    def stop(self) -> None:
        if self._runner is None:
            return
        self._runner.request_stop()
        self.stop_button.configure(state=tk.DISABLED)

    def _persist_preferences(self, config: RuntimeConfig, password: Optional[str]) -> None:
        previous_username = self._stored_username
        if config.remember_me:
            settings = PersistentSettings(
                url=config.url,
                username=config.username or "",
                user_data_dir=str(config.user_data_dir or DEFAULT_USER_DATA_DIR),
                remember_me=True,
                headless=config.headless,
                use_chrome_profile=config.use_chrome_profile,
                after_play=config.after_play,
                buffer=config.buffer,
                slow_mo=config.slow_mo,
                diagnose=config.diagnose,
                start_chapter=config.start_chapter,
            )
            save_persistent_settings(settings)
            self._settings = settings
            if password and config.username:
                if not save_password(config.username, password):
                    if not keyring_available():
                        self._log_queue.put(
                            "Keyring non disponibile: la password non verrà salvata."
                        )
                    else:
                        self._log_queue.put(
                            "Impossibile salvare la password nel keyring."
                        )
                else:
                    self._stored_password = password
            else:
                delete_password(config.username or "")
                self._stored_password = None
        else:
            clear_persistent_settings()
            delete_password(config.username or "")
            if self._stored_username and self._stored_username != (config.username or ""):
                delete_password(self._stored_username)
            self._settings = PersistentSettings(remember_me=False)
            self._stored_password = None
        self._stored_username = config.username or ""
        if previous_username and previous_username != self._stored_username:
            delete_password(previous_username)


def launch_gui() -> None:
    root = tk.Tk()
    app = AutoplayApp(root)
    root.mainloop()
