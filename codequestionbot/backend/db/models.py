from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_user_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    github_login: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    repos: Mapped[list["Repo"]] = relationship(back_populates="user")


class OauthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()


class OauthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="repos")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="repo")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"))
    commit_sha: Mapped[str] = mapped_column(String, nullable=False)
    manifest_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ready")
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    repo: Mapped["Repo"] = relationship(back_populates="submissions")
    questions: Mapped[list["Question"]] = relationship(back_populates="submission")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("submissions.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    line_start: Mapped[int] = mapped_column(nullable=False)
    line_end: Mapped[int] = mapped_column(nullable=False)
    excerpt_text: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    submission: Mapped["Submission"] = relationship(back_populates="questions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="question")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"))
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("submissions.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    time_spent_ms: Mapped[int] = mapped_column(nullable=False, default=0)
    paste_attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    focus_loss_count: Mapped[int] = mapped_column(nullable=False, default=0)
    typing_stats_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    question: Mapped["Question"] = relationship(back_populates="answers")


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("answers.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    score: Mapped[int] = mapped_column(nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    answer: Mapped["Answer"] = relationship()


class IntegrityEvent(Base):
    __tablename__ = "integrity_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("submissions.id"))
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )
