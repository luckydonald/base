# Plan: cut the git-split e2e test time

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

Follow-up to todo `2eaeb8ce-67be-4878-a8df-3fb3311a4be8`, requested by the user as its own commit with its own history.

## Context

The full suite from `scripts/°base/tests` ran for over 25 minutes.
Nearly all of it is the two e2e modules, `test_git_split_e2e_smoke_matrix.py` and `test_git_split_e2e_deep_flow.py`, which call `get-base.py` as a subprocess (`run_fake_curl` in `_git_split_e2e_fixtures.py`) against a temp repo.
They were previously hidden on Python 3.12 because they crashed early on `full_match` (fixed in `15fa8c80d`), so they now run in full.

## Measurements (Python 3.14, `scratchpad/timing.py` and `scratchpad/prof.py`)

- One deep-flow variant takes 38s: about 8s of fixture setup and 6 `get-base` calls (9s for the first, about 3s for each of the other 5, per `--base-ref`).
- The first call spawns 283 `git` processes for only 10 split commits, about 30ms each. No single function dominates, and a bare `git rev-parse` costs 20ms with or without the global config, so there is no cheap configuration win.
- Deep flow is 6 variants × 2 base refs, all sequential. The smoke matrix is 54 combinations in one test method, also sequential, and each combination is a fixture build plus a first-call `get-base` (about 13s), so roughly 12 minutes.
- The machine has 10 cores and the work is subprocess-bound, so parallelism pays off. `pytest`/xdist is not installed and the suite is plain `unittest`.

## Changes

1. **Skip the redundant `HEAD` pass in `test_git_split_e2e_deep_flow.py`.** `BASE_REFS = ("base", "HEAD")` fetches the same commit twice whenever the checked-out commit is the `base` branch tip, as it is here. Resolve both refs once in `setUpClass` with `fixtures.resolve_this_repo_root()` and `git rev-parse`, and keep only `"base"` when they are equal. Coverage is unchanged, because the second pass tested the identical commit. It still runs on a feature branch where the two differ.
2. **Run independent scenarios in a thread pool.**
   - In `test_git_split_e2e_smoke_matrix.py`, move the body of the inner loop into a `run_combination(repo_name, repo_builder, branch_name, branch_applier)` function that returns the `CompletedProcess` and the merge-state check result without asserting.
   - Submit all 54 combinations to a `concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count()))`, then assert each result in the main thread inside `self.subTest(repo=..., branch=...)`, so failure reporting stays per combination.
   - In `test_git_split_e2e_deep_flow.py`, pass the repo root into `_run_deep_flow` and its `_assert_*` helpers instead of using `self.repo_root`, so the base refs of one variant can run concurrently when they do differ.
   - Threads are safe here: each combination uses its own `tempfile` directory, the helpers only spawn subprocesses, and `classify.ai_ignore_path()` only reads the cwd.
3. **Add a worker-count override** through one module-level constant `E2E_WORKERS` in `_git_split_e2e_fixtures.py`, read from the env var `E2E_WORKERS` (default `min(8, os.cpu_count())`, `1` for serial debugging).

Out of scope: batching the per-commit `git` calls inside `°split_lib` and sharing a prebuilt fixture repo between combinations. Both are larger refactors with correctness risk, and can be separate todos if the new times are still too long.

## Verification

- Time before and after with the same invocation on 3.14 from the repo root: `uv run python -m unittest scripts.°base.tests.test_git_split_e2e_smoke_matrix scripts.°base.tests.test_git_split_e2e_deep_flow`. Target is under 5 minutes in total, from roughly 25.
- Run once with `E2E_WORKERS=1` to confirm the serial path still passes.
- Break a fixture on purpose (for example make `get-base.py` exit 1) to confirm failures are still reported per `subTest` with STDOUT/STDERR.
- Run the full suite from the repo root with the 3.14 venv and then the new tests on 3.12.2.
