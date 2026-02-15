from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import SnippetConfig
from services.repo_ingest import RepoFile
from services.snippets import extract_snippets


def test_extract_snippets_from_python():
    config = SnippetConfig(
        allowed_extensions=[".py"],
        excluded_dirs=[],
        max_file_size_kb=64,
        snippet_max_lines=10,
        snippet_context_lines=1,
        max_snippets_per_file=3,
        selection_count=5,
        max_candidates=10,
    )
    content = "\n".join(
        [
            "import os",
            "",
            "def run():",
            "    return os.getcwd()",
            "",
            "class Thing:",
            "    pass",
        ]
    )
    repo_file = RepoFile(path="app.py", content=content, lines=content.splitlines())
    snippets = extract_snippets([repo_file], config)
    assert len(snippets) == 2
    assert snippets[0].line_start == 3
    assert "def run" in snippets[0].excerpt_text
