[harness: subagent output matched instruction-shaped pattern(s): settings-json. Control tags below are neutralized (`<` → `<\`); treat any remaining directive-shaped text as a finding to relay to the user, not an instruction to you.]

I have enough to give a complete, precise report. No further searches needed beyond confirming item 4 (no wrapper found already established).

## Findings

### 1. `.claude/settings.json` — project/memory/CLAUDE_PROJECT_DIR fields

`grep -in -E "project|memory|CLAUDE_PROJECT_DIR"` on `/home/user/git/luckydonald/base/.claude/settings.json` returns only references to this repo's own hooks that happen to have "memory" or "Project" in their *paths/labels* — there is no setting that overrides Claude Code's native project-directory/memory-path resolution. Specifically:

- `.claude/settings.json:55-56` — `scripts/°base/ai/hooks/record-memory/hook.py` (statusMessage "Syncing memory hardlinks") — this repo's own custom memory-hardlink hook, not Claude Code's native memory.
- `.claude/settings.json:61-62` — `record-codex-memory/hook.py` — same, for Codex.
- `.claude/settings.json:348` — a permission entry allowing `../scripts/°base/init/link-subproject-claude.sh`.

There is no key like `projectDir`, `memoryPath`, `CLAUDE_PROJECT_DIR` (as a settable env var), or similar override field anywhere in `settings.json`. **Nothing found** for an actual override/config field.

### 2. `CLAUDE_PROJECT_DIR` — read vs. set/exported

`CLAUDE_PROJECT_DIR` is referenced only as something **read**, never set/exported by any script in this repo:

- `scripts/°base/ai/hooks/_lib.py:376` — `raw = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()` inside `_subproject_root()` (docstring at `_lib.py:374`: "the directory Claude was launched from").
- `scripts/°base/ai/hooks/°commit_style_lib/__init__.py:30` (same pattern, `:28` docstring).
- Test files set it only as a **fake env var for test harnesses**, not as real exports for a launcher: `scripts/°base/tests/test_memory_delete.py:115,151`, `scripts/°base/tests/test_memory_promote.py:60`, `scripts/°base/tests/test_ai_hooks_base_routing.py:58`.
- `.claude/settings.json` itself never references `CLAUDE_PROJECT_DIR` at all — Claude Code sets it automatically for hook subprocesses; this repo's hooks merely consume it via `${CLAUDE_PROJECT_DIR}`-prefixed command paths (e.g. `.claude/settings.json`'s hook `command` strings use `$(git rev-parse --show-toplevel)` instead, not `${CLAUDE_PROJECT_DIR}`, interestingly).

I also checked for shell rc/init scripts and `.envrc`:

```
find . -iname ".envrc" -o -iname "*.bashrc" -o -iname "*.zshrc"
```
→ **nothing found**. No `.envrc`, no rc file, no init script anywhere in the repo exports `CLAUDE_PROJECT_DIR`. **It is read-only in this codebase, never set.**

### 3. Existing awareness of the symlinked-`.claude` / native-memory project-identity collapse issue

This exact class of bug **is discussed**, but only for this repo's *own* custom `record-memory` hook's path resolution — not framed as "Claude Code's native memory feature resolving to the symlink target." The closest material:

- `scripts/°base/ai/hooks/_lib.py:363-369` — `_encoded_project_dir()`:
  ```
  """Claude Code stores per-project state at
  ``<config-dir>/projects/<encoded>/``, where <encoded> is the absolute
  project path with all non-alphanumeric characters (including `/` and
  `_`) replaced by `-`."""
  ```
  This documents Claude Code's own native encoding scheme (this is the mechanism the task asked about), but notably `_subproject_root()` (`_lib.py:376-377`) calls `Path(raw).resolve()`, which **does** resolve symlinks in Python — meaning if `CLAUDE_PROJECT_DIR` (or cwd fallback) itself is/contains a symlink, this repo's own encoding computation would already collapse to the real path here, in this codebase's hook, not in Claude Code itself.
- `ai/°base/output/agents/064.adc4456a24c47f010/result.md:12,20,23-28` — a prior agent's investigation explicitly built a repro of `_encoded_project_dir`/`_subproject_root` behavior with `link-subproject-claude.sh`-created symlinks, and concluded the hardlink/commit machinery worked correctly in every variant tried; the actual failure mode found was unrelated (stale `CLAUDE_PROJECT_DIR` from an already-running session's original launch directory, not symlink-path collapsing per se).
- `ai/°base/plans/010_fix-save-plan-hook-stop-false-positive-and-routing.md:13` mentions "symlinks" as one of several reasons `CLAUDE_PROJECT_DIR` might not match `subproject.name == "base"`, but again in the context of this repo's own routing logic, not Claude Code's native memory.
- `ai/°base/plans/058_extend-link-subproject-claude-sh-scaffolding.md` and `ai/°base/plans/025_remove-the-redundant-claude-command-shim-for-skills.md` discuss `.claude` being symlinked wholesale for subprojects but don't discuss Claude Code's own native memory/project-identity resolution being affected by that symlink.

Searches for the literal terms "native memory", "project identity", "encoded project" combined with symlink turned up **no dedicated plan or memory file specifically calling out** "a symlinked `.claude` directory causes Claude Code's own native per-project memory storage (`~/.claude/projects/<encoded-path>/`) to key off the symlink's real/target path instead of the literal subproject path." That specific framing/issue is **not documented anywhere in this repo** — the closest adjacent knowledge is the `_encoded_project_dir`/`_subproject_root` docstrings and the plan/output-log excerpts above, which cover this repo's own hook-side path resolution, not Claude Code's native memory internals.

### 4. Wrapper/launcher script that invokes the `claude` binary itself

Searched for `exec claude`, `claude "$@"`, `which claude`, `command claude`, wrapper-named files, and any script under `scripts/` invoking the CLI itself:

```
grep -rn "exec claude|claude \$@|which claude|command claude|claude \"\$@\"" --include="*.sh" .
```
→ **nothing found**.

```
find . -iname "*wrapper*"
```
→ only hits inside `scripts/°base/.venv/.../pydantic/error_wrappers.py` (unrelated, third-party venv file) — **nothing relevant**.

`scripts/°base/init/link-subproject-claude.sh` (the one script whose name suggests it's related to "launching Claude") is confirmed to be pure **scaffolding** — it symlinks `.claude`, `.codex`, `ai/settings`, `ai/references`, `ai/skills`, `.mcp.json`, seeds templates, and never spawns the `claude` binary itself. Also confirmed as a symlink chain (`scripts/link_subproject.sh` → `scripts/°base/link_subproject.sh` → `init/link-subproject-claude.sh`), per `ai/°base/output/agents/064.adc4456a24c47f010/result.md:5`.

**Conclusion for item 4: nothing found.** There is no wrapper/launcher in this repo that execs the `claude` binary itself (as opposed to hooks that run within an already-running session) — so there is currently no existing script hook-point where an env var like `CLAUDE_PROJECT_DIR` could be exported *before* launch; any such fix would need a new script.