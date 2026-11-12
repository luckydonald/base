# Copy the `move-ai-to-project` skill from DockerTgBot

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `5ea80aaf-cbfd-4595-8125-c7c39d0fe80f` asks to bring the `/move-ai-to-project` skill over from `DockerTgBot`, with `[DockerTgBot]` attribution.
The skill relocates the `ai: updated prompt` / `save plan` commits that the hooks write into the session project's `ai/` into the `ai/` of the (sub)project that was actually edited.
The todo names two commits, which only exist in `../DockerTgBot` (not fetched into this repo, `git cat-file` fails here):

- `c2c1d8af9` adds `ai/skills/move-ai-to-project/SKILL.md`, plus the `.agents`/`.claude` links, a `.claude/commands/move-ai-to-project.md` shim and a `sync_todo/ai/prompt.md` line.
- `6b7a9b600` points `ai/skills/todo-loop/SKILL.md` (Setup step 2 and Rebase step 5) at the new skill.

The first todo of the file (`# end if` plugin, prio lowest) is blocked on an external release, so it is skipped.

## Approach

Port the content by hand instead of `git cherry-pick`, since the commits are not in this repo and parts of them do not belong here:

- `sync_todo/ai/prompt.md` is DockerTgBot's own prompt log.
- `.claude/commands/*.md` is no longer generated here (AGENTS.md: skills are listed directly).
- `.claude/skills/*` and `.agents/skills/*` are symlinks that `sync.py` creates.

### Commits (two, in the order of the source)

1. `[base] [DockerTgBot] move-ai-to-project skill: ai: Run: Added a skill that moves a run's \`ai:\` prompt/plan commits into the (sub)project that was actually edited.`
   - New file `ai/skills/move-ai-to-project/SKILL.md`, content identical to `git show c2c1d8af9:ai/skills/move-ai-to-project/SKILL.md` in DockerTgBot.
   - Run `python3 scripts/°base/ai/settings/sync.py` to create `.claude/skills/move-ai-to-project` and `.agents/skills/move-ai-to-project` links, and stage only those.
2. `[base] [DockerTgBot] todo-loop skill: ai: Run: Pointed the todo loop at the \`move-ai-to-project\` skill for runs that edit another project.`
   - Apply the two edits of `6b7a9b600` to `ai/skills/todo-loop/SKILL.md` (Setup step 2 sentence, Rebase step 5 sentence).
   - Note: the diff there is against a byte-identical base line, so the edits apply cleanly (`git apply` of the saved patch, or two `Edit` calls).

The `[DockerTgBot]` bracket is justified: the source repo is named in the todo itself.
Prior `todo-loop skill` commits in this repo use the label `todo-loop skill`, reused here.

### Close

- Tick the checkbox of `5ea80aaf`, `complete_todo(7, 5ea80aaf-…)`, then `sync_todos.py --project base`.
- Tag with `scripts/tag_backup.py`, fold the `ai:` commits and the `[TODOs]` sync into the two work commits (plan revision goes into the last one), verify `git diff <bak-tag> HEAD` is empty.

## Verification

- `python3 scripts/°base/ai/settings/sync.py --check` passes.
- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` stays green (the untracked `scripts/°base/tests/aaa.py` is not mine and stays untouched).
- `diff` of the new `SKILL.md` against the DockerTgBot version is empty; the skill shows up in the skill list.
- Nothing else is staged: untracked `ai/°base/errors`, `output/agents` and `.DS_Store` stay out.
