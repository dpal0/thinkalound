from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

import requests
import yaml

from config import AppConfig
from llm.module import (
    build_grader_prompt,
    build_question_prompt,
    build_snippet_select_prompt,
    normalize_grade,
    validate_llm_response,
)
from services.snippets import Snippet

_LOGGER = logging.getLogger(__name__)
_LAST_CALL_TS = 0.0


@dataclass(frozen=True)
class GeneratedQuestion:
    question_text: str
    file_path: str
    line_start: int
    line_end: int
    excerpt_text: str
    excerpt_hash: str


@dataclass(frozen=True)
class GradeResult:
    score: int
    rationale: str
    confidence: float
    model: str


def generate_questions(
    snippets: list[Snippet],
    config: AppConfig,
    repo_meta: dict[str, Any] | None = None,
) -> list[GeneratedQuestion]:
    if not snippets:
        return []
    repo_meta = repo_meta or {}
    llm_snippets = _cap_snippets(snippets)
    snippet_payload = [_snippet_payload(snippet) for snippet in llm_snippets]

    api_key = _get_api_key()
    if not api_key:
        _LOGGER.info("LLM API key missing; using fallback question generation.")
        return _fallback_questions(llm_snippets, config)

    prompt = build_question_prompt(repo_meta, snippet_payload)
    response = _call_llm(prompt["messages"], prompt["response_schema"], api_key)
    if response is None:
        return _fallback_questions(llm_snippets, config)

    questions_payload = response.get("questions", [])
    return _map_questions(questions_payload, llm_snippets, config)


def select_relevant_snippets(
    snippets: list[Snippet],
    config: AppConfig,
    repo_meta: dict[str, Any] | None = None,
) -> list[Snippet]:
    if not snippets:
        return []
    repo_meta = repo_meta or {}
    candidates = _cap_candidates(snippets, config)
    selection_count = min(config.snippets.selection_count, len(candidates))
    if selection_count <= 0:
        return []

    api_key = _get_api_key()
    if not api_key:
        _LOGGER.info("LLM API key missing; using fallback snippet selection.")
        return candidates[:selection_count]

    snippet_payload = [_snippet_payload(snippet) for snippet in candidates]
    prompt = build_snippet_select_prompt(repo_meta, snippet_payload, selection_count)
    response = _call_llm(prompt["messages"], prompt["response_schema"], api_key)
    if response is None:
        return candidates[:selection_count]

    selected_indices = response.get("selected_indices", [])
    selected: list[Snippet] = []
    seen: set[int] = set()
    for raw in selected_indices:
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(candidates) and idx not in seen:
            selected.append(candidates[idx])
            seen.add(idx)
        if len(selected) >= selection_count:
            break

    if len(selected) < selection_count:
        for candidate in candidates:
            if candidate in selected:
                continue
            selected.append(candidate)
            if len(selected) >= selection_count:
                break

    return selected


def grade_answer(answer_text: str, question: GeneratedQuestion) -> GradeResult:
    if not answer_text.strip():
        grading = _grading_config()
        min_score = int(grading.get("min_score", 1))
        default_conf = float(grading.get("default_confidence", 0.5))
        return GradeResult(
            score=min_score,
            rationale="Blank answer.",
            confidence=default_conf,
            model="fallback",
        )

    api_key = _get_api_key()
    if not api_key:
        _LOGGER.info("LLM API key missing; using fallback grading.")
        grading = _grading_config()
        return GradeResult(
            score=int(grading.get("min_score", 1)),
            rationale="LLM unavailable; fallback grading applied.",
            confidence=float(grading.get("default_confidence", 0.5)),
            model="fallback",
        )

    excerpt = _snippet_payload(
        Snippet(
            file_path=question.file_path,
            line_start=question.line_start,
            line_end=question.line_end,
            excerpt_text=question.excerpt_text,
            excerpt_hash=question.excerpt_hash,
        )
    )
    prompt = build_grader_prompt(
        question={"question_text": question.question_text},
        excerpt=excerpt,
        answer=answer_text,
    )
    response = _call_llm(prompt["messages"], prompt["response_schema"], api_key)
    if response is None:
        grading = _grading_config()
        return GradeResult(
            score=int(grading.get("min_score", 1)),
            rationale="LLM failure; fallback grading applied.",
            confidence=float(grading.get("default_confidence", 0.5)),
            model="fallback",
        )
    normalized = normalize_grade(response)
    return GradeResult(
        score=normalized["score"],
        rationale=normalized["rationale"],
        confidence=normalized["confidence"],
        model=_llm_config().get("model", "openai"),
    )


