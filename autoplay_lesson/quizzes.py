"""Utilities to solve multiple choice quizzes within the course platform."""
from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass
from typing import Dict, Optional, Set, TYPE_CHECKING

from playwright.async_api import Error as PlaywrightError, Locator, Page

from .config import RuntimeConfig

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .lessons import ActivityWatchdog


QUIZ_CONTAINER_SELECTOR = "div.mt-8.px-4"
COLLAPSIBLE_HEADER_SELECTOR = "div.flex.align-middle.leading-none.px-4"
OPTION_SELECTOR = ":scope .px-3"
SELECTED_CLASS = "bg-platform-active-color"
WRONG_CLASS = "!bg-platform-red/10"
SUBMIT_SELECTOR = "button.bg-platform-primary:has-text(\"Invia\")"
RETRY_SELECTOR = "button.bg-platform-primary:has-text(\"Ripeti\")"
EXECUTE_SELECTOR = "button.bg-white.border-platform-primary:has-text(\"Esegui\")"
@dataclass(slots=True)
class QuizOutcome:
    """Represents the result of a quiz attempt."""

    attempts: int
    correct_answers: int
    total_questions: int
    success: bool


class QuizSolver:
    """Implements the retry logic required to complete a quiz."""

    MAX_ATTEMPTS = 50
    CORRECT_THRESHOLD: Optional[float] = None

    def __init__(
        self,
        page: Page,
        logger,
        config: RuntimeConfig,
        stop_event: asyncio.Event,
        *,
        watchdog: Optional["ActivityWatchdog"] = None,
    ) -> None:
        self.page = page
        self.logger = logger
        self.config = config
        self.stop_event = stop_event
        self.watchdog = watchdog
        self.correct_answers: Dict[int, int] = {}
        self.wrong_answers: Dict[int, set[int]] = {}
        self._touched_sections: Set[int] = set()

    async def solve(self) -> QuizOutcome:
        """Attempt to solve the quiz, returning the final outcome."""

        try:
            await self._ensure_quiz_started()
        except PlaywrightError as exc:
            self.logger.error("Quiz: impossibile avviare l'interfaccia: %s", exc)
            return QuizOutcome(0, 0, 0, False)

        questions = self.page.locator(QUIZ_CONTAINER_SELECTOR)
        total_questions = await questions.count()
        if total_questions == 0:
            try:
                await self.page.wait_for_selector(QUIZ_CONTAINER_SELECTOR, timeout=5000)
            except PlaywrightError:
                self.logger.error("Quiz: nessuna domanda trovata nell'interfaccia")
                return QuizOutcome(0, 0, 0, False)
            total_questions = await questions.count()
        if total_questions == 0:
            return QuizOutcome(0, 0, 0, False)

        required_correct: Optional[int] = None
        if self.CORRECT_THRESHOLD:
            required_correct = max(1, math.ceil(total_questions * self.CORRECT_THRESHOLD))
        attempt = 0
        last_correct = 0

        while attempt < self.MAX_ATTEMPTS and not self.stop_event.is_set():
            attempt += 1
            if self.watchdog:
                self.watchdog.raise_if_expired()
                self.watchdog.ping(f"quiz tentativo {attempt}")
            self.logger.info("Quiz: tentativo %s/%s", attempt, self.MAX_ATTEMPTS)

            if not await self._prepare_attempt():
                self.logger.warning(
                    "Quiz: impossibile preparare il tentativo %s: nessun pulsante 'Invia' o 'Ripeti'",
                    attempt,
                )
                await self._human_pause(1.0)
                continue

            await self._answer_questions(total_questions)
            if self.stop_event.is_set():
                break

            submitted = await self._submit_answers()
            if not submitted:
                if await self._handle_missing_submit():
                    self.logger.info(
                        "Quiz: 'Invia' assente al tentativo %s, riavvio tramite 'Ripeti'",
                        attempt,
                    )
                    await self._human_pause(0.8)
                    continue
                self.logger.warning("Quiz: pulsante 'Invia' non trovato al tentativo %s", attempt)
                await self._human_pause(1.0)
                continue

            try:
                await self._human_pause(1.2)
            except asyncio.CancelledError:  # pragma: no cover - cooperative cancellation
                break

            await self._wait_for_feedback(total_questions)

            correct_count = await self._collect_results(total_questions)
            last_correct = correct_count
            self.logger.info(
                "Quiz: risposte corrette %s/%s (soglia %s)",
                correct_count,
                total_questions,
                required_correct if required_correct is not None else "disattivata",
            )
            all_correct = correct_count == total_questions and total_questions > 0
            threshold_reached = (
                required_correct is not None and correct_count >= required_correct
            )
            if threshold_reached or all_correct:
                return QuizOutcome(attempt, correct_count, total_questions, True)

            if required_correct is None:
                self.logger.info(
                    "Quiz: completato con punteggio %s/%s, soglia minima disattivata",
                    correct_count,
                    total_questions,
                )
                return QuizOutcome(attempt, correct_count, total_questions, True)

            try:
                await asyncio.sleep(self._adjusted_delay(0.8))
            except asyncio.CancelledError:  # pragma: no cover
                break

            if self.stop_event.is_set():
                break

            if not await self._retry_quiz():
                self.logger.error("Quiz: pulsante 'Ripeti' non disponibile")
                break

            await self._wait_for_reset()

        return QuizOutcome(attempt, last_correct, total_questions, False)

    async def _ensure_quiz_started(self) -> None:
        button = self.page.locator(EXECUTE_SELECTOR)
        try:
            if await button.count():
                await button.first.click()
                await asyncio.sleep(self._adjusted_delay(2.0))
        except PlaywrightError as exc:
            self.logger.debug("Quiz: impossibile cliccare 'Esegui': %s", exc)
        await self._expand_collapsible_sections()
        try:
            await self.page.wait_for_selector(QUIZ_CONTAINER_SELECTOR, timeout=8000)
        except PlaywrightError:
            await self._expand_collapsible_sections(force=True)
            await self.page.wait_for_selector(QUIZ_CONTAINER_SELECTOR, timeout=5000)

    async def _expand_collapsible_sections(self, *, force: bool = False) -> None:
        if self.stop_event.is_set():
            return
        headers = self.page.locator(COLLAPSIBLE_HEADER_SELECTOR)
        try:
            count = await headers.count()
        except PlaywrightError:
            return
        if count == 0:
            return
        for index in range(count):
            if not force and index in self._touched_sections:
                continue
            if await self.page.locator(QUIZ_CONTAINER_SELECTOR).count():
                return
            header = headers.nth(index)
            clickable = header
            try:
                button_candidate = header.locator("button, [role='button']")
                if await button_candidate.count():
                    clickable = button_candidate.first
            except PlaywrightError:
                pass
            clicked = await self._safe_click(clickable, f"apertura sezione quiz {index + 1}")
            if not clicked:
                try:
                    toggle = header.locator("svg").first
                    if await toggle.count():
                        clicked = await self._safe_click(
                            toggle, f"espansione icona quiz {index + 1}"
                        )
                except PlaywrightError:
                    clicked = False
            if clicked and not force:
                self._touched_sections.add(index)
            if clicked:
                await self._human_pause(0.45)
        if force:
            await self.page.wait_for_timeout(200)

    async def _answer_questions(self, total_questions: int) -> None:
        for index in range(total_questions):
            if self.stop_event.is_set():
                return
            if self.watchdog:
                self.watchdog.ping(f"quiz domanda {index + 1}")
            question = self.page.locator(QUIZ_CONTAINER_SELECTOR).nth(index)
            if index in self.correct_answers:
                await self._select_option_by_index(question, self.correct_answers[index])
                await self._human_pause(0.35)
                continue
            await self._select_random_option(question, index)
            await self._human_pause(0.35)

        await self._ensure_all_answered(total_questions)
        await self._human_review(total_questions)

    async def _ensure_all_answered(self, total_questions: int) -> None:
        questions = self.page.locator(QUIZ_CONTAINER_SELECTOR)
        for index in range(total_questions):
            if self.stop_event.is_set():
                return
            question = questions.nth(index)
            if await self._has_selection(question):
                continue
            await self._select_random_option(question, index)
            await self._human_pause(0.25)

    async def _has_selection(self, question: Locator) -> bool:
        options = question.locator(OPTION_SELECTOR)
        try:
            for opt_index in range(await options.count()):
                classes = await options.nth(opt_index).get_attribute("class")
                if classes and SELECTED_CLASS in classes:
                    return True
        except PlaywrightError:
            return False
        return False

    async def _select_option_by_index(self, question: Locator, option_index: int) -> None:
        options = question.locator(OPTION_SELECTOR)
        try:
            count = await options.count()
        except PlaywrightError:
            return
        if option_index >= count:
            return
        target = options.nth(option_index)
        if not await self._safe_click(target, f"ripristino risposta {option_index}"):
            self.logger.debug(
                "Quiz: errore nel ripristino risposta %s: nessuna interazione riuscita",
                option_index,
            )

    async def _select_random_option(self, question: Locator, question_index: int) -> None:
        options = question.locator(OPTION_SELECTOR)
        candidates: list[int] = []
        try:
            count = await options.count()
        except PlaywrightError:
            count = 0
        wrong_choices = self.wrong_answers.get(question_index, set())
        for opt_index in range(count):
            if opt_index in wrong_choices:
                continue
            candidates.append(opt_index)
        if not candidates:
            self.logger.warning("Quiz: nessuna opzione disponibile per domanda %s", question_index + 1)
            return
        random.shuffle(candidates)
        for selected_index in candidates:
            if await self._safe_click(
                options.nth(selected_index),
                f"opzione {selected_index} domanda {question_index + 1}",
            ):
                await self._human_pause(0.2)
                self.logger.debug(
                    "Quiz: selezionata opzione %s per domanda %s",
                    selected_index,
                    question_index + 1,
                )
                return
        self.logger.warning(
            "Quiz: impossibile selezionare una risposta per domanda %s",
            question_index + 1,
        )

    async def _submit_answers(self) -> bool:
        button = self.page.locator(SUBMIT_SELECTOR)
        try:
            if await button.count():
                if await self._safe_click(button.first, "invio risposte"):
                    await self._human_pause(0.25)
                    return True
        except PlaywrightError as exc:
            self.logger.debug("Quiz: click 'Invia' fallito: %s", exc)
        return False

    async def _prepare_attempt(self) -> bool:
        if self.stop_event.is_set():
            return False
        submit_button = self.page.locator(SUBMIT_SELECTOR)
        try:
            if await submit_button.count():
                return True
        except PlaywrightError:
            pass
        retry_button = self.page.locator(RETRY_SELECTOR)
        try:
            if await retry_button.count():
                self.logger.info("Quiz: quiz già completato, uso 'Ripeti' per riavviare")
                if await self._retry_quiz():
                    await self._wait_for_reset()
                    await self._expand_collapsible_sections()
                    try:
                        if await submit_button.count():
                            return True
                    except PlaywrightError:
                        pass
        except PlaywrightError:
            pass
        return False

    async def _handle_missing_submit(self) -> bool:
        if self.stop_event.is_set():
            return False
        retry = self.page.locator(RETRY_SELECTOR)
        try:
            if await retry.count():
                if await self._retry_quiz():
                    await self._wait_for_reset()
                    await self._expand_collapsible_sections()
                    return True
        except PlaywrightError as exc:
            self.logger.debug("Quiz: impossibile utilizzare 'Ripeti' in assenza di 'Invia': %s", exc)
        return False

    async def _collect_results(self, total_questions: int) -> int:
        questions = self.page.locator(QUIZ_CONTAINER_SELECTOR)
        correct_count = 0
        for index in range(total_questions):
            question = questions.nth(index)
            options = question.locator(OPTION_SELECTOR)
            try:
                option_count = await options.count()
            except PlaywrightError:
                option_count = 0
            for opt_index in range(option_count):
                try:
                    classes = await options.nth(opt_index).get_attribute("class")
                except PlaywrightError:
                    continue
                tokens = set((classes or "").split())
                if SELECTED_CLASS not in tokens:
                    continue
                if WRONG_CLASS in tokens:
                    self.wrong_answers.setdefault(index, set()).add(opt_index)
                else:
                    correct_count += 1
                    self.correct_answers[index] = opt_index
        return correct_count

    async def _retry_quiz(self) -> bool:
        button = self.page.locator(RETRY_SELECTOR)
        try:
            if await button.count():
                if await self._safe_click(button.first, "ripeti quiz"):
                    await self._human_pause(0.45)
                    return True
        except PlaywrightError as exc:
            self.logger.debug("Quiz: click 'Ripeti' fallito: %s", exc)
        return False

    async def _wait_for_reset(self) -> None:
        await asyncio.sleep(self._adjusted_delay(1.0))
        questions = self.page.locator(QUIZ_CONTAINER_SELECTOR)
        try:
            for _ in range(3):
                pending = False
                count = await questions.count()
                for index in range(count):
                    options = questions.nth(index).locator(OPTION_SELECTOR)
                    for opt_index in range(await options.count()):
                        classes = await options.nth(opt_index).get_attribute("class")
                        tokens = set((classes or "").split())
                        if SELECTED_CLASS in tokens:
                            pending = True
                            break
                    if pending:
                        break
                if not pending:
                    return
                await asyncio.sleep(self._adjusted_delay(0.6))
        except PlaywrightError:
            return

    async def _human_review(self, total_questions: int) -> None:
        if total_questions == 0 or random.random() > 0.55:
            return
        question_index = random.randrange(total_questions)
        question = self.page.locator(QUIZ_CONTAINER_SELECTOR).nth(question_index)
        options = question.locator(OPTION_SELECTOR)
        try:
            option_count = await options.count()
        except PlaywrightError:
            return
        if option_count == 0:
            return
        target_index = random.randrange(option_count)
        try:
            await options.nth(target_index).hover()
            await self._human_pause(0.2)
        except PlaywrightError:
            return
        else:
            self.logger.debug(
                "Quiz: ricontrollata domanda %s prima dell'invio",
                question_index + 1,
            )

    async def _wait_for_feedback(self, total_questions: int) -> None:
        feedback_detected = False
        for attempt in range(6):
            if self.stop_event.is_set():
                return
            try:
                if await self.page.locator(RETRY_SELECTOR).count():
                    feedback_detected = True
                    break
            except PlaywrightError:
                pass
            if await self._has_feedback_marks(total_questions):
                feedback_detected = True
                break
            await self._human_pause(0.4)
        if not feedback_detected:
            self.logger.debug("Quiz: feedback non rilevato esplicitamente dopo l'invio")

    async def _has_feedback_marks(self, total_questions: int) -> bool:
        questions = self.page.locator(QUIZ_CONTAINER_SELECTOR)
        try:
            count = await questions.count()
        except PlaywrightError:
            return False
        count = min(count, total_questions)
        for index in range(count):
            options = questions.nth(index).locator(OPTION_SELECTOR)
            try:
                option_count = await options.count()
            except PlaywrightError:
                continue
            for opt_index in range(option_count):
                try:
                    classes = await options.nth(opt_index).get_attribute("class")
                except PlaywrightError:
                    continue
                tokens = set((classes or "").split())
                if WRONG_CLASS in tokens:
                    return True
        return False

    async def _safe_click(self, target: Locator, description: str) -> bool:
        for attempt in range(3):
            try:
                await target.scroll_into_view_if_needed(timeout=2000)
            except PlaywrightError:
                pass
            try:
                await target.click(timeout=2000, force=False)
            except PlaywrightError as exc:
                self.logger.debug(
                    "Quiz: click fallito (%s) al tentativo %s: %s",
                    description,
                    attempt + 1,
                    exc,
                )
                await self._human_pause(0.25)
                continue
            else:
                if attempt:
                    self.logger.debug(
                        "Quiz: click riuscito (%s) dopo %s tentativi",
                        description,
                        attempt + 1,
                    )
                return True
        self.logger.warning("Quiz: nessun click riuscito per %s", description)
        return False

    async def _human_pause(self, base: float) -> None:
        try:
            await asyncio.sleep(self._adjusted_delay(base))
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancellation
            pass

    def _adjusted_delay(self, base: float) -> float:
        base = max(0.05, base)
        if self.config.fast_mode:
            base *= 0.6
        jitter = base * 0.2
        lower = max(0.02, base - jitter)
        upper = base + jitter
        return random.uniform(lower, upper)
