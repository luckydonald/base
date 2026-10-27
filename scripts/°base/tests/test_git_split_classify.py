from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

LIB_ROOT = Path(__file__).resolve().parents[1] / "git"
sys.path.insert(0, str(LIB_ROOT))

classify = importlib.import_module("°split_lib.classify")


class IsAiBasePathTests(unittest.TestCase):
    def test_path_classification_matrix(self):
        paths_matrix: dict[str, dict[str, bool]] = {
            "AI top-level directories": {
                "ai/something.py": True,
                "ai/prompt.md": True,
                ".claude/foo/bar.bazt/banana": True,
                ".claude/settings.json": True,
                ".codex/1": True,
                ".codex/config.toml": True,
                ".agents/idk": True,
                ".agents/skills/example/SKILL.md": True,
                ".ai-ignore": False,
            },
            "exact AI files": {
                ".mcp.json": True,
                "AGENTS.md": True,
                "CLAUDE.md": True,
            },
            "base path segment": {
                "scripts/°base/git/split.py": True,
                "deep/nested/°base/thing.py": True,
            },
            "ordinary code paths": {
                "src/main.py": False,
                "backend/api/routes.py": False,
                "frontend/src/App.vue": False,
                "scripts/deploy.py": False,
                "assets/logo.svg": False,
                "README.md": False,
            },
            "lookalike paths": {
                "ai-notes.txt": False,
                ".claude-thing/x.py": False,
                "base/x.py": False,
            },
            "mixed dirs": {
                ".github/hooks/generated.json": True,
                ".github/workflows/claude.yml": True,
                ".github/workflows/claude-issue-agent.yml": True,
                ".github/workflows/codex-issue-agent.yml": True,
                ".github/workflows/something-else.yml": False,
                ".github/issue_templates/README.md": False,
            },
        }

        for category, paths in paths_matrix.items():
            with self.subTest(category=category):
                for path, expected in paths.items():
                    self.assertEqual(classify.is_ai_base_path(path), expected, msg=f"Path {path=!r} should {'' if expected else 'not '}be classified as AI path.")
                # end for
            # end with
        # end for

        with tempfile.TemporaryDirectory() as temporary_directory:
            ignore_file = Path(temporary_directory) / ".ai-ignore"
            ignore_file.write_text(
                (
                    "# An ignored comment\n"
                    "notes/**\n"
                    "!notes/public/**\n"
                    "notes/public/keep.md\n"
                    "*.prompt\n"
                    "!private.prompt\n"
                ),
                encoding="utf-8",
            )
            nested_directory = Path(temporary_directory) / "nested"
            nested_directory.mkdir()
            (nested_directory / ".ai-ignore").write_text(
                data=(
                    "generated/**\n"
                    "!generated/keep.py\n"
                    ".ai-ignore\n"
                    "\n"
                    "# comment, don't match or parse {]|**\n"
                    "missing-last-line"
                ),
                encoding="utf-8",
            )
            custom_paths_matrix: dict[str, bool] = {
                "notes/draft.md": True,
                "notes/public/readme.md": False,
                "notes/public/keep.md": True,
                "nested/example.prompt": True,
                "nested/.ai-ignore": True,
                "nested/subfolder/.ai-ignore": False,
                "nested/generated/build.py": True,
                "nested/generated/keep.py": False,
                "other/generated/build.py": False,
                "private.prompt": False,
                "src/main.py": False,
            }
            for path, expected in custom_paths_matrix.items():
                with self.subTest(category="custom .ai-ignore", path=path):
                    self.assertEqual(classify.is_ai_base_path(path, ignore_file=ignore_file), expected, msg=f"Path {path=!r} should {'' if expected else 'not '}be classified as AI path.")
                # end with
            # end for
        # end with
    # end def
# end class


