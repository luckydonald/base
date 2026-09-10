# Enabling the `bugsink` MCP server

This applies to any project using the `scripts/°base/ai/settings/sync.py` settings-sync system (for monorepos: project `.claude`/`.codex` dirs and `.mcp.json` are usually symlinks into a shared config living at the monorepo/base-repo root).
The `bugsink` MCP server (`mcp__bugsink__*` tools) ships disabled by default and needs to be turned on before an agent can call it.

## The one file that matters

The source of truth is **`ai/settings/settings.json`** (relative to the git root), under:

```json5
{
  // ...
  "mcp": {
    "servers": {
      "bugsink": {
        "enabled": false,
        // ...
      }
    }
  }
}
```

Flip `enabled` to `true` there, then run:

```bash
python3 "scripts/°base/ai/settings/sync.py" --dry-run   # verify what will change
python3 "scripts/°base/ai/settings/sync.py"              # apply
```

This regenerates `.claude/settings.json`, moving `"bugsink"` from `disabledMcpjsonServers` into `enabledMcpjsonServers`. That's the file Claude Code actually reads.

## Gotcha: `.codex/config.toml` can silently fight you

`sync.py` treats *all* native files (`.claude/settings.json`, `.mcp.json`, `.codex/config.toml`) as round-trippable sources, merged back into the shared config by file mtime. `.mcp.json` has no `enabled` concept so it's harmless.
**`.codex/config.toml` does encode `enabled` explicitly**, inside its generated block:

```toml
# --- BEGIN generated mcp_servers (scripts/°base/ai/settings/sync.py) ---
[mcp_servers."bugsink"]
enabled = false        # <-- if this is stale/false, it wins
...
# --- END generated mcp_servers ---
```

If a previous sync left `enabled = false` baked in here, it gets merged back into the shared config *during the same `_load_layer` call that renders `.claude/settings.json`*
— so your edit to `ai/settings/settings.json` gets silently overridden back to `false` before it ever reaches `.claude/settings.json`.
Symptom: `sync.py --dry-run` only reports `Would write: ai/settings/settings.json` (just re-normalizing) and never mentions `.claude/settings.json` at all, even though you just changed `enabled` to `true`.

**Fix:** grep for the server under `.codex/config.toml`'s generated block and flip `enabled` there too, matching the shared file, *before* rerunning sync:

```bash
grep -n -A2 'mcp_servers\."bugsink"' .codex/config.toml
```

## Verifying it

```bash
python3 "scripts/°base/ai/settings/sync.py" --dry-run
# expect: Would write: .claude/settings.json   (nothing else)
python3 "scripts/°base/ai/settings/sync.py"
grep -n -A3 'enabledMcpjsonServers' .claude/settings.json
# expect "bugsink" listed there, disabledMcpjsonServers empty (or without it)
```

If `--dry-run` still doesn't mention `.claude/settings.json` after fixing the Codex file, another native source is winning the merge — reproduce `°settings_lib.cli._load_layer(...)` in a one-off Python snippet (see `scripts/°base/ai/settings/°settings_lib/cli.py`) and print `shared["mcp"]["servers"]["bugsink"]` after each merge step to find which file is reintroducing `enabled: false`.
