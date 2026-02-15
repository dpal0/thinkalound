from __future__ import annotations

import logging
import time

from sqlalchemy import select

from db import session_scope
from db.models import Answer, Grade, Question
from db.storage import create_grade
from llm.interface import GeneratedQuestion, grade_answer

_LOGGER = logging.getLogger(__name__)


def grade_answer_task(answer_id) -> None:
    with session_scope() as session:
        answer = session.execute(select(Answer).where(Answer.id == answer_id)).scalar_one_or_none()
        if not answer:
            _LOGGER.warning("Answer %s not found for grading.", answer_id)
            return
        existing = session.execute(
            select(Grade).where(Grade.answer_id == answer_id)
        ).scalar_one_or_none()
        if existing:
            return
        question = session.execute(
            select(Question).where(Question.id == answer.question_id)
        ).scalar_one_or_none()
        if not question:
            _LOGGER.warning("Question %s not found for grading.", answer.question_id)
            return

        question_context = GeneratedQuestion(
            question_text=question.question_text,
            file_path=question.file_path,
            line_start=question.line_start,
            line_end=question.line_end,
            excerpt_text=question.excerpt_text,
            excerpt_hash=question.excerpt_hash,
        )
        grade = grade_answer(answer.answer_text, question_context)
        create_grade(
            session,
            answer_id=answer.id,
            user_id=answer.user_id,
            score=grade.score,
            rationale=grade.rationale,
            confidence=grade.confidence,
            model=grade.model,
        )


def grade_answers_batch(submission_id, answer_ids: list) -> None:
    _LOGGER.info(
        "Starting grading for submission %s (%s answers).",
        submission_id,
        len(answer_ids),
    )
    for i, answer_id in enumerate(answer_ids):
        if i > 0:
            time.sleep(3)  # Space out LLM calls to avoid rate limits
        grade_answer_task(answer_id)
    _LOGGER.info(
        "Completed grading for submission %s (%s answers).",
        submission_id,
        len(answer_ids),
    )
