from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Iterable
from zipfile import ZipFile

from config import SnippetConfig


@dataclass(frozen=True)
class RepoFile:
    path: str
    content: str
    lines: list[str]


def extract_repo_files(archive_bytes: bytes, config: SnippetConfig) -> list[RepoFile]:
    files: list[RepoFile] = []
    with ZipFile(BytesIO(archive_bytes)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if info.file_size > config.max_file_size_kb * 1024:
                continue
            normalized = _strip_archive_root(info.filename)
            if not normalized:
                continue
            if _is_excluded(normalized, config.excluded_dirs):
                continue
            if not _has_allowed_extension(normalized, config.allowed_extensions):
                continue
            raw = archive.read(info.filename)
            if b"\x00" in raw:
                continue
            try:
                text = raw.decode("utf-8", errors="ignore")
            except UnicodeDecodeError:
                continue
            lines = text.splitlines()
            files.append(RepoFile(path=normalized, content=text, lines=lines))
    return files


def _strip_archive_root(path: str) -> str:
    parts = PurePosixPath(path).parts
    if len(parts) <= 1:
        return ""
    return str(PurePosixPath(*parts[1:]))


def _is_excluded(path: str, excluded_dirs: Iterable[str]) -> bool:
    parts = set(PurePosixPath(path).parts)
    return any(excluded in parts for excluded in excluded_dirs)


def _has_allowed_extension(path: str, allowed: Iterable[str]) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    return suffix in {ext.lower() for ext in allowed}
