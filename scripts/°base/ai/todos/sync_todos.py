#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2.3", "pydantic>=2.6", "python-dotenv>=1.0"]
# ///
"""Sync the todos of the `sync_todo` CalDAV list into the todo files of other projects.

Reads the list live through the sync_todo MCP server (`list_todos`, read-only, needs the
`mcp_todos_read` scope), assigns every todo to a project by its `#Tag` prefix / category, and
merges them into that project's todo markdown file. One-way: CalDAV is the source of truth.

    uv run scripts/°base/ai/todos/sync_todos.py [--dry-run] [--no-git] [-v] [--project NAME] [--purge-missing] [--purge-complete|--purge-completed] [--include-completed|--include-complete] [--reset-todo-file] [--add-files|--add] [--config PATH]
    uv run scripts/°base/ai/todos/sync_todos.py --write-schema

The tag to project mapping is tracked in `ai/settings/sync_todos.json`, the schemas for IDE completion are `ai/settings/sync_todos.schema.json` and `ai/settings/sync_todos-local.schema.json`.
Where a project lives on this machine is not: `ai/settings/sync_todos.local.json` (gitignored) maps each project name to a `path` and may override its `commit_prefix`.
Every run adds a `null` entry for each project that is missing there; a project with a `null` path is skipped, so nothing outside the configured paths is ever written. Line format:

    - [ ] text — `todo:<uid>` _(state)_
      > description line

Only lines carrying a `todo:<uid>` are managed; everything else in the file is left alone. The `>` lines of a managed todo follow its CalDAV description: notes written above or below an unchanged description stay, a changed description replaces the block and the lines that go are reported.
New todos go under `## Todos synced from CalDAV` (the old `## Synced from CalDAV` still counts); a file that does not exist yet starts from `todos.template.md` next to this script, and the old bare `# Todos` header is upgraded to it; completed ones that are not in the file yet are ignored (`--include-completed`). `--purge-missing` / `--purge-complete` then clean up, each as its own commit. `--reset-todo-file` (needs `--project`, git, and a file without uncommitted changes) first rebuilds the file from the template plus its checkbox lines and their `>` rows, as its own commit; what it dropped is printed. Files that a summary or description mentions (`@path` or `` `dir/file` ``, resolved against the project's git root) and that exist are written as markdown links relative to the todo file, like `ai/query.md` does; `--add-files` also commits the mentioned files that have changes. Every written file is committed as
`{commit_prefix}[TODOs] synced todos for {projects}.` in the git root of each project (one commit per repo and prefix, only those files; `--no-git` skips it).
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import functools
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema



def resolve_roots(file: str) -> tuple[Path, Path, Path, Path, Path]:
    """(git root, tracked config, its schema, local config, its schema) for the script started as `file`.

    The git root is asked from git, never guessed from a folder name, so it is the checkout the base was merged into.
    `abspath` keeps a symlinked location, `resolve()` would follow it somewhere else.
    """
    here = Path(os.path.abspath(file))
    top = subprocess.run(["git", "-C", str(here.parent), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    root = Path(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else here.parents[4]
    settings = root / "ai" / "settings"
    return root, settings / "sync_todos.json", settings / "sync_todos.schema.json", settings / "sync_todos.local.json", settings / "sync_todos-local.schema.json"
# end def


REPO_ROOT, DEFAULT_CONFIG, SCHEMA_PATH, LOCAL_CONFIG, LOCAL_SCHEMA_PATH = resolve_roots(__file__)
SECTION = "## Todos synced from CalDAV"
LEGACY_SECTION = "## Synced from CalDAV"
OLD_TEMPLATE_HEADER = "# Todos"
NEW_TEMPLATE_MARKER = "## For Agents"
TEMPLATE_PATH = Path(os.path.realpath(__file__)).with_name("todos.template.md")
VERBOSE = False
HOOKS_DIR = Path(os.path.abspath(__file__)).parents[1] / "hooks"
LINKED: dict[str, list[Any]] = {}  # project name -> file mentions linked while rendering, for `--add-files`


def vlog(message: str) -> None:
    """Detail about every comparison, only with --verbose."""
    if VERBOSE:
        print(f"  . {message}")
    # end if
# end def


def short(uid: str) -> str:
    return uid[:8]
# end def


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Label, also used by --project.")
    tags: list[str] = Field(
        min_length=1,
        description="`#Tag` summary prefixes / categories that belong to this project (matched case-insensitively).",
    )
    path: SkipJsonSchema[str | None] = Field(
        default=None, exclude=True,
        description="Project root on this machine, from the local config only (null: skipped). `~` is expanded, relative paths are relative to the git root.",
    )
    todo_file: str = Field(default="ai/todos.md", description="Todo markdown file, relative to `path`.")
    commit_prefix: str | None = Field(
        default=None,
        description="Prefix of the commit message for this project, e.g. `[sync_todo] ` for a subproject. Overrides the global one, and is itself overridden by the local config; null inherits it.",
    )

    @field_validator("tags")
    @classmethod
    def tags_nonblank(cls, tags: list[str]) -> list[str]:
        if any(not t.strip() for t in tags):
            raise ValueError("tags must not be blank")
        # end if
        return tags
    # end def

    def root(self) -> Path:
        if self.path is None:
            raise ValueError(f"project {self.name!r} has no path in {LOCAL_CONFIG.name}")
        # end if
        root = Path(os.path.expanduser(self.path))
        if not root.is_absolute():
            root = REPO_ROOT / root
        # end if
        return root
    # end def

    def file(self) -> Path:
        return self.root() / self.todo_file
    # end def
# end class


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: str | None = Field(default=None, alias="$schema")
    url_env: str = Field(default="SYNC_TODO_MCP_URL", description="Env var holding the MCP server URL.")
    token_env: str = Field(default="SYNC_TODO_MCP_TOKEN", description="Env var holding the bare `sytd_...` token.")
    env_file: str | None = Field(default="ai/.env", description="Env file (relative to the git root) to load first.")
    commit_prefix: str = Field(default="", description="Default prefix of the commit messages, e.g. `[root] `.")
    calendar_id: int = Field(default=7, description="Calendar to read (7 = `TODO: Today`).")
    projects: list[Project] = Field(min_length=1)

    @model_validator(mode="after")
    def unique(self) -> "Config":
        names: set[str] = set()
        tags: dict[str, str] = {}
        for p in self.projects:
            if p.name.casefold() in names:
                raise ValueError(f"duplicate project name {p.name!r}")
            # end if
            names.add(p.name.casefold())
            for t in p.tags:
                other = tags.setdefault(t.casefold(), p.name)
                if other != p.name:
                    raise ValueError(f"tag {t!r} is used by both {other!r} and {p.name!r}")
                # end if
            # end for
        # end for
        return self
    # end def
# end class


class LocalProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | None = Field(
        default=None,
        description="Project root on this machine. `~` is expanded, relative paths are relative to the git root. null: the project is skipped, nothing is read or written there.",
    )
    commit_prefix: str | None = Field(default=None, description="Overrides the tracked per-project and global commit prefix; null keeps them.")
# end class


class LocalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: str | None = Field(default=None, alias="$schema")
    projects: dict[str, LocalProject] = Field(default_factory=dict, description="Project name (as in the tracked mapping) to its machine-local settings.")
# end class


def _schema_text(model: type[BaseModel], file_name: str, title: str) -> str:
    """The model's JSON schema, headed like the `ai/settings/settings*.schema.json` files (draft, `$id`, title)."""
    body = model.model_json_schema(by_alias=True)
    body.pop("title", None)
    head = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://github.com/luckydonald/base/ai/settings/{file_name}",
        "title": title,
    }
    return json.dumps({**head, **body}, indent=2, ensure_ascii=False) + "\n"
