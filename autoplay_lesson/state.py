"""Persistence helpers for autoplay lesson runner."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class LessonState:
    chapter_index: Optional[int] = None
    lesson_title: Optional[str] = None

    @classmethod
    def load(cls, path: Path) -> "LessonState":
        if not path.exists():
            return cls()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            chapter_index=payload.get("chapter_index"),
            lesson_title=payload.get("lesson_title"),
        )

    def save(self, path: Path) -> None:
        try:
            path.write_text(
                json.dumps(
                    {
                        "chapter_index": self.chapter_index,
                        "lesson_title": self.lesson_title,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        except OSError:
            # Saving the state must never crash the runner.
            pass
