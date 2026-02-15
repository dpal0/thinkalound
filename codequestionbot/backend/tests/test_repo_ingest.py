from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
from zipfile import ZipFile

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import SnippetConfig
from services.repo_ingest import extract_repo_files


def _build_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("repo-root/app.py", "def hello():\n    return 'hi'\n")
        archive.writestr("repo-root/node_modules/skip.js", "console.log('skip');")
        archive.writestr("repo-root/binary.bin", b"\x00\x01\x02")
    return buffer.getvalue()


def test_extract_repo_files_filters_noise():
    config = SnippetConfig(
        allowed_extensions=[".py"],
        excluded_dirs=["node_modules"],
        max_file_size_kb=64,
        snippet_max_lines=20,
        snippet_context_lines=4,
        max_snippets_per_file=5,
        selection_count=5,
        max_candidates=10,
    )
    files = extract_repo_files(_build_zip(), config)
    assert len(files) == 1
    assert files[0].path == "app.py"
