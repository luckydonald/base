I need to understand a bug/limitation in this repo (/home/user/git/luckydonald/base). The user says: "If I create a subfolder and link it with the link script it will not be able to save claude memories."

Please investigate and report back (don't make any edits, read-only):

1. Read `scripts/link_subproject.sh` and `scripts/°base/link_subproject.sh` (compare if they differ) — what does "linking a subproject" do? Does it symlink/hardlink the base repo's `ai/` tooling (hooks, settings) into a subfolder so that subfolder can act as an independent Claude Code project root?

2. Read `scripts/°base/ai/hooks/record-memory/hook.py` in full — this is the hook responsible for saving Claude Code memories from a session's `~/.claude/projects/<encoded-project-path>/memory/` directory. Understand exactly how it determines:
   - the project directory encoding (how `<encoded-project-path>` is derived from the actual working directory path)
   - where it writes/hardlinks memory files to (i.e., which directory in the git repo memories end up linked to, e.g. `ai/memory/` at repo root vs somewhere else)

3. Read `scripts/°base/ai/hooks/°memory_lib/links.py` — understand `link_file`/`same_inode` and how hardlinking across directories/filesystems is handled (note: hardlinks don't work across filesystems, and also note whether the memory dir target is computed based on git repo root vs the immediate project folder).

4. Read `scripts/°base/init/link-subproject-claude.sh` — this seems related to setting up Claude for a linked subproject. What does it set up (settings.json, hooks, CLAUDE_CONFIG_DIR)? Does it configure anything memory-related, or is memory setup missing/not invoked for subprojects?

5. Look for how a normal (non-subproject, i.e. `base` itself or a project that already fully adopted `°base`) project's memory setup differs from a freshly-linked subproject. Specifically: is there a required registration step (e.g. adding the project's encoded Claude path, or an entry somewhere) that `link_subproject.sh` / `link-subproject-claude.sh` does NOT perform, which would explain why memories fail to save for a new subfolder?

6. Check if there's related documentation: `ai/°base/AGENTS.md`, and any doc under `ai/°base/ai/hooks/record-memory/` or similar, describing prerequisites for the record-memory hook to work (e.g. must be a git repo, must have `ai/memory/` dir already existing, `.claude/settings.json` must reference the hook, CLAUDE_CONFIG_DIR consistency, etc).

Also check the memory file /home/user/.confuig/claude/accounts/private/projects/-home-user-git-luckydonald-base/memory/project_dual_codex_config_dirs.md content for related context (already read, mentions CLAUDE_CONFIG_DIR path resolution bugs in record-memory hook) — see how that interacts with subprojects specifically (is the subproject given a different CLAUDE_CONFIG_DIR, or does record-memory hook assume something about the directory structure that breaks for a freshly linked subfolder e.g. it not being a distinct git repo, or memory dir not existing yet, or settings.json hook registration not copied over).

Report back: the exact root cause you found (with file:line citations) for why a newly linked subfolder can't save memories, and what's missing/broken. Be thorough — this is investigation only, no fixes.