def _call_llm(
    messages: list[dict[str, str]],
    response_schema: dict[str, Any],
    api_key: str,
) -> dict[str, Any] | None:
    llm_cfg = _llm_config()
    api_base = llm_cfg.get("api_base", "https://api.openai.com/v1")
    model = llm_cfg.get("model", "gpt-4o-mini")
    temperature = float(llm_cfg.get("temperature", 0.2))
    max_output_tokens = llm_cfg.get("max_output_tokens")
    timeout_seconds = float(llm_cfg.get("timeout_seconds", 30.0))
    max_retries = int(llm_cfg.get("max_retries", 2))
    backoff = float(llm_cfg.get("retry_backoff_seconds", 1.0))

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    if max_output_tokens is not None:
        payload["max_completion_tokens"] = int(max_output_tokens)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{api_base.rstrip('/')}/chat/completions"

    for attempt in range(max_retries + 1):
        _respect_rate_limit()
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
        except requests.RequestException as exc:
            _LOGGER.warning("LLM request failed: %s", exc)
            if attempt >= max_retries:
                return None
            time.sleep(backoff * (attempt + 1))
            continue

        if response.status_code in (429, 500, 502, 503, 504):
            _LOGGER.warning("LLM response status %s", response.status_code)
            if attempt >= max_retries:
                return None
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else backoff * (attempt + 1)
                _LOGGER.info("Rate limited; waiting %.1fs before retry.", wait)
            else:
                wait = backoff * (attempt + 1)
            time.sleep(wait)
            continue

        if response.status_code >= 400:
            _LOGGER.error("LLM error status %s: %s", response.status_code, response.text)
            return None

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            _LOGGER.warning("LLM response parse failed: %s", exc)
            if attempt >= max_retries:
                return None
            time.sleep(backoff * (attempt + 1))
            continue

        validation = validate_llm_response(parsed, response_schema)
        if not validation["ok"]:
            _LOGGER.warning("LLM schema validation failed: %s", validation["errors"])
            if attempt >= max_retries:
                return None
            time.sleep(backoff * (attempt + 1))
            continue

        return validation["data"]
    return None


def _snippet_payload(snippet: Snippet) -> dict[str, Any]:
    return {
        "file_path": snippet.file_path,
        "line_start": snippet.line_start,
        "line_end": snippet.line_end,
        "excerpt_text": snippet.excerpt_text,
        "excerpt_hash": snippet.excerpt_hash,
    }


def _map_questions(
    questions_payload: list[dict[str, Any]],
    snippets: list[Snippet],
    config: AppConfig,
) -> list[GeneratedQuestion]:
    questions: list[GeneratedQuestion] = []
    for question in questions_payload:
        index = int(question.get("snippet_index", 0))
        if index < 0 or index >= len(snippets):
            continue
        snippet = snippets[index]
        questions.append(
            GeneratedQuestion(
                question_text=str(question.get("question_text", "")).strip(),
                file_path=snippet.file_path,
                line_start=snippet.line_start,
                line_end=snippet.line_end,
                excerpt_text=snippet.excerpt_text,
                excerpt_hash=snippet.excerpt_hash,
            )
        )
    if len(questions) < config.question_count:
        questions.extend(
            _fallback_questions(snippets, config)[len(questions) : config.question_count]
        )
    return questions[: config.question_count]


def _fallback_questions(snippets: list[Snippet], config: AppConfig) -> list[GeneratedQuestion]:
    categories = _question_categories()
    if not snippets:
        return []
    questions: list[GeneratedQuestion] = []
    for idx in range(config.question_count):
        snippet = snippets[idx % len(snippets)]
        category = categories[idx % len(categories)]
        question_text = _fallback_question_text(snippet, category)
        questions.append(
            GeneratedQuestion(
                question_text=question_text,
                file_path=snippet.file_path,
                line_start=snippet.line_start,
                line_end=snippet.line_end,
                excerpt_text=snippet.excerpt_text,
                excerpt_hash=snippet.excerpt_hash,
            )
        )
    return questions


def _fallback_question_text(snippet: Snippet, category: str) -> str:
    base = f"In `{snippet.file_path}` (lines {snippet.line_start}-{snippet.line_end})"
    if category == "design":
        return f"{base}, what design choice does this code reflect?"
    if category == "tradeoff":
        return f"{base}, what tradeoff does this implementation make?"
    return f"{base}, explain why this code works."


def _cap_snippets(snippets: list[Snippet]) -> list[Snippet]:
    max_snippets = int(_llm_config().get("max_snippets", 0))
    if max_snippets <= 0:
        return snippets
    return snippets[:max_snippets]


def _cap_candidates(snippets: list[Snippet], config: AppConfig) -> list[Snippet]:
    if config.snippets.max_candidates <= 0:
        return snippets
    return snippets[: config.snippets.max_candidates]


def _load_raw_config() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        return {}
    return data


def _llm_config() -> dict[str, Any]:
    raw = _load_raw_config()
    return raw.get("llm", {}) if isinstance(raw.get("llm", {}), dict) else {}


def _grading_config() -> dict[str, Any]:
    raw = _load_raw_config()
    return raw.get("grading", {}) if isinstance(raw.get("grading", {}), dict) else {}


def _question_categories() -> list[str]:
    raw = _load_raw_config()
    categories = raw.get("question_categories", ["why", "design", "tradeoff"])
    if not isinstance(categories, list) or not categories:
        return ["why", "design", "tradeoff"]
    return [str(item) for item in categories]


def _get_api_key() -> str | None:
    provider = _llm_config().get("provider", "openai")
    if provider == "gemini":
        return os.environ.get("GEMINI_API_KEY")
    if provider == "openai":
        return os.environ.get("OPENAI_API_KEY")
    _LOGGER.warning("Unsupported LLM provider: %s", provider)
    return None


def _respect_rate_limit() -> None:
    global _LAST_CALL_TS
    llm_cfg = _llm_config()
    rpm = float(llm_cfg.get("rate_limit_per_minute", 0))
    if rpm <= 0:
        return
    min_interval = 60.0 / rpm
    now = time.monotonic()
    elapsed = now - _LAST_CALL_TS
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _LAST_CALL_TS = time.monotonic()
