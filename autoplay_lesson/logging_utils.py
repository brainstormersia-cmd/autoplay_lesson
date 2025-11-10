"""Logging helpers shared by CLI and GUI entrypoints."""
from __future__ import annotations

import logging
import queue
from dataclasses import dataclass
from typing import Optional

from .config import RuntimeConfig


class TkLogHandler(logging.Handler):
    """Handler that forwards log records into a queue consumed by the GUI."""

    def __init__(self, log_queue: "queue.Queue[str]") -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - UI glue
        message = self.format(record)
        try:
            self.log_queue.put_nowait(message)
        except queue.Full:
            pass


@dataclass(slots=True)
class LoggingSetup:
    logger: logging.Logger
    queue_handler: Optional[TkLogHandler] = None


def configure_logging(config: RuntimeConfig, *, log_queue: Optional["queue.Queue[str]"] = None) -> LoggingSetup:
    logger = logging.getLogger("autoplay_lesson")
    level = logging.DEBUG if config.detailed_log else logging.INFO
    logger.setLevel(level)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.handlers.clear()
    logger.addHandler(console_handler)

    queue_handler: Optional[TkLogHandler] = None
    if log_queue is not None:
        queue_handler = TkLogHandler(log_queue)
        queue_handler.setFormatter(formatter)
        queue_handler.setLevel(level)
        logger.addHandler(queue_handler)

    if config.log_file:
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(config.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)

    return LoggingSetup(logger=logger, queue_handler=queue_handler)
