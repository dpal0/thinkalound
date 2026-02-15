from __future__ import annotations

from typing import Iterable

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from auth.crypto import decrypt_token, encrypt_token
from db.models import (
    Answer,
    Grade,
    IntegrityEvent,
    OauthState,
    OauthToken,
    Question,
    Repo,
    Submission,
    User,
)


def get_or_create_user(session: Session, github_user_id: str, github_login: str) -> User:
    stmt = select(User).where(User.github_user_id == github_user_id)
    user = session.execute(stmt).scalar_one_or_none()
    if user:
        return user
    user = User(github_user_id=github_user_id, github_login=github_login)
    session.add(user)
    session.flush()
    return user


def upsert_user(
    session: Session,
    github_user_id: str,
    github_login: str,
    name: str | None,
    email: str | None,
) -> User:
    stmt = select(User).where(User.github_user_id == github_user_id)
    user = session.execute(stmt).scalar_one_or_none()
    if user:
        user.github_login = github_login
        user.name = name
        user.email = email
        session.flush()
        return user
    user = User(
        github_user_id=github_user_id,
        github_login=github_login,
        name=name,
        email=email,
    )
    session.add(user)
    session.flush()
    return user


def get_user_by_id(session: Session, user_id) -> User | None:
    return session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()


def upsert_oauth_token(session: Session, user_id, access_token: str) -> OauthToken:
    session.execute(delete(OauthToken).where(OauthToken.user_id == user_id))
    token = OauthToken(user_id=user_id, access_token=encrypt_token(access_token))
    session.add(token)
    session.flush()
    return token


def get_oauth_token(session: Session, user_id) -> str | None:
    token = session.execute(
        select(OauthToken).where(OauthToken.user_id == user_id)
    ).scalar_one_or_none()
    if not token:
        return None
    return decrypt_token(token.access_token)


def create_oauth_state(session: Session, state: str) -> None:
    session.add(OauthState(state=state))
    session.flush()


def consume_oauth_state(session: Session, state: str) -> bool:
    existing = session.execute(
        select(OauthState).where(OauthState.state == state)
    ).scalar_one_or_none()
    if not existing:
        return False
    session.execute(delete(OauthState).where(OauthState.state == state))
    return True

def get_or_create_repo(
    session: Session,
    user_id,
    repo_url: str,
    owner: str,
    name: str,
) -> Repo:
    stmt = select(Repo).where(Repo.user_id == user_id, Repo.repo_url == repo_url)
    repo = session.execute(stmt).scalar_one_or_none()
    if repo:
        return repo
    repo = Repo(user_id=user_id, repo_url=repo_url, owner=owner, name=name)
    session.add(repo)
    session.flush()
    return repo


def create_submission(
    session: Session,
    user_id,
    repo_id,
    commit_sha: str,
    manifest_json: dict,
) -> Submission:
    submission = Submission(
        user_id=user_id,
        repo_id=repo_id,
        commit_sha=commit_sha,
        manifest_json=manifest_json,
        status="ready",
    )
    session.add(submission)
    session.flush()
    return submission


def create_questions(
    session: Session, submission_id, user_id, questions: Iterable[Question]
) -> None:
    for question in questions:
        question.submission_id = submission_id
        question.user_id = user_id
        session.add(question)
    session.flush()


def create_answer(
    session: Session,
    question_id,
    submission_id,
    user_id,
    answer_text: str,
    time_spent_ms: int,
    paste_attempts: int,
    focus_loss_count: int,
    typing_stats_json: dict | None,
) -> Answer:
    answer = Answer(
        question_id=question_id,
        submission_id=submission_id,
        user_id=user_id,
        answer_text=answer_text,
        time_spent_ms=time_spent_ms,
        paste_attempts=paste_attempts,
        focus_loss_count=focus_loss_count,
        typing_stats_json=typing_stats_json,
    )
    session.add(answer)
    session.flush()
    return answer


def create_grade(
    session: Session,
    answer_id,
    user_id,
    score: int,
    rationale: str,
    confidence: float,
    model: str,
) -> Grade:
    grade = Grade(
        answer_id=answer_id,
        user_id=user_id,
        score=score,
        rationale=rationale,
        confidence=confidence,
        model=model,
    )
    session.add(grade)
    session.flush()
    return grade


def create_integrity_event(
    session: Session,
    submission_id,
    question_id,
    user_id,
    event_type: str,
    event_data: dict | None,
) -> IntegrityEvent:
    event = IntegrityEvent(
        submission_id=submission_id,
        question_id=question_id,
        user_id=user_id,
        event_type=event_type,
        event_data=event_data,
    )
    session.add(event)
    session.flush()
    return event


def cleanup_unanswered_questions(session: Session, repo_id) -> dict[str, int]:
    question_ids = session.execute(
        select(Question.id)
        .join(Submission, Question.submission_id == Submission.id)
        .where(Submission.repo_id == repo_id)
        .outerjoin(Answer, Answer.question_id == Question.id)
        .where(Answer.id.is_(None))
    ).scalars().all()

    deleted_questions = 0
    deleted_events = 0
    deleted_submissions = 0

    if question_ids:
        deleted_events += session.execute(
            delete(IntegrityEvent).where(IntegrityEvent.question_id.in_(question_ids))
        ).rowcount or 0
        deleted_questions += session.execute(
            delete(Question).where(Question.id.in_(question_ids))
        ).rowcount or 0

    submission_ids = session.execute(
        select(Submission.id)
        .where(Submission.repo_id == repo_id)
        .where(~exists(select(Answer.id).where(Answer.submission_id == Submission.id)))
        .where(~exists(select(Question.id).where(Question.submission_id == Submission.id)))
    ).scalars().all()

    if submission_ids:
        deleted_events += session.execute(
            delete(IntegrityEvent).where(IntegrityEvent.submission_id.in_(submission_ids))
        ).rowcount or 0
        deleted_submissions += session.execute(
            delete(Submission).where(Submission.id.in_(submission_ids))
        ).rowcount or 0

    return {
        "deleted_questions": deleted_questions,
        "deleted_events": deleted_events,
        "deleted_submissions": deleted_submissions,
    }
