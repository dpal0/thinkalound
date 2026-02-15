from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml


@lru_cache
def _load_prompts() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "config" / "prompts.yaml"
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("prompts.yaml must be a mapping.")
    return data


@lru_cache
def _load_config() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("config.yaml must be a mapping.")
    return data


def build_question_prompt(repo_meta: dict[str, Any], snippets: list[dict[str, Any]]):
    prompts = _load_prompts()
    config = _load_config()
    question_count = int(config.get("question_count", 5))
    categories = list(config.get("question_categories", ["why", "design", "tradeoff"]))

    prompt_cfg = prompts.get("question_generator", {})
    system_prompt, user_template = _extract_prompt_parts(prompt_cfg)
    user_content = user_template.format(
        repo_url=str(repo_meta.get("repo_url", "")),
        repo_owner=str(repo_meta.get("owner", "")),
        repo_name=str(repo_meta.get("name", "")),
        commit_sha=str(repo_meta.get("commit_sha", "")),
        snippets=_format_snippets(snippets),
        question_count=question_count,
        categories=", ".join(categories),
    )
    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_content.strip()},
    ]
    response_schema = _question_schema(question_count, categories, len(snippets))
    return {"messages": messages, "response_schema": response_schema}


def build_grader_prompt(question: dict[str, Any], excerpt: dict[str, Any], answer: str):
    prompts = _load_prompts()
    config = _load_config()
    prompt_cfg = prompts.get("grader", {})
    system_prompt, user_template = _extract_prompt_parts(prompt_cfg)
    user_content = user_template.format(
        question_text=str(question.get("question_text", "")).strip(),
        snippet=_format_snippet(excerpt),
        answer_text=str(answer or "").strip(),
    )
    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_content.strip()},
    ]
    response_schema = _grade_schema(config)
    return {"messages": messages, "response_schema": response_schema}


def build_snippet_select_prompt(
    repo_meta: dict[str, Any],
    snippets: list[dict[str, Any]],
    selection_count: int,
):
    prompts = _load_prompts()
    prompt_cfg = prompts.get("snippet_selector", {})
    system_prompt, user_template = _extract_prompt_parts(prompt_cfg)
    user_content = user_template.format(
        repo_url=str(repo_meta.get("repo_url", "")),
        repo_owner=str(repo_meta.get("owner", "")),
        repo_name=str(repo_meta.get("name", "")),
        commit_sha=str(repo_meta.get("commit_sha", "")),
        snippets=_format_snippets(snippets),
        selection_count=selection_count,
    )
    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_content.strip()},
    ]
    response_schema = _snippet_selection_schema(selection_count, len(snippets))
    return {"messages": messages, "response_schema": response_schema}


def normalize_grade(payload: Mapping[str, Any]) -> dict[str, Any]:
    config = _load_config()
    grading_cfg = config.get("grading", {})
    min_score = int(grading_cfg.get("min_score", 1))
    max_score = int(grading_cfg.get("max_score", 5))
    min_conf = float(grading_cfg.get("min_confidence", 0.0))
    max_conf = float(grading_cfg.get("max_confidence", 1.0))
    default_conf = float(grading_cfg.get("default_confidence", 0.5))

    score = _normalize_score(payload.get("score"), min_score, max_score)
    confidence = _normalize_confidence(payload.get("confidence"), min_conf, max_conf, default_conf)
    rationale = str(payload.get("rationale", "")).strip()
    return {"score": score, "confidence": confidence, "rationale": rationale}


def validate_llm_response(response: Any, response_schema: Mapping[str, Any]):
    errors: list[str] = []
    data = _validate_node(response, response_schema, path="$", errors=errors)
    return {"ok": not errors, "data": data, "errors": errors}


def _extract_prompt_parts(prompt_cfg: Any) -> tuple[str, str]:
    if isinstance(prompt_cfg, str):
        return prompt_cfg, "{snippets}"
    if isinstance(prompt_cfg, dict):
        return str(prompt_cfg.get("system", "")), str(prompt_cfg.get("user_template", ""))
    return "", "{snippets}"


def _format_snippets(snippets: list[dict[str, Any]]) -> str:
    return "\n\n".join(_format_snippet(snippet, index) for index, snippet in enumerate(snippets))


def _format_snippet(snippet: Mapping[str, Any], index: int | None = None) -> str:
    header = f"Snippet {index}:" if index is not None else "Snippet:"
    file_path = snippet.get("file_path", "")
    line_start = snippet.get("line_start", "")
    line_end = snippet.get("line_end", "")
    excerpt_text = snippet.get("excerpt_text", "")
    return "\n".join(
        [
            header,
            f"path: {file_path}",
            f"lines: {line_start}-{line_end}",
            "```",
            str(excerpt_text),
            "```",
        ]
    )