class GlobFallbackTests(unittest.TestCase):
    """`glob_to_regex` stands in for `PurePosixPath.full_match`, which only exists since Python 3.13."""

    def test_glob_matrix(self):
        cases: dict[str, dict[str, bool]] = {
            "a/**": {"a/b": True, "a/b/c": True, "b/c": False},
            "**/a": {"a": True, "x/a": True, "x/y/a": True, "a/b": False},
            "*.md": {"file.md": True, "d/file.md": False},
            "a/**/b": {"a/b": True, "a/x/b": True, "a/x/y/b": True, "a/c": False},
            "[ab]/c": {"a/c": True, "c/c": False},
            "[!a]/c": {"b/c": True, "a/c": False},
            "?/c": {"a/c": True, "ab/c": False},
        }
        for pattern, paths in cases.items():
            for path, expected in paths.items():
                with self.subTest(pattern=pattern, path=path):
                    self.assertEqual(classify.glob_to_regex(pattern).fullmatch(path) is not None, expected)

    def test_full_match_without_native_support(self):
        class OldPath:
            def __init__(self, path: str):
                self.path = path

            def as_posix(self) -> str:
                return self.path

        self.assertTrue(classify.full_match(OldPath("ai/x/y"), "ai/**"))
        self.assertFalse(classify.full_match(OldPath("src/x"), "ai/**"))


class AiSubjectRegexTests(unittest.TestCase):
    def test_matches_plain_ai_prefix(self):
        self.assertTrue(classify.AI_SUBJECT_RE.match("ai: updated prompt"))

    def test_matches_bracketed_topic_convention(self):
        self.assertTrue(classify.AI_SUBJECT_RE.match("[base] topic: ai: Run: did a thing."))
        self.assertTrue(classify.AI_SUBJECT_RE.match("[dumper] init script: ai: Run: extended linking."))

    def test_does_not_match_unrelated_subjects(self):
        self.assertFalse(classify.AI_SUBJECT_RE.match("aisle: fix typo"))
        self.assertFalse(classify.AI_SUBJECT_RE.match("said: hello"))
        self.assertFalse(classify.AI_SUBJECT_RE.match("[base] fix a bug."))


class ClassifyCommitTests(unittest.TestCase):
    def test_ai_only_commit(self):
        result = classify.classify_commit("abc", "ai: updated prompt", ["ai/prompt.md"])
        self.assertTrue(result.is_ai_only_commit)
        self.assertTrue(result.is_ai_tainted_commit)
        self.assertFalse(result.is_code_containing_commit)

    def test_pure_code_commit(self):
        result = classify.classify_commit("abc", "Add export button", ["src/export.py"])
        self.assertFalse(result.is_ai_only_commit)
        self.assertFalse(result.is_ai_tainted_commit)
        self.assertTrue(result.is_code_containing_commit)

    def test_mixed_commit_is_ai_tainted_and_code_containing(self):
        result = classify.classify_commit(
            "abc", "Add export button", ["src/export.py", "ai/prompt.md"]
        )
        self.assertFalse(result.is_ai_only_commit)
        self.assertTrue(result.is_ai_tainted_commit)
        self.assertTrue(result.is_code_containing_commit)

    def test_empty_paths_with_ai_subject_is_tainted_but_not_ai_only(self):
        result = classify.classify_commit("abc", "ai: empty marker commit", [])
        self.assertFalse(result.is_ai_only_commit)
        self.assertTrue(result.is_ai_tainted_commit)
        self.assertFalse(result.is_code_containing_commit)

    def test_empty_paths_with_plain_subject_is_untainted(self):
        result = classify.classify_commit("abc", "empty marker commit", [])
        self.assertFalse(result.is_ai_only_commit)
        self.assertFalse(result.is_ai_tainted_commit)
        self.assertFalse(result.is_code_containing_commit)

    def test_code_commit_with_ai_flavored_subject_is_tainted_by_subject(self):
        result = classify.classify_commit(
            "abc", "[base] topic: ai: Run: refactor.", ["src/export.py"]
        )
        self.assertTrue(result.is_ai_tainted_commit)
        self.assertTrue(result.is_code_containing_commit)


if __name__ == "__main__":
    unittest.main()
