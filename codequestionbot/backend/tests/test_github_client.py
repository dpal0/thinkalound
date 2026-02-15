from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.github import parse_repo_url


def test_parse_repo_url_valid():
    owner, name = parse_repo_url("https://github.com/example/my-repo")
    assert owner == "example"
    assert name == "my-repo"


def test_parse_repo_url_strips_git_suffix():
    owner, name = parse_repo_url("https://github.com/example/my-repo.git")
    assert owner == "example"
    assert name == "my-repo"


@pytest.mark.parametrize(
    "repo_url",
    [
        "http://gitlab.com/example/repo",
        "https://github.com/example",
        "ftp://github.com/example/repo",
    ],
)
def test_parse_repo_url_invalid(repo_url: str):
    with pytest.raises(ValueError):
        parse_repo_url(repo_url)
