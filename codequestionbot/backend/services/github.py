from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from config import GitHubConfig


@dataclass(frozen=True)
class RepoMetadata:
    owner: str
    name: str
    default_branch: str
    is_personal: bool
    owner_id: str
    owner_login: str
    permissions: dict[str, bool]


class GitHubClient:
    def __init__(self, config: GitHubConfig, token: str | None = None) -> None:
        self._base = config.api_base.rstrip("/")
        self._timeout = config.timeout_seconds
        self._token = token

    def verify_repo_url(self, repo_url: str) -> RepoMetadata:
        owner, name = parse_repo_url(repo_url)
        payload = self._get_json(f"/repos/{owner}/{name}")
        repo_owner = payload.get("owner", {})
        owner_type = repo_owner.get("type", "")
        owner_id = str(repo_owner.get("id", ""))
        owner_login = str(repo_owner.get("login", ""))
        default_branch = payload.get("default_branch", "")
        permissions = payload.get("permissions", {}) if isinstance(payload.get("permissions"), dict) else {}
        return RepoMetadata(
            owner=owner,
            name=name,
            default_branch=default_branch,
            is_personal=owner_type == "User",
            owner_id=owner_id,
            owner_login=owner_login,
            permissions=permissions,
        )

    def get_commit_sha(self, owner: str, name: str, ref: str) -> str:
        payload = self._get_json(f"/repos/{owner}/{name}/commits/{ref}")
        sha = payload.get("sha")
        if not sha:
            raise ValueError("Missing commit sha in GitHub response.")
        return str(sha)

    def download_repo_zip(self, owner: str, name: str, ref: str) -> bytes:
        url = f"{self._base}/repos/{owner}/{name}/zipball/{ref}"
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        resp = requests.get(url, headers=headers, timeout=self._timeout)
        if resp.status_code != 200:
            raise ValueError(f"GitHub archive error {resp.status_code}: {resp.text}")
        return resp.content

    def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self._base}{path}"
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        resp = requests.get(url, headers=headers, timeout=self._timeout)
        if resp.status_code != 200:
            raise ValueError(f"GitHub API error {resp.status_code}: {resp.text}")
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected GitHub API response format.")
        return data


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Repo URL must start with http or https.")
    if parsed.netloc.lower() != "github.com":
        raise ValueError("Repo URL must be hosted on github.com.")
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Repo URL must include owner and repo name.")
    owner, name = parts[0], parts[1]
    if name.endswith(".git"):
        name = name[:-4]
    return owner, name