# end def


def schema_text() -> str:
    return _schema_text(Config, SCHEMA_PATH.name, "Tracked todo sync mapping (tags to projects)")
# end def


def local_schema_text() -> str:
    return _schema_text(LocalConfig, LOCAL_SCHEMA_PATH.name, "Machine-local todo sync settings (project paths)")
# end def


def load_config(tracked: Path, local: Path, write_local: bool = True) -> Config:
    """The tracked mapping with the machine-local paths and prefix overrides applied.

    A `path` in the tracked file is refused (it would be wrong on every other machine).
    Missing projects are added to the local file with `null` values, existing values are never touched.
    """
    raw = json.loads(tracked.read_text(encoding="utf-8"))
    for project in raw.get("projects", []):
        if isinstance(project, dict) and "path" in project:
            raise ValueError(f"{tracked.name}: project {project.get('name')!r} has a `path`, put it into {local.name} instead")
        # end if
    # end for
    config = Config.model_validate(raw)
    local_config = LocalConfig.model_validate_json(local.read_text(encoding="utf-8")) if local.exists() else LocalConfig()
    added = [p.name for p in config.projects if p.name not in local_config.projects]
    for name in added:
        local_config.projects[name] = LocalProject()
    # end for
    if added and write_local:
        data = {"$schema": f"./{LOCAL_SCHEMA_PATH.name}", **local_config.model_dump(exclude={"schema_"})}
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"added {', '.join(added)} to {local.name} with a null path (set one to enable the project)", file=sys.stderr)
    # end if
    stale = sorted(set(local_config.projects) - {p.name for p in config.projects})
    if stale:
        print(f"{local.name} has projects that are not in {tracked.name}: {', '.join(stale)}", file=sys.stderr)
    # end if
    for project in config.projects:
        entry = local_config.projects[project.name]
        project.path = entry.path
        if entry.commit_prefix is not None:
            project.commit_prefix = entry.commit_prefix
        # end if
    # end for
    return config
# end def


# --------------------------------------------------------------------------- assignment

PREFIX = re.compile(r"^\s*#(\w[\w-]*)\s*")


