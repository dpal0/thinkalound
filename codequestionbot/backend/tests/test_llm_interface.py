from __future__ import annotations

import os
from pathlib import Path
import unittest
import yaml

from config import load_config
from llm.interface import GeneratedQuestion, generate_questions, grade_answer
from services.snippets import Snippet


class LlmInterfaceFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_key = os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self) -> None:
        if self._orig_key is not None:
            os.environ["OPENAI_API_KEY"] = self._orig_key

    def test_generate_questions_fallback_count(self) -> None:
        config = load_config(Path(__file__).parents[1] / "config" / "config.yaml")
        snippet = Snippet(
            file_path="main.py",
            line_start=1,
            line_end=3,
            excerpt_text="def foo():\n    return 1",
            excerpt_hash="hash",
        )
        questions = generate_questions(
            [snippet],
            config,
            repo_meta={"repo_url": "https://github.com/user/repo", "owner": "user", "name": "repo"},
        )
        self.assertEqual(len(questions), config.question_count)
        self.assertTrue(all(q.file_path == "main.py" for q in questions))

    def test_grade_answer_blank_fallback(self) -> None:
        config_path = Path(__file__).parents[1] / "config" / "config.yaml"
        with config_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        grading = raw.get("grading", {})
        question = GeneratedQuestion(
            question_text="Why does this work?",
            file_path="main.py",
            line_start=1,
            line_end=3,
            excerpt_text="def foo():\n    return 1",
            excerpt_hash="hash",
        )
        grade = grade_answer("", question)
        self.assertEqual(grade.score, int(grading.get("min_score", 1)))
        self.assertEqual(
            grade.confidence, float(grading.get("default_confidence", 0.5))
        )
