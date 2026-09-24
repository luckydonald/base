Based on the official Claude Code documentation, here's what I found:

## 1. **Project Path Encoding: Not Explicitly Documented**

The documentation states that auto memory's project path is **"derived from the git repository"** and transcripts are stored at `~/.claude/projects/<project>/` where `<project>` is "your working directory path with non-alphanumeric characters replaced by `-`" — but **it does not explicitly specify whether symlinks are resolved** using `realpath()` or used literally.

However, Claude Code's documented behavior strongly suggests path resolution occurs: it explicitly **refuses to create worktrees when `.claude` is a symlink**, with the error:

> "Claude Code refuses to create a worktree when `.claude`, `.claude/worktrees`, or the worktree directory itself is a symlink, and the error names the symlinked path. Remove the symlink and retry."

This suggests Claude Code performs symlink resolution somewhere in its path-identity logic, though the documentation doesn't confirm it applies to memory path encoding specifically.

## 2. **Override via Environment Variable: Yes**

`CLAUDE_CODE_PROJECT_DIR_NAME` (available since v2.1.234+) **does solve this**. Set it alongside `CLAUDE_CONFIG_DIR` in your shell environment at startup:

```bash
CLAUDE_CONFIG_DIR=~/.claude CLAUDE_CODE_PROJECT_DIR_NAME=my_subproject claude
```

This pins the project directory name independently of where `.claude` physically resolves, so memories and transcripts land in `~/.claude/projects/my_subproject/` regardless of symlink depth.

**Important**: Set it only in the shell environment at startup — `env` blocks in `settings.json` don't work for this variable.

## 3. **Symlinking `.claude`: Discouraged, Not Explicitly Anti-Pattern**

Symlinking the entire `.claude` directory is **not documented as an anti-pattern for monorepos**, but it **is blocked for worktree creation**. The documentation does not address your specific scenario (shared settings via symlink in subprojects).

**Bottom line**: The symlink-resolution behavior affecting memory storage is not documented. The safest approach for your monorepo setup is `CLAUDE_CODE_PROJECT_DIR_NAME` (v2.1.234+) or symlinking individual files within a real `.claude` directory rather than the directory itself.