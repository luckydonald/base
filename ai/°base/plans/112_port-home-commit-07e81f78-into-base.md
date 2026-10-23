# Port `.home` commit 07e81f78 into base

## Context

`luckydonald/.home@07e81f78` adds `scripts/fix_git_credential_user.py` (finds the `git` command that opened a credential manager and pins `GIT_USERNAME` into the remote URL, with a `Confirm? [Y/n]` step) plus `scripts/test_fix_git_credential_user.py` and a 3-line `ai/query.md` addition.
It is a generic helper, so it belongs in base, adapted to base's layout: real files under `scripts/°base/`, a relative symlink in `scripts/`, tests under `scripts/°base/tests/`, and prompts under `ai/°base/`.

Commit style: `commit-with-lplp-style` is active (origin is `luckydonald/base`, so assumed `yes` without asking).
That means a plain new commit per completed task, a `scripts/tag_backup.py` tag on the prior HEAD first, the message written via `ai/git/pending-commit.md`, and an interactive rebase afterwards to fold nearby `ai:` auto-commits.
Only the files below are committed, never the unrelated untracked files in `git status`.

## Changes

1. Copy the script from the source commit (`git -C /Users/user/.home show 07e81f78:scripts/fix_git_credential_user.py`) to `scripts/°base/fix_git_credential_user.py`, keeping its executable bit and the `uv run --script` header unchanged.
   Only the usage lines in the docstring are updated to `./scripts/fix_git_credential_user.py`, which stays valid through the symlink.
2. Add the symlink `scripts/fix_git_credential_user.py -> °base/fix_git_credential_user.py`, matching the existing ones (e.g. `scripts/tag_backup.py -> °base/tag_backup.py`).
3. Port the tests to `scripts/°base/tests/test_fix_git_credential_user.py` as `unittest`, since base runs `python -m unittest discover` and has no pytest dependency.
   - Load the script via `importlib.util` from `Path(__file__).resolve().parents[1] / "fix_git_credential_user.py"` (the `SCRIPT` pattern in `test_get_base.py`).
   - The `parametrize` cases become `subTest` loops, and `tmp_path` becomes `tempfile.TemporaryDirectory`.
   - Same coverage: URL rewriting, special-character quoting, `CREDENTIAL_HELPER_RE`, `REMOTE_HELPER_RE`, `git_working_dir`, `set_url_command`.
4. `ai/°base/query.md`: the hook has already recorded this prompt (it is the last entry), so nothing to add.
   The 3-line source addition is a prompt from the `.home` session about this script's origin, so it is not copied; the commit message mentions the source instead.

## Commit

One commit for items 1–3, message `[base] [.home] scripts: ai: Run: Added fix_git_credential_user.py to pin the git username into the remote URL a credential manager was opened for.`, with the source commit hash in the body.
No `Co-Authored-By` or `Claude-Session` trailer, because the repo's commit-msg hook rejects them.

## Verification

- `uv run --project scripts/°base python -m unittest scripts/°base/tests/test_fix_git_credential_user.py -v` (or `discover -s scripts/°base/tests -p 'test_fix_git_credential_user.py'`) passes.
- `ls -l scripts/fix_git_credential_user.py` shows the symlink and `./scripts/fix_git_credential_user.py --help`-style startup resolves through it (the script waits for a helper, so only confirm it launches and prints the `GIT_USERNAME` line, then Ctrl-C).
- `git status` shows only the three intended paths staged before committing.
