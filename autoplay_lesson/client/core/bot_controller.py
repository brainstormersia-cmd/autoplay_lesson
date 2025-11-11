"""Threaded bridge between the GUI and automation runner."""

from __future__ import annotations

import threading
import time
from queue import Queue
from typing import Callable, Dict, Optional

from autoplay_lesson.runner import AutomationRunner


class BotController:
    """Fire-and-forget wrapper around :class:`AutomationRunner`."""

    def __init__(
        self,
        log_callback: Callable[[str, str], None],
        progress_callback: Callable[[float, Optional[str]], None],
    ) -> None:
        self._log_callback = log_callback
        self._progress_callback = progress_callback
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._queue: "Queue[tuple[str, Dict[str, float | str | None]]]" = Queue()
        self._automation = AutomationRunner(self._enqueue_log, self._enqueue_progress)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: Dict[str, object]) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, args=(config,), daemon=True)
        self._thread.start()
        threading.Thread(target=self._drain_queue, daemon=True).start()

    def stop(self) -> None:
        if not self.is_running:
            return
        self._stop_event.set()
        self._automation.request_stop()

    def _worker(self, config: Dict[str, object]) -> None:
        try:
            self._automation.run(config)
        except Exception as exc:  # pragma: no cover - defensive
            self._log_callback(f"✗ Errore: {exc}", "error")
        finally:
            self._stop_event.set()

    def _enqueue_log(self, message: str, level: str = "default") -> None:
        self._queue.put(("log", {"message": message, "level": level}))

    def _enqueue_progress(self, value: float, eta: Optional[str] = None) -> None:
        self._queue.put(("progress", {"value": value, "eta": eta}))

    def _drain_queue(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                kind, payload = self._queue.get(timeout=0.1)
            except Exception:
                continue
            if kind == "log":
                self._log_callback(payload["message"], payload["level"])
            elif kind == "progress":
                self._progress_callback(float(payload["value"]), payload.get("eta"))
            self._queue.task_done()
            time.sleep(0.01)
