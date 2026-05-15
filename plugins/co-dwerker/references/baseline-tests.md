# Baseline Tests Reference

This document specifies how `/co-dwerker:work` Phase 3 Step 1 (Baseline Tests) captures the repo's pre-existing test state before any code changes. It is invoked from the brief Step 1 stub in `commands/work.md`. The downstream diff treatment is in `commands/work.md` Step 5 Verify, which reads the file produced here.

## Purpose

Capture which tests and linters are currently failing on the unmodified target branch so that post-implementation verification can distinguish regressions (caused by this work) from pre-existing failures (already broken, not this PR's problem). This is informational only — failures do not block the workflow.

Run in the current working directory before the worktree is created in Phase 3 Step 3. The CWD reflects the target branch state with no co-dwerker edits.

## Detect available test and lint commands

In this order, stopping when something is found:

1. **Project `CLAUDE.md`** — read the repo's `CLAUDE.md` (and any nested `CLAUDE.md` files for monorepos) for explicit test/lint commands. Examples to look for: `uv run pytest`, `pytest`, `npm test`, `dotnet test`, `Invoke-Pester`, `go test ./...`, `uv run ruff check .`, `uv run black --check .`.
2. **Manifest files** — if `CLAUDE.md` is silent, infer from manifests:
   - `pyproject.toml` / `setup.cfg` / `tox.ini` → `uv run pytest` (or `pytest` if `uv` is not installed)
   - `package.json` with a `scripts.test` → `npm test` (or `yarn test` / `pnpm test` based on lockfile)
   - `*.csproj` / `*.sln` → `dotnet test`
   - `*.Tests.ps1` → `Invoke-Pester`
   - `go.mod` → `go test ./...`
3. **Nothing detected** — do **not** write `.co-dwerker.baseline-tests.json`. Tell the user with the "skip" summary template in `commands/work.md` Step 1 and return control to work.md to continue to Step 1b. Downstream Step 5 treats a missing baseline file as "no baseline available".

## Run each detected suite

Run all detected suites independently. One suite failing does **not** block subsequent suites. Capture for each: command, exit code, totals (passed/failed/errors/skipped), duration in seconds, and a list of failing test identifiers (truncate to the first 50 per suite; set `failing_tests_truncated: true` when truncation occurs).

Cap **cumulative** wall-clock time across all suites combined at 10 minutes (suite execution only; detection and parse time are not counted). If a single suite is still running when the cap is reached, terminate it, record its `status: "timeout"` with `null` totals (or whatever partial totals were captured), then mark any remaining undetected suites `status: "timeout"` with `null` totals and continue. Per-suite timeouts are not enforced — only the cumulative cap.

If a command's tooling is missing (e.g., `pytest: command not found`), record `status: "tooling_missing"` for that suite and continue.

## Write the baseline file

Before writing, add the file to the repo's local git exclude so intermediate `superpowers:executing-plans` commits do not accidentally include it:

```bash
grep -qxF '.co-dwerker.baseline-tests.json' .git/info/exclude 2>/dev/null \
  || echo '.co-dwerker.baseline-tests.json' >> .git/info/exclude
```

(This only affects the local clone; the repo's `.gitignore` is not modified.)

Write `.co-dwerker.baseline-tests.json` to the repo root:

```json
{
  "captured_at": "<ISO 8601 UTC>",
  "branch": "<current branch>",
  "commit": "<git rev-parse HEAD>",
  "issue_number": <ACTIVE_ISSUE>,
  "suites": [
    {
      "name": "pytest",
      "kind": "test",
      "command": "uv run pytest",
      "status": "completed",
      "exit_code": 1,
      "duration_seconds": 47,
      "totals": { "passed": 142, "failed": 3, "errors": 0, "skipped": 5 },
      "failing_tests": ["tests/test_foo.py::test_bar"],
      "failing_tests_truncated": false
    },
    {
      "name": "ruff",
      "kind": "lint",
      "command": "uv run ruff check .",
      "status": "completed",
      "exit_code": 0,
      "duration_seconds": 2,
      "totals": null,
      "failing_tests": [],
      "failing_tests_truncated": false
    }
  ]
}
```

### Field notes

- `kind`: `"test"` or `"lint"`. Linters share the same `suites[]` array but their `totals` and `failing_tests` fields are typically `null` / `[]` — pass/fail is determined by `exit_code` alone (0 = clean, non-zero = issues found).
- `status` enum: `completed` (suite ran to completion), `skipped` (suite was detected but the agent chose not to run it — rare; not currently triggered by any rule in this skill, reserved for future use), `tooling_missing` (the command's binary was not found), `timeout` (cumulative 10-minute cap hit).
- `totals`: required for `status: "completed"` test suites; `null` for lint suites, `tooling_missing`, `timeout`, or any partial-data case.
- `failing_tests`: truncated to the first 50 entries per suite. When truncation occurred, set `failing_tests_truncated: true` so Step 5 Verify can warn the user that the baseline diff is best-effort rather than exhaustive.

## What to do after capture

Return control to `commands/work.md` Step 1, which will surface a summary to the user (using the templates defined there) and continue to Step 1b (Baseline Local App).
