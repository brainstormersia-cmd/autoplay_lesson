"""Centralised CSS selectors used across lessons and quizzes."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverlaySelectors:
    """Selectors and labels used to detect and dismiss blocking overlays."""

    candidates: tuple[str, ...] = (
        "div.fixed.inset-0",
        "div.fixed.top-0.left-0.right-0.bottom-0",
        "div.fixed[class*='z-']",
        "div[class*='bg-black\\/20'][class*='fixed']",
        "div[class*='overlay'][class*='fixed']",
        "div[class*='modal'][class*='fixed']",
    )
    button_labels: tuple[str, ...] = (
        "Chiudi",
        "Chiudi X",
        "Close",
        "Ok",
        "OK",
        "Continua",
        "Ho capito",
        "Comprendo",
    )


@dataclass(frozen=True)
class LessonSelectors:
    """Selectors related to lesson discovery and progress extraction."""

    title_exclusions: tuple[str, ...] = ("dispensa", "obiettivi")
    quiz_keywords: tuple[str, ...] = ("test di fine lezione",)
    lesson_row: str = (
        ":scope div.border-t.hover\\:bg-platform-hover-light, "
        ":scope a.css-1oaf, "
        ":scope a.css-v7ntdn, "
        ":scope a[class*='outline-single-item-content-wrapper'], "
        ":scope li[data-current-item='true'], "
        ":scope li[data-current-item='true'] a"
    )
    title: str = (
        ":scope div.mb-2, :scope span.font-semibold, :scope .text-base .mb-2, "
        ":scope div.font-semibold, :scope h3, :scope h4"
    )
    duration: str = ":scope div.text-sm.text-platform-gray, :scope span.text-sm, :scope span.text-xs"
    percentage: str = (
        ":scope div.w-1\\/12.text-xs, :scope div.w-1\\/12.md\\:text-xs, :scope span.text-xs, :scope span.text-sm"
    )
    progress_complete: str = (
        ":scope .bg-platform-green[style*='width: 100%'], "
        ":scope .bg-platform-primary[style*='width: 100%'], "
        ":scope svg[data-testid='learn-item-success-icon']"
    )
    chapter_container: str = (
        "div.bg-white.text-base.border.font-sans.font-semibold, "
        "div:has(.cds-AccordionHeader-button)"
    )
    chapter_header: str = (
        "h3.css-k9b3du button.cds-AccordionHeader-button, "
        ".cds-AccordionHeader-button, "
        "div[data-testid='module-number-heading'], "
        "div.bg-white.text-base.border div.cursor-pointer, "
        "div.bg-white.text-base.border svg + div, "
        "div.bg-white.text-base.border:has(svg), "
        "div.bg-white.text-base.border div[role='button'], "
        "div.flex.items-center.font-medium:has(svg)"
    )
    video_block_header_text: str = "Riproduzione del video non consentita"
    video_block_header: str = "h3.text-2xl.font-medium.mt-4.whitespace-pre-line"
    video_block_confirm: str = "button.bg-platform-primary.text-white"


@dataclass(frozen=True)
class QuizSelectors:
    """Selectors required to interact with quizzes."""

    container: str = "div.mt-8.px-4"
    collapsible_header: str = "div.flex.align-middle.leading-none.px-4"
    option: str = ":scope .px-3"
    selected_class: str = "bg-platform-active-color"
    wrong_class: str = "!bg-platform-red/10"
    submit: str = "button.bg-platform-primary:has-text(\"Invia\")"
    retry: str = "button.bg-platform-primary:has-text(\"Ripeti\")"
    execute: str = "button.bg-white.border-platform-primary:has-text(\"Esegui\")"
    alternate_execute: tuple[str, ...] = (
        "button.bg-platform-primary:has-text(\"Esegui\")",
        "button:has-text(\"Avvia\")",
        "button:has-text(\"Continua\")",
        "button:has-text(\"Prosegui\")",
        "button:has-text(\"Inizia\")",
        "[role='button']:has-text(\"Avvia\")",
        "[role='button']:has-text(\"Continua\")",
        "[role='button']:has-text(\"Prosegui\")",
    )


LESSON_SELECTORS = LessonSelectors()
QUIZ_SELECTORS = QuizSelectors()
OVERLAY_SELECTORS = OverlaySelectors()

__all__ = [
    "LESSON_SELECTORS",
    "QUIZ_SELECTORS",
    "OVERLAY_SELECTORS",
    "LessonSelectors",
    "QuizSelectors",
    "OverlaySelectors",
]
