from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from flask import Flask, Response, g, jsonify, request
from sqlalchemy import select

from config import AppConfig
from db import session_scope
from db.models import Answer, Grade, IntegrityEvent, Question, Repo, Submission, User
from app.tasks import TaskQueue
from db.storage import (
    cleanup_unanswered_questions,
    create_answer,
    create_integrity_event,
    create_questions,
    create_submission,
    get_oauth_token,
    get_user_by_id,
    get_or_create_repo,
)
from llm.interface import generate_questions
from services.grading import grade_answers_batch
from services.github import GitHubClient
from services.ingestion import ingest_repo


def register_routes(app: Flask) -> None:
    @app.post("/repos/verify")
    def verify_repo() -> tuple[Response, int]:
        data = _require_json(request.get_json(silent=True))
        repo_url = _require_field(data, "repo_url")
        config: AppConfig = app.config["APP_CONFIG"]
        with session_scope() as session:
            token = get_oauth_token(session, g.user_id)
        if not token:
            return jsonify({"error": "Missing GitHub token."}), 401
        client = GitHubClient(config.github, token=token)
        metadata = client.verify_repo_url(repo_url)
        if not metadata.is_personal:
            return jsonify({"error": "Only personal repos are supported."}), 400
        if metadata.owner_login and metadata.owner_login != g.github_login:
            return jsonify({"error": "Repo owner does not match authenticated user."}), 403
        if metadata.permissions and not metadata.permissions.get("pull", False):
            return jsonify({"error": "No read access to repository."}), 403
        return jsonify({"ok": True, "owner": metadata.owner, "name": metadata.name}), 200

    @app.post("/submissions")
    def create_submission_route() -> tuple[Response, int]:
        data = _require_json(request.get_json(silent=True))
        repo_url = _require_field(data, "repo_url")
        commit_sha = data.get("commit_sha")
        if commit_sha is not None:
            if not isinstance(commit_sha, str):
                return jsonify({"error": "commit_sha must be a string."}), 400
            commit_sha = commit_sha.strip() or None
        config: AppConfig = app.config["APP_CONFIG"]

        with session_scope() as session:
            user = get_user_by_id(session, g.user_id)
            if not user:
                return jsonify({"error": "User not found."}), 401
            token = get_oauth_token(session, g.user_id)
        if not token:
            return jsonify({"error": "Missing GitHub token."}), 401

        ingestion = ingest_repo(repo_url, config, token=token, commit_sha=commit_sha)
        if not ingestion.snippets:
            return jsonify({"error": "No code snippets found in repo."}), 400
        if ingestion.owner != g.github_login:
            return jsonify({"error": "Repo owner does not match authenticated user."}), 403
        repo_meta = {
            "repo_url": repo_url,
            "owner": ingestion.owner,
            "name": ingestion.name,
            "commit_sha": ingestion.commit_sha,
        }
        generated = generate_questions(ingestion.snippets, config, repo_meta=repo_meta)

        manifest_json = {"files": [repo_file.path for repo_file in ingestion.files]}

        with session_scope() as session:
            user = get_user_by_id(session, g.user_id)
            if not user:
                return jsonify({"error": "User not found."}), 401
            repo = get_or_create_repo(
                session,
                user_id=user.id,
                repo_url=repo_url,
                owner=ingestion.owner,
                name=ingestion.name,
            )
            cleanup_unanswered_questions(session, repo.id)
            submission = create_submission(
                session,
                user_id=user.id,
                repo_id=repo.id,
                commit_sha=ingestion.commit_sha,
                manifest_json=manifest_json,
            )
            questions = [
                Question(
                    question_text=q.question_text,
                    file_path=q.file_path,
                    line_start=q.line_start,
                    line_end=q.line_end,
                    excerpt_text=q.excerpt_text,
                    excerpt_hash=q.excerpt_hash,
                    user_id=user.id,
                )
                for q in generated
            ]
            create_questions(session, submission.id, user.id, questions)

            response_questions = [
                {
                    "id": str(question.id),
                    "text": question.question_text,
                    "file_path": question.file_path,
                    "line_start": question.line_start,
                    "line_end": question.line_end,
                    "excerpt": question.excerpt_text,
                }
                for question in questions
            ]

        return (
            jsonify(
                {
                    "submission_id": str(submission.id),
                    "status": "ready",
                    "questions": response_questions,
                }
            ),
            200,
        )

    @app.get("/submissions/<submission_id>/questions")
    def get_questions(submission_id: str) -> tuple[Response, int]:
        submission_uuid = _parse_uuid(submission_id)
        with session_scope() as session:
            submission = session.execute(
                select(Submission).where(Submission.id == submission_uuid)
            ).scalar_one_or_none()
            if not submission:
                return jsonify({"error": "Submission not found."}), 404
            if submission.user_id != g.user_id:
                return jsonify({"error": "Forbidden."}), 403
            stmt = select(Question).where(Question.submission_id == submission_uuid)
            questions = session.execute(stmt).scalars().all()
            response_questions = [
                {
                    "id": str(question.id),
                    "text": question.question_text,
                    "file_path": question.file_path,
                    "line_start": question.line_start,
                    "line_end": question.line_end,
                    "excerpt": question.excerpt_text,
                }
                for question in questions
            ]
        return jsonify({"questions": response_questions}), 200

    @app.post("/answers")
    def submit_answers() -> tuple[Response, int]:
        data = _require_json(request.get_json(silent=True))
        answers_payload = data.get("answers")
        if not isinstance(answers_payload, list) or not answers_payload:
            return jsonify({"error": "answers must be a non-empty list."}), 400

        task_queue: TaskQueue | None = app.config.get("TASK_QUEUE")

        parsed_payload: list[dict[str, Any]] = []
        for item in answers_payload:
            if not isinstance(item, dict):
                return jsonify({"error": "Each answer must be an object."}), 400
            parsed_payload.append(item)

        results: list[dict[str, Any]] = []
        pending_answer_ids: list[uuid.UUID] = []
        submission_id_for_batch: uuid.UUID | None = None
        with session_scope() as session:
            validated: list[tuple[dict[str, Any], Submission, Question]] = []
            for payload in parsed_payload:
                submission_id = _parse_uuid(_require_field(payload, "submission_id"))
                question_id = _parse_uuid(_require_field(payload, "question_id"))
                submission = session.execute(
                    select(Submission).where(Submission.id == submission_id)
                ).scalar_one_or_none()
                if not submission:
                    return jsonify({"error": "Submission not found."}), 404
                if submission.user_id != g.user_id:
                    return jsonify({"error": "Forbidden."}), 403
                if submission_id_for_batch is None:
                    submission_id_for_batch = submission_id
                elif submission_id_for_batch != submission_id:
                    return jsonify({"error": "All answers must share the same submission_id."}), 400
                question = session.execute(
                    select(Question).where(
                        Question.id == question_id,
                        Question.submission_id == submission_id,
                    )
                ).scalar_one_or_none()
                if not question:
                    return jsonify({"error": "Question not found."}), 404
                validated.append((payload, submission, question))

            for payload, submission, question in validated:
                answer_text = _require_text(payload, "answer_text")
                time_spent_ms = int(payload.get("time_spent_ms", 0))
                paste_attempts = int(payload.get("paste_attempts", 0))
                focus_loss_count = int(payload.get("focus_loss_count", 0))
                typing_stats = payload.get("typing_stats", None)

                answer = create_answer(
                    session,
                    question_id=question.id,
                    submission_id=submission.id,
                    user_id=g.user_id,
                    answer_text=answer_text,
                    time_spent_ms=time_spent_ms,
                    paste_attempts=paste_attempts,
                    focus_loss_count=focus_loss_count,
                    typing_stats_json=typing_stats,
                )
                pending_answer_ids.append(answer.id)

                if not answer_text.strip():
                    create_integrity_event(
                        session,
                        submission_id=submission.id,
                        question_id=question.id,
                        user_id=g.user_id,
                        event_type="blank_answer",
                        event_data={"integrity_score": 0},
                    )

                results.append(
                    {
                        "answer_id": str(answer.id),
                        "question_id": str(question.id),
                        "status": "queued",
                    }
                )

        if submission_id_for_batch is not None:
            if task_queue is not None:
                task_queue.submit(grade_answers_batch, submission_id_for_batch, pending_answer_ids)
            else:
                grade_answers_batch(submission_id_for_batch, pending_answer_ids)

        return jsonify({"answers": results}), 202

    @app.get("/submissions/<submission_id>/grades")
    def get_grades(submission_id: str) -> tuple[Response, int]:
        submission_uuid = _parse_uuid(submission_id)
        with session_scope() as session:
            submission = session.execute(
                select(Submission).where(Submission.id == submission_uuid)
            ).scalar_one_or_none()
            if not submission:
                return jsonify({"error": "Submission not found."}), 404
            if submission.user_id != g.user_id:
                return jsonify({"error": "Forbidden."}), 403
            stmt = (
                select(Grade, Answer)
                .join(Answer, Grade.answer_id == Answer.id)
                .where(Answer.submission_id == submission_uuid)
            )
            rows = session.execute(stmt).all()
            grades = [
                {
                    "answer_id": str(answer.id),
                    "score": grade.score,
                    "rationale": grade.rationale,
                    "confidence": grade.confidence,
                }
                for grade, answer in rows
            ]
        return jsonify({"grades": grades}), 200

    @app.get("/exports/submissions.csv")
    def export_csv() -> Response:
        config: AppConfig = app.config["APP_CONFIG"]
        if g.github_login not in config.instructors:
            return jsonify({"error": "Instructor access required."}), 403
        with session_scope() as session:
            rows = session.execute(
                select(Answer, Question, Submission, Repo, User, Grade)
                .join(Question, Answer.question_id == Question.id)
                .join(Submission, Answer.submission_id == Submission.id)
                .join(Repo, Submission.repo_id == Repo.id)
                .join(User, Submission.user_id == User.id)
                .join(Grade, Grade.answer_id == Answer.id, isouter=True)
            ).all()
            integrity = session.execute(select(IntegrityEvent)).scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "user_id",
                "github_login",
                "repo_url",
                "repo_owner",
                "repo_name",
                "commit_sha",
                "submission_id",
                "question_id",
                "question_text",
                "file_path",
                "line_start",
                "line_end",
                "answer_id",
                "answer_text",
                "score",
                "rationale",
                "confidence",
                "grade_model",
                "paste_attempts",
                "focus_loss_count",
                "time_spent_ms",
            ]
        )
        for answer, question, submission, repo, user, grade in rows:
            writer.writerow(
                [
                    str(user.id),
                    user.github_login,
                    repo.repo_url,
                    repo.owner,
                    repo.name,
                    submission.commit_sha,
                    str(answer.submission_id),
                    str(answer.question_id),
                    question.question_text,
                    question.file_path,
                    question.line_start,
                    question.line_end,
                    str(answer.id),
                    answer.answer_text,
                    grade.score if grade else "",
                    grade.rationale if grade else "",
                    grade.confidence if grade else "",
                    grade.model if grade else "",
                    answer.paste_attempts,
                    answer.focus_loss_count,
                    answer.time_spent_ms,
                ]
            )

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=submissions.csv"},
        )


def _require_json(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("JSON body required.")
    return data


def _require_field(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid field: {field}")
    return value.strip()


def _require_text(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str):
        raise ValueError(f"Missing or invalid field: {field}")
    return value


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError("Invalid UUID.") from exc
