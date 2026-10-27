"""End-to-end test of the `query.md` -> `prompt.md` migration on a shallow clone of this repository.

The clone gets the root and `°base` logs plus two subprojects (one deeply nested below a path that has `ai` in its name), all with
random log lines. Every scenario (the four cases, dirty variants, links) is then run against every location and compared with
the exact expected files: existence, committed content, working tree content, and the number of migration commits.
"""
from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable, NamedTuple

ROOT = Path(__file__).resolve().parents[3]
OVERLAY_DIRS = ("ai", "git", "init")
SUBPROJECT = "subproject"
DEEP_SUBPROJECT = "longer/deeper/path/with/ai/in/its/name/but/its/actually/just/a/subproject"
DECOY = "longer/deeper/path/with/ai/in/query.md"
LOCATIONS = ("ai", "ai/°base", f"{SUBPROJECT}/ai", f"{DEEP_SUBPROJECT}/ai")
SUBPROJECT_LOCATIONS = LOCATIONS[2:]
TEMPLATE = ROOT / "scripts" / "°base" / "init" / "templates" / "prompt.md"
ENV = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"}


class Expect(NamedTuple):
    query: tuple[str | None, str | None]  # (committed in HEAD, working tree), None = does not exist
    prompt: tuple[str | None, str | None]
    commits: int  # migration commits on top of the scenario HEAD


def git(clone: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(clone), "-c", "core.quotepath=false", *args], capture_output=True, text=True, env=ENV, check=check)
    return result.stdout
# end def


def lines(rng: random.Random, prefix: str) -> str:
    return "".join(f"{prefix} {rng.getrandbits(48):012x} line {i}\n" for i in range(rng.randint(10, 50)))
# end def


class Clone:
    def __init__(self, path: Path) -> None:
        self.path = path
    # end def

    def commit(self, rel: str, text: str | None, message: str) -> None:
        # `text` None removes the file.
        file = self.path / rel
        if text is None:
            git(self.path, "rm", "--quiet", "--force", "--", rel)
        else:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text, encoding="utf-8")
            git(self.path, "add", "--", rel)
        # end if
        git(self.path, "commit", "--quiet", "--allow-empty", "--no-verify", "-m", message)
    # end def

    def write(self, rel: str, text: str) -> None:
        file = self.path / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
    # end def

    def head_text(self, rel: str) -> str | None:
        shown = subprocess.run(["git", "-C", str(self.path), "show", f"HEAD:{rel}"], capture_output=True, text=True, env=ENV)
        return shown.stdout if shown.returncode == 0 else None
    # end def

    def wt_text(self, rel: str) -> str | None:
        file = self.path / rel
        return file.read_text(encoding="utf-8") if file.is_file() else None
    # end def

    def reset(self, head: str) -> None:
        git(self.path, "reset", "--hard", "--quiet", head)
        git(self.path, "clean", "-fdxq")
    # end def

    def run_migration(self) -> None:
        subprocess.run(
            [sys.executable, "-I", str(self.path / "scripts" / "°base" / "ai" / "migrate_query_to_prompt.py")],
            cwd=self.path, env=ENV, check=True, capture_output=True,
        )
    # end def
# end class