def todo_tags(todo: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    m = PREFIX.match(todo.get("summary") or "")
    if m:
        found.add(m.group(1).casefold())
    # end if
    for c in todo.get("categories") or []:
        c = c.strip()
        if c.casefold().startswith("category:"):
            c = c.split(":", 1)[1].strip()
        # end if
        found.add(c.lstrip("#").casefold())
    # end for
    return found
# end def


def assign(todos: list[dict[str, Any]], projects: list[Project]) -> dict[str, list[dict[str, Any]]]:
    """Project name -> its todos (CalDAV order). Untagged subtasks inherit from their parent."""
    by_uid = {t["uid"]: t for t in todos}
    owner: dict[str, str | None] = {}

    def resolve(todo: dict[str, Any], seen: frozenset[str] = frozenset()) -> str | None:
        uid = todo["uid"]
        if uid in owner:
            return owner[uid]
        # end if
        tags = todo_tags(todo)
        result = next((p.name for p in projects if tags & {t.casefold() for t in p.tags}), None)
        parent = by_uid.get(todo.get("parent_uid") or "")
        if result is None and parent is not None and uid not in seen:
            result = resolve(parent, seen | {uid})
        # end if
        owner[uid] = result
        via = "tags " + ",".join(sorted(tags)) if tags else "no tags"
        vlog(f"assign {short(uid)} {(todo.get('summary') or '')[:40]!r}: {via} -> {result or 'nobody'}"
             + (" (inherited from parent)" if result and not tags & {t.casefold() for p in projects if p.name == result for t in p.tags} else ""))
        return result
    # end def

    out: dict[str, list[dict[str, Any]]] = {p.name: [] for p in projects}
    for todo in todos:
        name = resolve(todo)
        if name:
            out[name].append(todo)
        # end if
    # end for
    return out
# end def


# --------------------------------------------------------------------------- rendering

@functools.cache
def reffiles() -> Any | None:
    """The `°reffiles_lib` of the base hooks (the one that links files in `ai/query.md`), None if the base is not checked out."""
    if not HOOKS_DIR.is_dir():
        vlog(f"{HOOKS_DIR} not found, file mentions stay plain text")
        return None
    # end if
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    # end if
    try:
        return importlib.import_module("°reffiles_lib")
    except ImportError as e:
        vlog(f"°reffiles_lib not importable ({e}), file mentions stay plain text")
        return None
# end def


def link_root(project: Project) -> Path:
    """Git root of the project (mentions are resolved against it), else the project root."""
    top = git(project.root(), "rev-parse", "--show-toplevel")
    return Path(top.stdout.strip()) if top.returncode == 0 else project.root()
# end def


def link_files(text: str, project: Project) -> str:
    """Turn `@path` / `` `dir/file` `` mentions of existing files into markdown links relative to the project's todo file, like the
    `ai/query.md` hook does. Applied to the CalDAV text before it is compared or written, so both sides stay equal and a sync is idempotent."""
    lib = reffiles()
    if lib is None or "/" not in text:
        return text
    # end if
    root = link_root(project)
    here = os.getcwd()
    os.chdir(root)  # the library resolves against the cwd
    try:
        linked, resolved = lib.process_referenced_files(text, root, project.file())
    finally:
        os.chdir(here)
    if resolved:
        LINKED.setdefault(project.name, []).extend(resolved)
    # end if
    return linked
# end def


def commit_mentions(project: Project) -> None:
    """`--add-files`: stage and commit the files the todos of `project` mention (those with changes, as the query.md hook does)."""
    lib = reffiles()
    mentions = LINKED.get(project.name)
    if lib is None or not mentions:
        return
    # end if
    here = os.getcwd()
    os.chdir(link_root(project))
    try:
        lib.stage_and_commit_mentions(mentions)
    finally:
        os.chdir(here)
# end def


def clean_summary(todo: dict[str, Any], project: Project) -> str:
    text = " ".join((todo.get("summary") or "").split())
    m = PREFIX.match(text)
    if m and m.group(1).casefold() in {t.casefold() for t in project.tags}:
        text = text[m.end():]
    # end if
    return link_files(text, project) if text else "(no title)"
# end def


def checkbox_and_state(todo: dict[str, Any]) -> tuple[str, str]:
    status = todo.get("status")
    pct = todo.get("percent_complete")
    if status == "COMPLETED":
        return "x", "_(done)_"
    # end if
    if status == "CANCELLED":
        return "-", "_(cancelled)_"
    # end if
    if status == "IN-PROCESS":
        return "…", f"_(in process, {pct}%)_" if pct else "_(in process)_"
    # end if
    if status == "NEEDS-ACTION":
        return "!", "_(needs action)_"
    # end if
    return " ", ""
# end def


def render(todo: dict[str, Any], project: Project, indent: int = 0) -> list[str]:
    box, state = checkbox_and_state(todo)
    pad = " " * indent
    head = f"{pad}- [{box}] {clean_summary(todo, project)} — `todo:{todo['uid']}`"
    if state:
        head += f" {state}"
    # end if
    lines = [head]
    for line in link_files((todo.get("description") or "").strip(), project).splitlines():
        lines.append(f"{pad}  > {line}".rstrip())
    # end for
    return lines
# end def


STATE = re.compile(r"\s*_\((?:done|cancelled|needs action|in process[^)]*|missing|partial)\)_")


def update_line(line: str, todo: dict[str, Any], project: Project) -> str:
    """Refresh checkbox, summary and state marker of an existing line; keep hand-written
    annotations after the uid and the description lines below it untouched."""
    m = MANAGED.match(line)
    assert m
    indent = m.group("indent")
    box, state = checkbox_and_state(todo)
    tail = line[m.end():]  # after the closing backtick of `todo:<uid>`
    tail = STATE.sub("", tail).rstrip()
    if state:
        tail += f" {state}"
    # end if
    return f"{indent}- [{box}] {clean_summary(todo, project)} — `todo:{m.group('uid')}`{tail}"
# end def


def render_tree(todos: list[dict[str, Any]], project: Project) -> dict[str, list[str]]:
    """uid -> its own lines (todo + description), without children."""
    return {t["uid"]: render(t, project) for t in todos}
# end def


# --------------------------------------------------------------------------- merge

MANAGED = re.compile(r"^(?P<indent>\s*)- \[.\] .* — `todo:(?P<uid>[0-9A-Za-z-]+)`")


def block_end(lines: list[str], start: int) -> int:
    """Index after the managed line at `start`: its `>` description lines only."""
    indent = len(MANAGED.match(lines[start]).group("indent"))  # type: ignore[union-attr]
    desc = " " * (indent + 2) + ">"
    i = start + 1
    while i < len(lines) and lines[i].startswith(desc):
        i += 1
    # end while
    return i
# end def


def subtree_end(lines: list[str], start: int) -> int:
    indent = len(MANAGED.match(lines[start]).group("indent"))  # type: ignore[union-attr]
    i = block_end(lines, start)
    while i < len(lines):
        if not lines[i].strip():
            break
        # end if
        if len(lines[i]) - len(lines[i].lstrip()) <= indent:
            break
        # end if
        i += 1
    # end while
    return i
# end def


def render_template(template: str, project: Project, calendar_id: int) -> str:
    """Fill the `{{project}}`, `{{calendar_id}}` and `{{script}}` (path to this script from the project root) placeholders."""
    script = os.path.relpath(Path(os.path.abspath(__file__)), project.root())
    return template.replace("{{project}}", project.name).replace("{{calendar_id}}", str(calendar_id)).replace("{{script}}", script)
# end def


def new_todo_file_text(project: Project, calendar_id: int) -> str:
    """The text of a todo file that does not exist yet: the template, or just the heading without one."""
    if not TEMPLATE_PATH.exists():
        return OLD_TEMPLATE_HEADER + "\n\n"
    # end if
    return render_template(TEMPLATE_PATH.read_text(encoding="utf-8"), project, calendar_id)
# end def


def upgrade_old_template(text: str, new_template: str) -> str:
    """Replace the bare header this script used to write (`# Todos`, blank, then the synced section) with `new_template`.

    Only the tail of the file counts: whatever is above the last `# Todos` line stays on top, the managed section below it is kept
    (its heading is renamed to the current one). A file that already has the new template's `## For Agents`, or whose last `# Todos`
    is followed by anything else than blanks and the synced section, is returned unchanged, so this is a no-op the second time.
    """
    lines = text.split("\n")
    if NEW_TEMPLATE_MARKER in lines:
        return text
    # end if
    starts = [i for i, line in enumerate(lines) if line.rstrip() == OLD_TEMPLATE_HEADER]
    if not starts:
        return text
    # end if
    start = starts[-1]
    rest = lines[start + 1:]
    first = next((i for i, line in enumerate(rest) if line.strip()), None)
    if first is not None and rest[first].rstrip() not in (SECTION, LEGACY_SECTION):
        vlog(f"`{OLD_TEMPLATE_HEADER}` is followed by something else, not the old template, left alone")
        return text
    # end if
    head = new_template.rstrip("\n").split("\n")
    manual = lines[:start]
    while manual and not manual[-1].strip():
        manual.pop()
    # end while
    prefix = manual + [""] if manual else []
    if first is None:
        return "\n".join(prefix + head) + "\n\n"
    # end if
    # the template ends with the section heading, the old block brings its own heading and managed lines
    if head and head[-1].rstrip() == SECTION:
        head.pop()
    # end if
    return "\n".join(prefix + head + [SECTION] + rest[first + 1:])
# end def


def refresh_description(
    lines: list[str], start: int, end: int, todo: dict[str, Any], project: Project, indent: int, report: list[str],
) -> int:
    """Bring the `>` description lines of the managed line at `start` up to CalDAV's text; returns the new block end.

    A block that contains CalDAV's text as it is, with or without notes written above or below it, stays as it is.
    Any other block means the description was edited on CalDAV and is replaced; lines that are gone are reported,
    never dropped silently. (CalDAV removing the whole description counts as notes: an empty text is in everything.)"""
    rendered = render(todo, project, indent)[1:]
    block = lines[start + 1:end]
    if any(block[at:at + len(rendered)] == rendered for at in range(len(block) - len(rendered) + 1)):
        return end
    # end if
    dropped = [line.strip().removeprefix(">").strip() for line in block if line not in rendered]
    vlog(f"{short(todo['uid'])}: description differs, replaced\n      file:    {block}\n      CalDAV:  {rendered}")
    lines[start + 1:end] = rendered
    report.append(f"description changed on CalDAV: {todo['uid']}")
    report += [f"  dropped: {line}" for line in dropped if line]
    return start + 1 + len(rendered)
# end def


def merge(text: str, todos: list[dict[str, Any]], project: Project, include_completed: bool = False) -> tuple[str, list[str]]:
    """Merge `todos` into the markdown `text`. Returns (new text, report lines)."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    # end if
    report: list[str] = []
    mine = {t["uid"]: t for t in todos}

    # update existing, remember local ticks that CalDAV does not know
    i = 0
    seen: set[str] = set()
    while i < len(lines):
        m = MANAGED.match(lines[i])
        if not m:
            i += 1
            continue
        # end if
        uid, indent = m.group("uid"), len(m.group("indent"))
        end = block_end(lines, i)
        if uid in mine:
            if lines[i][indent:].startswith("- [x]") and mine[uid].get("status") != "COMPLETED":
                report.append(f"local tick not on CalDAV (not pushed): {uid}")
            # end if
            updated = update_line(lines[i], mine[uid], project)
            if updated == lines[i]:
                vlog(f"{short(uid)}: unchanged")
            else:
                vlog(f"{short(uid)}: line differs\n      file:    {lines[i]}\n      CalDAV:  {updated}")
            # end if
            lines[i] = updated
            end = refresh_description(lines, i, end, mine[uid], project, indent, report)
            seen.add(uid)
            i = end
        else:
            vlog(f"{short(uid)}: in file, not assigned to {project.name} (left alone)")
            i = end
        # end if
    # end while

    # new todos: under their parent if it is in the file, else in the managed section
    # (completed ones that are not in the file yet are ignored unless `include_completed`)
    new_todos = [
        t for t in todos
        if t["uid"] not in seen and not has_uid(lines, t["uid"])
        and (include_completed or t.get("status") != "COMPLETED")
    ]
    for t in todos:
        if t["uid"] not in seen and t not in new_todos and not has_uid(lines, t["uid"]):
            vlog(f"{short(t['uid'])}: completed and not in the file, ignored (--include-completed adds it)")
        # end if
    # end for
    pending = list(new_todos)
    progressed = True
    while pending and progressed:
        progressed = False
        for t in list(pending):
            parent = t.get("parent_uid")
            idx = find_uid(lines, parent) if parent else None
            if idx is None:
                continue
            # end if
            indent = len(MANAGED.match(lines[idx]).group("indent")) + 2  # type: ignore[union-attr]
            at = subtree_end(lines, idx)
            lines[at:at] = render(t, project, indent)
            report.append(f"added {t['uid']}")
            pending.remove(t)
            progressed = True
        # end for
    # end while
    roots = [t for t in pending]
    if roots:
        if SECTION not in lines and LEGACY_SECTION not in lines:
            if lines and lines[-1].strip():
                lines.append("")
            # end if
            lines += [SECTION, ""]
        # end if
        pos = len(lines)
        in_pending = {t["uid"] for t in roots}
        for t in roots:
            if (t.get("parent_uid") or "") in in_pending:
                continue  # emitted below its parent
            # end if
            block = with_children(t, roots, project, 0)
            lines[pos:pos] = block
            pos += len(block)
            report.append(f"added {t['uid']}")
        # end for
        for t in roots:
            if (t.get("parent_uid") or "") in in_pending:
                report.append(f"added {t['uid']}")
            # end if
        # end for
    # end if
    return "\n".join(lines) + "\n", report
# end def


def purge(text: str, matches: set[str], label: str) -> tuple[str, list[str]]:
    """Remove every managed line (with its description and children) whose uid, and the uid of
    every managed line below it, is in `matches`. A parent with a child that is not stays."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    # end if
    report: list[str] = []
    i = 0
    while i < len(lines):
        m = MANAGED.match(lines[i])
        if not m or m.group("uid") not in matches:
            i += 1
            continue
        # end if
        stop = subtree_end(lines, i)
        subtree = [x.group("uid") for x in map(MANAGED.match, lines[i:stop]) if x]
        if all(u in matches for u in subtree):
            report.extend(f"{label} {u}" for u in subtree)
            del lines[i:stop]
        else:
            kept = [u for u in subtree if u not in matches]
            vlog(f"{short(m.group('uid'))}: matches, but kept because of " + ", ".join(short(u) for u in kept))
            i += 1
        # end if
    # end while
    return "\n".join(lines) + "\n", report
# end def


def purge_missing(text: str, all_uids: set[str]) -> tuple[str, list[str]]:
    """Drop todos that no longer exist on CalDAV at all."""
    managed = {m.group("uid") for m in map(MANAGED.match, text.split("\n")) if m}
    vlog(f"{len(managed)} managed lines, {len(managed & all_uids)} still on CalDAV, {len(managed - all_uids)} missing")
    return purge(text, managed - all_uids, "purged missing")
# end def


def purge_complete(text: str, done_uids: set[str]) -> tuple[str, list[str]]:
    """Drop todos that are completed on CalDAV."""
    managed = {m.group("uid") for m in map(MANAGED.match, text.split("\n")) if m}
    vlog(f"{len(managed)} managed lines, {len(managed & done_uids)} completed on CalDAV")
    return purge(text, done_uids, "purged completed")
# end def


def with_children(todo: dict[str, Any], pool: list[dict[str, Any]], project: Project, indent: int) -> list[str]:
    out = render(todo, project, indent)
    for child in pool:
        if child.get("parent_uid") == todo["uid"]:
            out += with_children(child, pool, project, indent + 2)
        # end if
    # end for
    return out
# end def


def find_uid(lines: list[str], uid: str | None) -> int | None:
    for i, line in enumerate(lines):
        m = MANAGED.match(line)
        if m and m.group("uid") == uid:
            return i
        # end if
    # end for
    return None
# end def


def has_uid(lines: list[str], uid: str) -> bool:
    return find_uid(lines, uid) is not None
# end def


# --------------------------------------------------------------------------- MCP

def parse_result(result: Any) -> list[dict[str, Any]]:
    data = getattr(result, "structuredContent", None)
    if data is None:
        # FastMCP puts each list item into its own text block
        texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
        data = [json.loads(t) for t in texts]
        if len(data) == 1 and isinstance(data[0], list):
            data = data[0]
        # end if
    # end if
    if isinstance(data, dict):
        data = data.get("result", data)
    # end if
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected list_todos result: {str(data)[:200]}")
    # end if
    return data
# end def


async def fetch_todos(url: str, token: str, calendar_id: int) -> list[dict[str, Any]]:
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

    async with create_mcp_http_client(headers={"Authorization": f"Bearer {token}"}) as http:
        async with streamable_http_client(url, http_client=http) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("list_todos", {"calendar_id": calendar_id})
            if getattr(result, "isError", False):
                raise RuntimeError(f"list_todos failed: {result.content}")
            # end if
            return parse_result(result)
        # end with
    # end with
# end def


# --------------------------------------------------------------------------- main

def write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        # end with
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
# end def


LINE = re.compile(r"^(?P<indent>\s*)- \[(?P<box>.)\] (?P<summary>.*?) — `todo:(?P<uid>[0-9A-Za-z-]+)`(?P<tail>.*)$")
STATE_TEXT = re.compile(r"_\((?P<state>done|cancelled|needs action|in process[^)]*|missing|partial)\)_")
MAX_DETAIL_LINES = 30


def managed_todos(text: str) -> dict[str, dict[str, Any]]:
    """uid -> where it stands (`parent / child` path), checkbox, summary, state marker and `>` description rows; file order."""
    lines = text.split("\n")
    found: dict[str, dict[str, Any]] = {}
    stack: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if not m:
            continue
        # end if
        indent = len(m.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        # end while
        stack.append((indent, m.group("summary"), m.group("box")))
        rows: list[str] = []
        prefix = " " * (indent + 2) + ">"
        j = i + 1
        while j < len(lines) and lines[j].startswith(prefix):
            rows.append(lines[j].strip())
            j += 1
        # end while
        state = STATE_TEXT.search(m.group("tail"))
        found[m.group("uid")] = {
            "path": " / ".join(summary for _, summary, _ in stack), "box": m.group("box"), "summary": m.group("summary"),
            "shown": " / ".join(struck(summary, box) for _, summary, box in stack),
            "state": state.group("state") if state else "", "rows": rows,
        }
    # end for
    return found
# end def


def struck(text: str, box: str) -> str:
    """The text with a strikethrough if the checkbox says cancelled."""
    return f"~~{text}~~" if box == "-" else text
# end def


def describe_changes(old: str, new: str) -> list[str]:
    """What a stage did to the managed todos of a file, one short line per change, for the body of the commit message."""
    before, after = managed_todos(old), managed_todos(new)
    lines: list[str] = []
    for uid, now in after.items():
        was = before.get(uid)
        if was is None:
            lines.append(f"added: {now['shown']}" + (" (cancelled)" if now["box"] == "-" else ""))
            continue
        # end if
        if was["box"] != now["box"]:
            if now["box"] == "x":
                lines.append(f"ticked: {now['shown']}")
            elif now["box"] == "-":
                lines.append(f"cancelled: {now['shown']}")
            elif was["box"] == "x":
                lines.append(f"unticked: {now['shown']}")
            elif was["box"] == "-" and now["box"] == " ":
                lines.append(f"reopened: {now['shown']}")
            else:
                lines.append(f"checkbox [{was['box']}] -> [{now['box']}]: {now['shown']}")
            # end if
        elif was["state"] != now["state"]:
            lines.append(f"state: {now['shown']} ({was['state'] or 'none'} -> {now['state'] or 'none'})")
        # end if
        if was["summary"] != now["summary"]:
            lines.append(f"renamed: {struck(was['summary'], was['box'])} -> {struck(now['summary'], now['box'])}")
        # end if
        if was["rows"] != now["rows"]:
            lines.append(f"description changed: {now['shown']}")
        # end if
    # end for
    for uid, was in before.items():
        if uid not in after:
            lines.append(f"removed: {was['shown']}")
        # end if
    # end for
    return lines
# end def


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
# end def


def todo_dir_usable(project: Project) -> bool:
    """The todo file's folder exists, or can be created because the project root exists inside a git work tree
    (the folder is made when the file is written, so `--dry-run` creates nothing)."""
    folder = project.file().parent
    if folder.is_dir():
        return True
    # end if
    if not project.root().is_dir():
        print(f"[{project.name}] skipped, {project.root()} does not exist", file=sys.stderr)
        return False
    # end if
    if git(project.root(), "rev-parse", "--show-toplevel").returncode != 0:
        print(f"[{project.name}] skipped, {folder} does not exist and {project.root()} is not in a git repo", file=sys.stderr)
        return False
    # end if
    vlog(f"{project.name}: {folder} does not exist, will create it")
    return True
# end def


def commit_written(
    written: list[tuple[Project, Path]], default_prefix: str = "", action: str = "synced todos",
    details: dict[str, list[str]] | None = None,
) -> None:
    """Commit in the git root that contains each project (found from the project's own directory,
    so a subfolder of a monorepo commits in the monorepo root). One commit per (repo, prefix),
    limited to the written files, so other staged changes stay out."""
    groups: dict[tuple[str, str], list[tuple[Project, Path]]] = {}
    for project, path in written:
        top = git(path.parent, "rev-parse", "--show-toplevel")
        if top.returncode != 0:
            print(f"[{project.name}] not a git repo, not committing", file=sys.stderr)
            continue
        # end if
        prefix = project.commit_prefix if project.commit_prefix is not None else default_prefix
        vlog(f"{project.name}: git root {top.stdout.strip()}, prefix {prefix!r}")
        groups.setdefault((top.stdout.strip(), prefix), []).append((project, path))
    # end for
    for (top, prefix), items in groups.items():
        files = [str(path.resolve().relative_to(Path(top).resolve())) for _, path in items]
        names = ", ".join(dict.fromkeys(project.name for project, _ in items))
        added = git(Path(top), "add", "--", *files)
        if added.returncode != 0:
            print(f"[{names}] git add failed: {added.stderr.strip()}", file=sys.stderr)
            continue
        # end if
        if git(Path(top), "diff", "--cached", "--quiet", "--", *files).returncode == 0:
            vlog(f"{names}: nothing staged in {top} (ignored or unchanged in git), no commit")
            continue
        # end if
        several = len({project.name for project, _ in items}) > 1
        body = [
            f"- {f'[{project.name}] ' if several else ''}{line}"
            for project, _ in items for line in (details or {}).get(project.name, [])
        ]
        if len(body) > MAX_DETAIL_LINES:
            body = body[:MAX_DETAIL_LINES] + [f"- ... and {len(body) - MAX_DETAIL_LINES} more"]
        # end if
        message = ["-m", f"{prefix}[TODOs] {action} for {names}."] + (["-m", "\n".join(body)] if body else [])
        done = git(Path(top), "commit", *message, "--", *files)
        if done.returncode != 0:
            print(f"[{names}] git commit failed: {done.stderr.strip() or done.stdout.strip()}", file=sys.stderr)
        else:
            head = git(Path(top), "rev-parse", "--short=9", "HEAD").stdout.strip()
            print(f"[{names}] committed {head} in {top}: {prefix}[TODOs] {action} for {names}.")
        # end if
    # end for
# end def


KEPT_LINE = re.compile(r"^\s*[-*•]\s+\[[^\]\n]?\](?:\s|$)")
QUOTE_ROW = re.compile(r"^\s*>")


def reset_text(text: str, template: str) -> tuple[str, list[str]]:
    """The template followed by the todo-like lines of `text`; everything else is dropped (and reported).

    Todo-like: a checkbox line (`-`, `*` or `•`, then `[` any single character `]`, any indentation) and the
    `>` rows that directly follow it. The kept lines stay in their order, with their indentation."""
    kept: list[str] = []
    report: list[str] = []
    after_kept = False
    for line in text.split("\n"):
        if KEPT_LINE.match(line) or (after_kept and QUOTE_ROW.match(line)):
            kept.append(line)
            after_kept = True
            continue
        # end if
        after_kept = False
        if line.strip():
            report.append(f"dropped: {line.strip()}")
        # end if
    # end for
    return template.rstrip("\n") + "\n\n" + ("\n".join(kept) + "\n" if kept else ""), report
# end def


def reset_stage(text: str, project: Project, calendar_id: int) -> tuple[str, list[str]]:
    """Stage of `sync` for `--reset-todo-file`: see `reset_text`."""
    return reset_text(text, new_todo_file_text(project, calendar_id))
# end def


def assert_resettable(project: Project) -> None:
    """A reset throws text away, so the file must be in git with nothing uncommitted (the commit is the way back)."""
    path = project.file()
    if not project.todo_file.endswith(".md"):
        raise ValueError(f"[{project.name}] --reset-todo-file only works on markdown files, not {path.name}")
    # end if
    if not path.exists():
        return
    # end if
    if git(path.parent, "rev-parse", "--show-toplevel").returncode != 0:
        raise ValueError(f"[{project.name}] {path} is not in a git repository, a reset could not be undone")
    # end if
    if git(path.parent, "check-ignore", "-q", "--", str(path)).returncode == 0:
        raise ValueError(f"[{project.name}] {path} is ignored by git, a reset could not be undone")
    # end if
    if git(path.parent, "status", "--porcelain", "--", str(path)).stdout.strip():
        raise ValueError(f"[{project.name}] {path} has uncommitted changes, commit or stash them before resetting it")
    # end if
# end def


def upgrade_stage(text: str, project: Project, calendar_id: int) -> tuple[str, list[str]]:
    """Stage of `sync`: markdown todo files with the old bare header get the template (see `upgrade_old_template`)."""
    if not project.todo_file.endswith(".md"):
        return text, []
    # end if
    new = upgrade_old_template(text, new_todo_file_text(project, calendar_id))
    return new, ["upgraded the old header to the template"] if new != text else []
# end def


def select_projects(config: Config, only: str | None) -> list[Project]:
    """All projects, or the one whose name or one of whose tags is `only` (ignoring case)."""
    if not only:
        return list(config.projects)
    # end if
    found = [p for p in config.projects if only.casefold() in {p.name.casefold(), *(t.casefold() for t in p.tags)}]
    if not found:
        raise ValueError(f"no project {only!r} (known: {', '.join(p.name for p in config.projects)})")
    # end if
    return found
# end def


def sync(
    config: Config,
    todos: list[dict[str, Any]],
    only: str | None,
    dry_run: bool,
    use_git: bool = True,
    purge_missing_: bool = False,
    purge_complete_: bool = False,
    include_completed: bool = False,
    reset_todo_file: bool = False,
    add_files: bool = False,
) -> int:
    """Sync, then (optionally) purge missing, then purge completed: each stage is written and
    committed on its own, so the history shows what was a sync and what was a cleanup."""
    if reset_todo_file and not only:
        raise ValueError("--reset-todo-file needs --project: it rebuilds one file")
    # end if
    if reset_todo_file and not use_git:
        raise ValueError("--reset-todo-file needs git (the commit is the only way back), drop --no-git")
    # end if
    assigned = assign(todos, config.projects)  # all projects take part, so a tag never falls through to another one
    all_uids = {t["uid"] for t in todos}
    done_uids = {t["uid"] for t in todos if t.get("status") == "COMPLETED"}
    stages: list[tuple[str, Any]] = []
    if reset_todo_file:
        stages.append(("reset todo file", lambda text, project: reset_stage(text, project, config.calendar_id)))
    # end if
    if TEMPLATE_PATH.exists():
        stages.append(("upgraded todo file header", lambda text, project: upgrade_stage(text, project, config.calendar_id)))
    # end if
    stages += [
        ("synced todos", lambda text, project: merge(text, assigned[project.name], project, include_completed)),
    ]
    if purge_missing_:
        stages.append(("purged missing todos", lambda text, project: purge_missing(text, all_uids)))
    # end if
    if purge_complete_:
        stages.append(("purged completed todos", lambda text, project: purge_complete(text, done_uids)))
    # end if

    projects = select_projects(config, only)
    for p in projects:
        if p.path is None:
            print(f"[{p.name}] skipped, no path in {LOCAL_CONFIG.name} ({len(assigned[p.name])} todos not written)", file=sys.stderr)
        # end if
    # end for
    projects = [p for p in projects if p.path is not None and todo_dir_usable(p)]
    if reset_todo_file and not dry_run:
        for project in projects:
            assert_resettable(project)
        # end for
    # end if
    originals = {
        p.name: p.file().read_text(encoding="utf-8") if p.file().exists() else new_todo_file_text(p, config.calendar_id) for p in projects
    }
    current = dict(originals)
    changed: set[str] = set()
    for action, stage in stages:
        written: list[tuple[Project, Path]] = []
        details: dict[str, list[str]] = {}
        LINKED.clear()
        for project in projects:
            new, report = stage(current[project.name], project)
            for line in report:
                print(f"[{project.name}] {line}")
            # end for
            if new == current[project.name]:
                if action == "synced todos":
                    print(f"[{project.name}] up to date ({len(assigned[project.name])} todos)")
                # end if
                continue
            # end if
            details[project.name] = describe_changes(current[project.name], new)
            current[project.name] = new
            changed.add(project.name)
            if not dry_run:
                project.file().parent.mkdir(parents=True, exist_ok=True)
                write_atomic(project.file(), new)
                written.append((project, project.file()))
                print(f"[{project.name}] wrote {project.file()} ({action})")
            # end if
        # end for
        if use_git and written:
            commit_written(written, config.commit_prefix, action, details)
        # end if
        if add_files and use_git and not dry_run and action == "synced todos":
            for project in projects:
                commit_mentions(project)
            # end for
        # end if
    # end for
    if dry_run:
        for project in projects:
            sys.stdout.writelines(difflib.unified_diff(
                originals[project.name].splitlines(True), current[project.name].splitlines(True),
                str(project.file()), str(project.file()),
            ))
        # end for
    # end if
    return len(changed)
# end def


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="tracked tag to project mapping")
    ap.add_argument("--local-config", type=Path, default=LOCAL_CONFIG, help="machine-local project paths (gitignored)")
    ap.add_argument("--project", help="only this project (its name or one of its tags)")
    ap.add_argument("--dry-run", action="store_true", help="print a diff, write nothing")
    ap.add_argument("-v", "--verbose", action="store_true", help="log every comparison (assignment, line diffs, purge decisions)")
    ap.add_argument("--no-git", action="store_true", help="do not commit the written files")
    ap.add_argument("--purge-missing", action="store_true", help="drop managed lines whose todo no longer exists on CalDAV (own commit)")
    ap.add_argument("--purge-complete", "--purge-completed", action="store_true", help="drop todos that are completed on CalDAV (own commit); a parent stays while a child is open")
    ap.add_argument("--include-completed", "--include-complete", action="store_true", help="also add completed todos that are not in the file yet (ignored by default)")
    ap.add_argument("--reset-todo-file", action="store_true", help="rebuild the todo file of --project from the template plus its todo lines (checkbox lines and their `>` rows), everything else is dropped; refuses while the file has uncommitted changes; own commit, then the normal sync")
    ap.add_argument("--add-files", "--add", action="store_true", help="also stage and commit the files the todos mention (those with changes, each on its own); without it they are only linked")
    ap.add_argument("--write-schema", action="store_true", help=f"write {SCHEMA_PATH.name} and {LOCAL_SCHEMA_PATH.name} and exit")
    return ap
# end def


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    global VERBOSE
    VERBOSE = args.verbose

    for schema_path, text in ((SCHEMA_PATH, schema_text()), (LOCAL_SCHEMA_PATH, local_schema_text())):
        if args.write_schema or not schema_path.exists() or schema_path.read_text() != text:
            schema_path.write_text(text)
            if args.write_schema:
                print(f"wrote {schema_path}")
            # end if
        # end if
    # end for
    if args.write_schema:
        return 0
    # end if

    try:
        config = load_config(args.config, args.local_config)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if config.env_file:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / config.env_file)
    # end if
    url, token = os.environ.get(config.url_env), os.environ.get(config.token_env)
    if not url or not token:
        print(f"{config.url_env} / {config.token_env} not set (looked in env and {config.env_file})", file=sys.stderr)
        return 2
    # end if
    todos = asyncio.run(fetch_todos(url, token, config.calendar_id))
    try:
        sync(config, todos, args.project, args.dry_run, not args.no_git, args.purge_missing, args.purge_complete, args.include_completed, args.reset_todo_file, args.add_files)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    return 0
# end def


if __name__ == "__main__":
    sys.exit(main())
# end if
