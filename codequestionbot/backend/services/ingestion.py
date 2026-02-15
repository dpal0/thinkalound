from __future__ import annotations

from dataclasses import dataclass

from config import AppConfig
from services.github import GitHubClient
from services.repo_ingest import RepoFile, extract_repo_files
from services.snippets import Snippet, extract_snippets


@dataclass(frozen=True)
class IngestionResult:
    owner: str
    name: str
    default_branch: str
    commit_sha: str
    owner_id: str
    files: list[RepoFile]
    snippets: list[Snippet]


def ingest_repo(
    repo_url: str,
    config: AppConfig,
    token: str | None = None,
    commit_sha: str | None = None,
) -> IngestionResult:
    client = GitHubClient(config.github, token=token)
    metadata = client.verify_repo_url(repo_url)
    if not metadata.is_personal:
        raise ValueError("Only personal repositories are supported.")
    resolved_sha = commit_sha or client.get_commit_sha(
        metadata.owner,
        metadata.name,
        metadata.default_branch,
    )
    archive = client.download_repo_zip(metadata.owner, metadata.name, resolved_sha)
    files = extract_repo_files(archive, config.snippets)
    candidates = extract_snippets(files, config.snippets)
    # Take top N candidates directly instead of an extra LLM call for selection
    selection_count = min(config.snippets.selection_count, len(candidates))
    snippets = candidates[:selection_count]
    return IngestionResult(
        owner=metadata.owner,
        name=metadata.name,
        default_branch=metadata.default_branch,
        commit_sha=resolved_sha,
        owner_id=metadata.owner_id,
        files=files,
        snippets=snippets,
    )
