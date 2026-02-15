from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class GitHubConfig:
    api_base: str
    timeout_seconds: float


@dataclass(frozen=True)
class SnippetConfig:
    allowed_extensions: list[str]
    excluded_dirs: list[str]
    max_file_size_kb: int
    snippet_max_lines: int
    snippet_context_lines: int
    max_snippets_per_file: int
    selection_count: int
    max_candidates: int


@dataclass(frozen=True)
class AppConfig:
    question_count: int
    github: GitHubConfig
    snippets: SnippetConfig
    async_worker_count: int
    instructors: list[str]
    auth_cookie_name: str
    auth_cookie_secure: bool
    auth_cookie_samesite: str
    auth_jwt_exp_minutes: int
    cors_allowed_origins: list[str]
    auth_redirect_url: str


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping, got {type(data)}")
    return data


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or Path(__file__).parent / "config.yaml"
    raw = _read_yaml(path)
    github = raw.get("github", {})
    snippets = raw.get("snippets", {})
    async_cfg = raw.get("async", {})
    auth_cfg = raw.get("auth", {})
    return AppConfig(
        question_count=int(raw.get("question_count", 5)),
        github=GitHubConfig(
            api_base=str(github.get("api_base", "https://api.github.com")),
            timeout_seconds=float(github.get("timeout_seconds", 10)),
        ),
        snippets=SnippetConfig(
            allowed_extensions=list(snippets.get("allowed_extensions", [".py"])),
            excluded_dirs=list(
                snippets.get(
                    "excluded_dirs",
                    [
                        "node_modules",
                        "vendor",
                        ".git",
                        "__pycache__",
                        "dist",
                        "build",
                    ],
                )
            ),
            max_file_size_kb=int(snippets.get("max_file_size_kb", 256)),
            snippet_max_lines=int(snippets.get("snippet_max_lines", 120)),
            snippet_context_lines=int(snippets.get("snippet_context_lines", 6)),
            max_snippets_per_file=int(snippets.get("max_snippets_per_file", 5)),
            selection_count=int(snippets.get("selection_count", raw.get("question_count", 5) + 1)),
            max_candidates=int(snippets.get("max_candidates", 40)),
        ),
        async_worker_count=int(async_cfg.get("worker_count", 4)),
        instructors=list(auth_cfg.get("instructors", [])),
        auth_cookie_name=str(auth_cfg.get("cookie_name", "cqbot_auth")),
        auth_cookie_secure=bool(auth_cfg.get("cookie_secure", False)),
        auth_cookie_samesite=str(auth_cfg.get("cookie_samesite", "Lax")),
        auth_jwt_exp_minutes=int(auth_cfg.get("jwt_exp_minutes", 60)),
        cors_allowed_origins=list(auth_cfg.get("cors_allowed_origins", [])),
        auth_redirect_url=str(auth_cfg.get("redirect_url", "http://localhost:5173")),
    )
