---
name: "uvicorn-app-logging"
description: "Wire up (or fix) application logging for a FastAPI + `uvicorn.run()` app. Use this whenever a user reports their own `logger.info`/`logger.warning`/`logger.debug` calls aren't showing up in the output while uvicorn's own request logs still print fine, asks to 'fix logging', 'add logging setup', wants colored/consistent log output, or says things like 'logs not showing', 'logging isn't working', 'my logger never prints', 'why don't I see my log lines'."
---

# FastAPI/uvicorn app logging

## The symptom

`uvicorn.run(...)` is called with **no** `log_config=`. uvicorn's default log
config sets `disable_existing_loggers: True`, which silently detaches every
handler on every logger that existed *before* `uvicorn.run()` was called --
including any handler set up earlier in the same entrypoint (e.g. via
`luckydonaldUtils.logger.add_colored_handler(...)` or a manual
`logging.basicConfig()`), and every module-level
`logger = logging.getLogger(__name__)` in the app.

Net effect: `logger.info("...")` calls throughout the app go nowhere. Only
uvicorn's own `uvicorn.access`/`uvicorn.error` lines print. This is easy to
miss because the app still starts and runs fine -- there's no error, the logs
just aren't there. It's also **not** a per-call problem (adding more
`logger.info` calls or checking log *levels* won't fix it) -- it's the
`uvicorn.run()` invocation itself.

Diagnose by grepping the entry point:

```bash
grep -rn "uvicorn.run" --include="*.py" .
```

If the call has no `log_config=` kwarg, that's the bug.

## The fix

This skill ships a canonical two-file solution -- reuse it verbatim rather
than inventing a new logging setup:

- `<package>/fully_qualified_name.py` -- one helper, `fqn(obj)`, used to
  reference formatter/handler classes by dotted path inside the `dictConfig`
  dict (required because `dictConfig` takes strings, not class objects).
- `<package>/logs.py` -- `get_uvicorn_log_config(*, disable_existing_loggers=False, project=None)`,
  building a `dictConfig`-shaped dict that keeps `uvicorn`/`uvicorn.error`/
  `uvicorn.access`/`uvicorn.asgi.trace` loggers working *and* leaves the root
  logger (and therefore every `logging.getLogger(__name__)` in the app)
  attached to a colored stdout handler.

Copy both files from `references/fully_qualified_name.py` and
`references/logs.py` in this skill directory into the target app's package
directory verbatim -- no per-project edit is needed, `logs.py`'s
`from .fully_qualified_name import fqn` stays a relative import as long as
both files land in the same package.

The templates use `luckydonaldUtils.logger`'s `ColoredFormatter` /
`ColoredStreamHandler` for colored output. If the target project doesn't
already depend on `luckydonaldUtils`, either add it or swap those two
imports for a different colored-logging library, keeping the rest of the
`dictConfig` shape (formatters/handlers/loggers/root) unchanged -- that shape
is what actually fixes the bug, the coloring is cosmetic.

Then wire it into the entrypoint's `uvicorn.run()` call:

```python
from <package>.logs import get_uvicorn_log_config

uvicorn.run(
    app=f"{app_module_path}:app",
    host="0.0.0.0",
    port=int(environ.get("INTERNAL_PORT", "80")),
    reload=False,
    workers=1,
    root_path="",
    proxy_headers=False,
    # Keep existing loggers enabled so app loggers work
    log_config=get_uvicorn_log_config(disable_existing_loggers=False),
    log_level="info",
    use_colors=True,
)
```

The `# Keep existing loggers enabled so app loggers work` comment is load-bearing
context, not decoration -- keep it, it's the one-line answer to "why does this
project pass `log_config=` at all."

## Don't

- Don't reach for `logging.basicConfig()` or manually re-attach handlers
  after `uvicorn.run()` starts -- by the time the app code runs inside
  uvicorn's worker, the damage from `disable_existing_loggers: True` is
  already done for anything configured at import time in the entrypoint.
- Don't write a bespoke `dictConfig` per project. If `logs.py` needs a new
  logger silenced/promoted, extend the shared shape (e.g. via the optional
  `project=` kwarg, which pins one named logger to `DEBUG` + the colored
  handler) rather than forking the whole config.
- This applies only to apps that actually call `uvicorn.run()` themselves.
  Apps served by a different WSGI/ASGI server (gunicorn, hypercorn, an
  externally-managed uvicorn invocation with its own `--log-config`) don't
  hit this failure mode the same way -- check how the process is actually
  started before assuming this skill applies.