def _question_schema(count: int, categories: list[str], snippet_count: int) -> dict[str, Any]:
    index_schema: dict[str, Any] = {"type": "integer", "min": 0}
    if snippet_count > 0:
        index_schema["max"] = snippet_count - 1
    return {
        "type": "object",
        "required": ["questions"],
        "properties": {
            "questions": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "required": ["question_text", "snippet_index", "category"],
                    "properties": {
                        "question_text": {"type": "string"},
                        "snippet_index": index_schema,
                        "category": {"type": "string", "enum": categories},
                    },
                },
            }
        },
    }


def _grade_schema(config: Mapping[str, Any]) -> dict[str, Any]:
    grading_cfg = config.get("grading", {})
    return {
        "type": "object",
        "required": ["score", "rationale", "confidence"],
        "properties": {
            "score": {
                "type": "integer",
                "min": int(grading_cfg.get("min_score", 1)),
                "max": int(grading_cfg.get("max_score", 5)),
            },
            "rationale": {"type": "string"},
            "confidence": {
                "type": "number",
                "min": float(grading_cfg.get("min_confidence", 0.0)),
                "max": float(grading_cfg.get("max_confidence", 1.0)),
            },
        },
    }


def _snippet_selection_schema(selection_count: int, snippet_count: int) -> dict[str, Any]:
    index_schema: dict[str, Any] = {"type": "integer", "min": 0}
    if snippet_count > 0:
        index_schema["max"] = snippet_count - 1
    return {
        "type": "object",
        "required": ["selected_indices"],
        "properties": {
            "selected_indices": {
                "type": "array",
                "minItems": selection_count,
                "maxItems": selection_count,
                "items": index_schema,
            }
        },
    }


def _validate_node(value: Any, schema: Mapping[str, Any], path: str, errors: list[str]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            errors.append(f"{path} expected object")
            return {}
        result: dict[str, Any] = {}
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        for key, prop_schema in properties.items():
            if key in value:
                result[key] = _validate_node(value[key], prop_schema, f"{path}.{key}", errors)
        return result
    if schema_type == "array":
        if not isinstance(value, list):
            errors.append(f"{path} expected array")
            return []
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path} expected at least {min_items} items")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path} expected at most {max_items} items")
        item_schema = schema.get("items", {})
        return [
            _validate_node(item, item_schema, f"{path}[{index}]", errors)
            for index, item in enumerate(value)
        ]
    if schema_type == "string":
        if isinstance(value, str):
            if "enum" in schema and value not in schema["enum"]:
                errors.append(f"{path} must be one of {schema['enum']}")
            return value
        errors.append(f"{path} expected string")
        return ""
    if schema_type == "integer":
        coerced = _coerce_number(value, path, errors)
        if coerced is None:
            return 0
        integer_value = int(round(coerced))
        _validate_number_bounds(integer_value, schema, path, errors)
        return integer_value
    if schema_type == "number":
        coerced = _coerce_number(value, path, errors)
        if coerced is None:
            return 0.0
        _validate_number_bounds(coerced, schema, path, errors)
        return float(coerced)
    return value


def _coerce_number(value: Any, path: str, errors: list[str]) -> float | None:
    if isinstance(value, bool):
        errors.append(f"{path} expected number, got bool")
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            errors.append(f"{path} expected number, got string")
            return None
    errors.append(f"{path} expected number")
    return None


def _validate_number_bounds(value: float, schema: Mapping[str, Any], path: str, errors: list[str]) -> None:
    min_value = schema.get("min")
    max_value = schema.get("max")
    if min_value is not None and value < min_value:
        errors.append(f"{path} must be >= {min_value}")
    if max_value is not None and value > max_value:
        errors.append(f"{path} must be <= {max_value}")


def _normalize_score(score: Any, min_score: int, max_score: int) -> int:
    try:
        numeric = int(round(float(score)))
    except (TypeError, ValueError):
        return min_score
    return max(min_score, min(max_score, numeric))


def _normalize_confidence(
    confidence: Any, min_conf: float, max_conf: float, default_conf: float
) -> float:
    try:
        numeric = float(confidence)
    except (TypeError, ValueError):
        return default_conf
    if numeric < min_conf:
        return min_conf
    if numeric > max_conf:
        return max_conf
    return numeric
