from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import ast
import re

from config import SnippetConfig
from services.repo_ingest import RepoFile


@dataclass(frozen=True)
class Snippet:
    file_path: str
    line_start: int
    line_end: int
    excerpt_text: str
    excerpt_hash: str


_JS_PATTERN = re.compile(
    r"^\s*(export\s+)?(default\s+)?(async\s+)?(function|class)\s+\w+|"
    r"^\s*(export\s+)?const\s+\w+\s*=\s*.*=>"
)


def extract_snippets(files: list[RepoFile], config: SnippetConfig) -> list[Snippet]:
    snippets: list[Snippet] = []
    for repo_file in files:
        if repo_file.path.endswith(".py"):
            snippets.extend(_extract_python_blocks(repo_file, config))
        elif repo_file.path.endswith((".js", ".ts", ".tsx")):
            snippets.extend(_extract_js_blocks(repo_file, config))
    return snippets


def _extract_python_blocks(repo_file: RepoFile, config: SnippetConfig) -> list[Snippet]:
    try:
        module = ast.parse(repo_file.content)
    except SyntaxError:
        return []
    snippets: list[Snippet] = []
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        end_line = getattr(node, "end_lineno", None)
        if end_line is None:
            continue
        snippet = _build_snippet(repo_file, node.lineno - 1, end_line, config)
        if snippet:
            snippets.append(snippet)
        if len(snippets) >= config.max_snippets_per_file:
            break
    return snippets


def _extract_js_blocks(repo_file: RepoFile, config: SnippetConfig) -> list[Snippet]:
    snippets: list[Snippet] = []
    lines = repo_file.lines
    for idx, line in enumerate(lines):
        if not _JS_PATTERN.search(line):
            continue
        end_line = _find_js_block_end(lines, idx)
        if end_line is None:
            continue
        snippet = _build_snippet(repo_file, idx, end_line, config)
        if snippet:
            snippets.append(snippet)
        if len(snippets) >= config.max_snippets_per_file:
            break
    return snippets


def _find_js_block_end(lines: list[str], start_idx: int) -> int | None:
    depth = 0
    found_open = False
    for idx in range(start_idx, len(lines)):
        for char in lines[idx]:
            if char == "{":
                depth += 1
                found_open = True
            elif char == "}":
                depth -= 1
        if found_open and depth == 0:
            return idx + 1
    if not found_open:
        return min(start_idx + 1, len(lines))
    return None


def _build_snippet(
    repo_file: RepoFile, start_idx: int, end_idx: int, config: SnippetConfig
) -> Snippet | None:
    if end_idx <= start_idx:
        return None
    length = end_idx - start_idx
    if length > config.snippet_max_lines:
        return None
    excerpt_lines = repo_file.lines[start_idx:end_idx]
    if not excerpt_lines:
        return None
    excerpt_text = "\n".join(excerpt_lines)
    excerpt_hash = sha256(excerpt_text.encode("utf-8")).hexdigest()
    return Snippet(
        file_path=repo_file.path,
        line_start=start_idx + 1,
        line_end=end_idx,
        excerpt_text=excerpt_text,
        excerpt_hash=excerpt_hash,
    )
