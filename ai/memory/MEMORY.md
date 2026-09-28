# Memory
- [Repo commit hooks](repo_commit_hooks.md) — pre-commit hook rejects Co-Authored-By/Claude-Session commit trailers; `allowCoAuthoredEtc: false` in `ai/settings/settings.json` suppresses Claude Code's own footer.
- [bugsink MCP env symlink](project_bugsink_mcp_needs_env_symlink.md) — CONNECTION_CLOSED in a subproject/worktree usually means missing `ai/.env` symlink, not bad creds; needs a fresh session after fixing
