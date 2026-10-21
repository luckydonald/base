# Memory
- [Repo commit hooks](repo_commit_hooks.md) — pre-commit hook rejects Co-Authored-By/Claude-Session commit trailers; `allowCoAuthoredEtc: false` in `ai/settings/settings.json` suppresses Claude Code's own footer.
- [Telegram user_id is BIGINT](project_telegram_user_id_bigint.md) — Telegram ids exceed 32 bits: use BIGINT / 64-bit ints in db columns and in variable declarations of fixed-width languages
- [bugsink MCP env symlink](project_bugsink_mcp_needs_env_symlink.md) — CONNECTION_CLOSED in a subproject/worktree usually means missing `ai/.env` symlink, not bad creds; needs a fresh session after fixing