class MigrateQueryToPromptCloneTests(unittest.TestCase):
    clone: Clone
    head: str
    baseline: dict[str, str]
    tmp: tempfile.TemporaryDirectory[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "clone"
        # 1. a shallow clone of the current version of this repo
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", f"file://{ROOT}", str(path)], check=True, env=ENV, capture_output=True)
        cls.clone = Clone(path)
        git(path, "config", "user.email", "test@example.com")
        git(path, "config", "user.name", "Test")
        git(path, "config", "commit.gpgsign", "false")

        # the working tree version of the scripts under test, so the test does not depend on what is committed yet.
        for name in OVERLAY_DIRS:
            shutil.copytree(
                ROOT / "scripts" / "°base" / name, path / "scripts" / "°base" / name,
                dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        # end for

        # 2. rename `prompt.md` back to `query.md` if the clone is already migrated, so the test can run again later.
        for location in ("ai", "ai/°base"):
            if (path / location / "prompt.md").exists():
                git(path, "mv", f"{location}/prompt.md", f"{location}/query.md")
            # end if
        # end for
        git(path, "add", "--", "scripts")
        git(path, "commit", "--quiet", "--allow-empty", "--no-verify", "-m", "test: current scripts, old log names")

        # 3. 10-50 random lines in the root and `°base` logs
        rng = random.Random("baseline")
        cls.baseline = {}
        for location in ("ai", "ai/°base"):
            cls.baseline[location] = lines(rng, location)
            cls.clone.commit(f"{location}/query.md", cls.baseline[location], f"test: {location} log")
        # end for

        # 4. + 5. two subprojects, linked by the script
        for sub in (SUBPROJECT, DEEP_SUBPROJECT):
            (path / sub).mkdir(parents=True)
            subprocess.run(
                [sys.executable, "-I", str(path / "scripts" / "°base" / "init" / "link_subproject.py")],
                cwd=path / sub, env=ENV, check=True, capture_output=True,
            )
            for name in ("prompt.md", "query.md"):
                # whatever the script seeded, the baseline has the old name only
                file = path / sub / "ai" / name
                if file.exists() and not file.is_symlink():
                    file.unlink()
                    git(path, "rm", "--cached", "--quiet", "--ignore-unmatch", "--", f"{sub}/ai/{name}")
                # end if
            # end for
            cls.baseline[f"{sub}/ai"] = lines(rng, sub)
            cls.clone.write(f"{sub}/ai/query.md", cls.baseline[f"{sub}/ai"])
        # end for
        cls.clone.write(DECOY, "not a log, the folder before it is just called ai\n")

        # 6. nothing may be left uncommitted
        git(path, "add", "--", f"./{SUBPROJECT}/", "./longer/")
        git(path, "commit", "--quiet", "--allow-empty", "--no-verify", "-m", "test: subprojects")

        # 7. the state every scenario starts from
        cls.head = git(path, "rev-parse", "HEAD").strip()
    # end def

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()
    # end def

    def scenarios(self, location: str, rng: random.Random) -> dict[str, tuple[Callable[[], None], Expect]]:
        clone, base = self.clone, self.baseline[location]
        query, prompt = f"{location}/query.md", f"{location}/prompt.md"
        template = TEMPLATE.read_text(encoding="utf-8")
        dirty, other, longer = lines(rng, "dirty"), lines(rng, "other"), lines(rng, "longer")

        def q_dirty() -> None:
            clone.write(query, base + dirty)
        # end def

        def q_untracked() -> None:
            clone.commit(query, None, "test: remove old log")
            clone.write(query, longer)
        # end def

        def p_template() -> None:
            clone.commit(prompt, template, "test: shipped template")
        # end def

        def equal_q_older() -> None:
            # q has 2 more commits than in the baseline, p one more than it ever had (which is not much), same content.
            clone.commit(query, other, "test: rewrite old log, first")
            clone.commit(query, longer, "test: rewrite old log, second")
            clone.commit(prompt, longer, "test: new log")
        # end def

        def equal_p_older() -> None:
            # p has 2 more commits than it ever had, q none, same content.
            clone.commit(prompt, other, "test: new log, first")
            clone.commit(prompt, base, "test: new log, second")
        # end def

        def differ() -> None:
            clone.commit(prompt, other, "test: different new log")
        # end def

        def equal_q_dirty() -> None:
            clone.commit(prompt, base, "test: same new log")
            clone.write(query, base + dirty)
        # end def

        def equal_p_dirty() -> None:
            clone.commit(prompt, base, "test: same new log")
            clone.write(prompt, base + dirty)
        # end def

        def template_q_dirty() -> None:
            clone.commit(prompt, template, "test: shipped template")
            clone.write(query, base + dirty)
        # end def

        def p_only() -> None:
            clone.commit(query, None, "test: remove old log")
            clone.commit(prompt, other, "test: new log")
        # end def

        return {
            "q clean": (lambda: None, Expect((None, None), (base, base), 1)),
            "q dirty": (q_dirty, Expect((None, None), (base, base + dirty), 1)),
            "q never committed": (q_untracked, Expect((None, None), (None, longer), 0)),
            "p is the template": (p_template, Expect((None, None), (base, base), 2)),
            "equal, q older": (equal_q_older, Expect((None, None), (longer, longer), 2)),
            "equal, p older": (equal_p_older, Expect((None, None), (base, base), 1)),
            "differ": (differ, Expect((base, base), (other, other), 0)),
            "equal, q dirty": (equal_q_dirty, Expect((base, base + dirty), (base, base), 0)),
            "equal, p dirty": (equal_p_dirty, Expect((base, base), (base, base + dirty), 0)),
            "template, q dirty": (template_q_dirty, Expect((base, base + dirty), (template, template), 0)),
            "p only": (p_only, Expect((None, None), (other, other), 0)),
        }
    # end def

    def check(self, location: str, expect: Expect, commits_before: int) -> None:
        clone = self.clone
        for name, wanted in (("query.md", expect.query), ("prompt.md", expect.prompt)):
            rel = f"{location}/{name}"
            self.assertEqual(wanted, (clone.head_text(rel), clone.wt_text(rel)), f"{rel}: (committed, working tree)")
        # end for
        commits_after = int(git(clone.path, "rev-list", "--count", "HEAD").strip())
        # one rename commit for each of the other locations, which are plain clean logs
        self.assertEqual(expect.commits + len(LOCATIONS) - 1, commits_after - commits_before, f"{location}: migration commits")

        dirty = sorted(
            line[3:] for line in git(clone.path, "status", "--porcelain", "--untracked-files=all", "--", f"{location}/query.md", f"{location}/prompt.md").splitlines()
        )
        wanted_dirty = sorted(
            f"{location}/{name}" for name, (head, wt) in (("query.md", expect.query), ("prompt.md", expect.prompt)) if head != wt
        )
        self.assertEqual(wanted_dirty, dirty, f"{location}: git status")

        if expect.prompt[0] is not None and expect.commits:
            history = git(clone.path, "log", "--follow", "--format=%s", "--", f"{location}/prompt.md").splitlines()
            self.assertGreaterEqual(len(history), 2, f"{location}: history of prompt.md is cut off: {history}")
        # end if
    # end def

    def test_matrix(self) -> None:
        for location in LOCATIONS:
            names = list(self.scenarios(location, random.Random(location)))
            for name in names:
                with self.subTest(location=location, scenario=name):
                    self.clone.reset(self.head)
                    setup, expect = self.scenarios(location, random.Random(f"{location}/{name}"))[name]
                    setup()
                    git(self.clone.path, "status", "--porcelain")
                    commits_before = int(git(self.clone.path, "rev-list", "--count", "HEAD").strip())

                    self.clone.run_migration()
                    self.check(location, expect, commits_before)

                    # every other location is a plain clean q -> p migration, and the decoy was left alone.
                    for other in LOCATIONS:
                        if other == location:
                            continue
                        # end if
                        self.assertEqual(
                            (None, None), (self.clone.head_text(f"{other}/query.md"), self.clone.wt_text(f"{other}/query.md")),
                            f"{other} old name is gone",
                        )
                        self.assertEqual(self.baseline[other], self.clone.head_text(f"{other}/prompt.md"), f"{other} migrated")
                    # end for
                    self.assertEqual("not a log, the folder before it is just called ai\n", self.clone.wt_text(DECOY))
                # end with
            # end for
        # end for
    # end def

    def test_subproject_link_to_root_log(self) -> None:
        for location in SUBPROJECT_LOCATIONS:
            with self.subTest(location=location):
                self.clone.reset(self.head)
                link = self.clone.path / location / "query.md"
                link.unlink()
                git(self.clone.path, "rm", "--cached", "--quiet", "--", f"{location}/query.md")
                target = os.path.relpath(self.clone.path / "ai" / "query.md", link.parent)
                link.symlink_to(target)
                git(self.clone.path, "add", "--", f"{location}/query.md")
                git(self.clone.path, "commit", "--quiet", "--no-verify", "-m", "test: log is a link to the root log")

                self.clone.run_migration()

                self.assertFalse(os.path.lexists(link), "old link is gone")
                new = self.clone.path / location / "prompt.md"
                self.assertTrue(new.is_symlink())
                self.assertEqual(os.path.relpath(self.clone.path / "ai" / "prompt.md", new.parent), os.readlink(new))
                self.assertEqual(self.baseline["ai"], new.read_text(encoding="utf-8"))
                self.assertEqual(os.readlink(new), self.clone.head_text(f"{location}/prompt.md"))
            # end with
        # end for
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
