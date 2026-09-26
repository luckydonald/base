In the repo /home/user/git/luckydonald/base, I'm planning a feature that needs to, in edge cases, remove a single already-committed file from git history entirely — including from all branches and tags that reference the commit or any of its descendant commits — while being careful not to break other files with identical content committed elsewhere in the repo, and explicitly NOT using `git gc`.

Search the repo for any existing tooling, scripts, or documented patterns related to:
1. Rewriting git history / removing commits from branches or tags (grep for `filter-branch`, `filter-repo`, `rebase`, `update-ref`, `git tag -d`, `for-each-ref`, `cherry-pick`, `--allow-empty`, `rev-list`, `cat-file` in scripts/ and ai/ dirs)
2. Any existing memory files under /home/user/.confuig/claude/accounts/private/projects/-home-user-git-luckydonald-base/memory/ mentioning history rewriting, replay guards, or git internals — specifically read the file `2026-07-20-history-master-replay-guards.md` in that memory dir if it exists, and report its full content
3. Any `history_master.py` script in the repo (search for it) — read it if found, focusing on any logic for removing/rewriting commits, restoring branches, or checking git object references
4. Existing patterns in the repo for writing throwaway git repos in /tmp for testing (grep for `git init` inside test files or scripts)
5. Any git hooks in the repo (pre-commit etc.) that might interfere with force-committing a single file or with test repos in /tmp

Report file paths, function/section names, and relevant excerpts. Be thorough but concise — under 500 lines of output.