In the repo at /home/user/git/luckydonald/base, there are multiple memory-related directories under scripts/°base/:

1. scripts/°base/ai/hooks/°memory_lib — a shared library package
2. scripts/°base/ai/hooks/record-codex-memory — a hook
3. scripts/°base/ai/hooks/record-memory — a hook
4. scripts/°base/ai/memory — some directory (need to check what's in it — is it code, or actual memory data?)
5. scripts/°base/memories — some other directory

I need a thorough report to help plan whether these can be merged/consolidated. Please investigate and report:

1. For EACH of these 5 directories: what files are in them (full listing), and what is their actual purpose/role? Read key files (hook.py, delete.py, __init__.py, etc.) to summarize what each does. Is `scripts/°base/ai/memory` actual memory content (like the project's `ai/°base/memory/*.md` notes) or is it code/tooling? Same question for `scripts/°base/memories`.

2. Are any of these directories redundant, leftover, deprecated, or unused? Check git log/git blame for hints (e.g. `git log --oneline -- <path>` to see if a directory has been actively touched recently vs abandoned long ago).

3. Specifically investigate "link/unlink" technology: search the codebase (grep) for functions/modules related to linking or unlinking memory files (e.g. `unlink_path`, `hardlink`, `symlink`, `link_path`, files named `delete.py`, `link.py` under `°memory_lib` or elsewhere). Determine:
   - What the link/unlink mechanism is for (e.g. hardlinking synced memory files between locations)
   - Which current code paths actually call it today (grep for importers/callers)
   - Whether it appears to be actively used, or vestigial/dead code from an older architecture

4. Check for any references to these paths in documentation (ai/°base/AGENTS.md, README files, memory files under ai/°base/memory/*.md — especially ones with "memory" or "dual" or "codex" in the name, since a prior session's memory file mentioned "Dual work/private Codex config dirs" and there may be others describing this architecture).

5. Note any naming/path inconsistencies (e.g. `memory` vs `memories`, `°memory_lib` vs `memory_lib`) and any places that hardcode these paths (grep for the literal strings "scripts/°base/memories", "ai/hooks/°memory_lib", "ai/memory" import paths, etc.) — this tells us how risky a rename/merge would be.

Do NOT propose the actual plan or make any edits — this is read-only research. Report back with:
- A clear directory-by-directory breakdown (purpose, is it data or code, active or dead)
- The link/unlink findings (used today or not, and by what)
- A list of every file location that references these paths (for impact assessment)
- Any obvious redundancy or candidates for merging, with your reasoning

Be thorough — this repo uses `°` (degree sign) prefixed directory names as a deliberate namespacing convention (see AGENTS.md), so don't assume typos.