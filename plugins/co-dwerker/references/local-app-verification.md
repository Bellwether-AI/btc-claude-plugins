# Local App Verification Reference

This document specifies how `/co-dwerker:work` Phase 3 Step 5a (Local App Verification) validates the implemented branch by booting the application locally after unit tests pass, diffing the result against the Step 1b baseline, and gating progress to Step 6 (Changelog) on a clean — or explicitly user-acknowledged — outcome. It is invoked from the brief Step 5a stub in `commands/work.md`. The pre-implementation counterpart is `references/baseline-localapp.md`.

## Purpose

Catch configuration errors, missing wiring, runtime regressions, and warning churn that unit tests don't surface. The agentic testing phase is the last fully-local checkpoint before opening a PR — the agent should exhaust every available means of validating its own work here, not bail early. Non-destructive only: use local mocks and dev configs; do not call production services, mutate external state, or send anything that would be observable outside the developer's machine.

Run in the worktree directory after Step 5 (verification-before-completion) reports clean. The branch under test is the implemented branch, not the unmodified baseline branch.

## Detection

Reuse the detection cascade from `references/baseline-localapp.md` ("Detection" section). Same order, same precedence rules, same `CLAUDE.md` override. If Step 1b detected one or more apps and wrote `.co-dwerker.baseline-localapp.json`, the post-impl run should validate the **same** set of apps so the diff is well-defined.

If `.co-dwerker.json` contains a `local_app_command` value, that command takes precedence over framework detection (the user provided it explicitly in a prior session). If `.co-dwerker.json` contains `local_app_skip: true`, treat the repo as no-runnable-app and proceed to "What 'complete' means" below.

If detection returns nothing AND no cached config exists, see "No-app-detected handling" below — do **not** silently skip.

## Pre-flight: auto-remediation before escalating

Before declaring a blocker that needs the user, attempt the remediations below in order. Every remediation must be read-only / locally-reversible — no destructive system actions. Track each attempt in the run report so the user sees what was tried when the gate eventually surfaces.

### Port conflict

When `lsof -i :<port>` (or platform equivalent) shows the port occupied:

1. Read `$STATE_FILE.last_session.local_app_pids` (a `number[]` of PIDs spawned by co-dwerker during Step 1b and earlier Step 5a attempts in this session). If the port-holder's PID matches one of those — i.e. it's our own stale process — `kill -TERM <pid>`, wait 3 seconds, retry the port check.
2. If the port-holder is **not** in our PID list, inspect the holder with `ps -p <pid> -o comm=,user=`. If it is a typical local-dev process owned by the current user (`func`, `dotnet`, `uvicorn`, `gunicorn`, `flask`, `node`, `python`) and there is no obvious reason to keep it alive (e.g., it has been running since before the co-dwerker session started — check process start time vs the `.co-dwerker.state.json` session start), record the fact and **escalate** rather than killing. Don't kill processes the user might want.
3. If the port is still occupied after one TERM attempt on our own PID, **escalate**. Do not loop.

### Missing environment variables / secrets

When the app's startup fails with a missing-variable error, or when pre-flight inspection of `.env.example` / `local.settings.json.example` shows variables not present in the current environment:

1. For each missing variable, check in order: (a) is it already in the current shell env (`printenv <name>`)? (b) is there a non-template companion file on disk (`.env.local`, `local.settings.json` next to `.example`) that the run command isn't loading? If so, source it.
2. For variables still missing, check the template values: if the template literally has `"changeme"`, `""`, `null`, or a documented framework default that is known safe for local boot (e.g., Azure Functions `AzureWebJobsStorage` set to `"UseDevelopmentStorage=true"`), copy the template value into a local-only file (e.g., `.env` or `local.settings.json`) and mark it as auto-sourced. **Never** invent a value for a variable whose name suggests a real credential (`*_SECRET`, `*_KEY`, `*_TOKEN`, `*_PASSWORD`, `*_CONNECTION_STRING` with a non-default literal) — escalate instead.
3. Record exactly which variables were auto-sourced and from where. If any variable remains unset after the above, **escalate** with the list of missing variables.

### Missing tool

When `which <tool>` returns nothing for a required runtime (`func`, `dotnet`, `node`, `python`, `docker`):

1. Do **not** attempt to install. The agent should not be modifying the user's system toolchain.
2. **Escalate immediately** with: the missing tool name, the documented install command from the project's `CLAUDE.md` if one exists, and a one-line note that the agent will not auto-install.

### Stale boot artifacts

Some frameworks leave files behind that prevent a fresh boot (`.next/cache` corruption, partial `obj/` directory from a prior `dotnet build`, an orphaned `pid` file). If the framework documents a clean-rebuild command (e.g., `dotnet clean`, `rm -rf .next`, `npm run clean`) and the boot attempt failed with an error matching a known stale-artifact pattern, run the documented clean command once and retry the boot. If the second boot also fails, **escalate**.

### After remediation

If a remediation succeeded, log it to the run report and continue with the boot attempt. If a remediation failed or didn't apply, fall through to "Gate on blockers" below.

## Boot, idle watch, log capture

Mirror `references/baseline-localapp.md` exactly: same 60-second boot timeout, **90-second idle watch** (not 30s — the agentic phase tolerates wall-clock time, and consistency with the baseline matters for diff accuracy), same ready-signal scan, same HTTP probe fallback, same log capture patterns (error/warning regexes, Python tracebacks, .NET exception blocks), same normalization pipeline before diff.

Track every PID the agent spawns in this step and append to `$STATE_FILE.last_session.local_app_pids` so the next remediation pass can recognize stale processes from earlier attempts.

After the 90-second window, shut the process down cleanly (SIGTERM, then SIGKILL after 10s) before moving to the diff stage. Do not leave a process running into Step 6.

## Gate on blockers

When auto-remediation can't resolve and the boot cannot proceed, **never silently skip**. Present `AskUserQuestion` with this template (substitute the specific blocker into the question text):

> "Local app verification can't proceed without your help.
>
> **Blocker:** {one-line description — e.g. "port 7071 is held by an external process (PID 12345, `func` started 2 hours before this session); refusing to kill"}
>
> **What I already tried:** {comma-separated list of remediation attempts and their outcomes, or "no auto-remediation applies for this blocker"}
>
> How do you want to proceed?
>
> 1. **I'll fix it — pause and let me retry** — pause while you set the variable / free the port / install the tool. When you tell me you're ready, re-run Step 5a from the top.
> 2. **Skip with a documented reason** — give me a one-line reason. I'll record it in the run report, write it to `.co-dwerker.state.json` under `last_session.local_app_skip_reason`, and include it in the PR description's test plan so reviewers see what was skipped and why.
> 3. **Cancel this session** — exit `/co-dwerker:work` cleanly so you can address the blocker outside the workflow."

On choice 1, wait for the user's "ready" signal, then re-run Step 5a from the top (including detection + pre-flight + boot).

On choice 2, prompt for the one-line reason via `AskUserQuestion` (or accept it inline if the user already supplied one in their response). Write the reason to `$STATE_FILE.last_session.local_app_skip_reason`. The downstream Step 7 (Create PR) must include this reason in the PR body's Test Plan section.

On choice 3, exit `/co-dwerker:work` cleanly. Do not advance to Step 6.

## No-app-detected handling

When the detection cascade returns no runnable app and `.co-dwerker.json` doesn't have `local_app_command` or `local_app_skip` set:

1. Read `.co-dwerker.json` if it exists. Honor `local_app_command` (use it verbatim) or `local_app_skip: true` (treat as complete; report "Step 5a skipped — repo has no runnable app per `.co-dwerker.json`" and continue to Step 6).
2. If neither is set, present `AskUserQuestion`:

   > "I didn't detect a runnable application in this repo (no `host.json`, `Program.cs`, `app.py`, `manage.py`, `package.json` with a `start` script, or `docker-compose.yml`, and no `CLAUDE.md` override).
   >
   > 1. **No runnable app** — this is a library/CLI/tooling repo. Skip Step 5a permanently for this repo (writes `local_app_skip: true` to `.co-dwerker.json`).
   > 2. **Provide a custom run command** — e.g. `make dev`, `./scripts/serve.sh`, `docker compose -f docker-compose.dev.yml up`. I'll use it now and cache it for future sessions (writes `local_app_command` to `.co-dwerker.json`).
   > 3. **Provide a command just for this session** — use a command once without caching."

3. Persist the choice:
   - Option 1: write `"local_app_skip": true` to `.co-dwerker.json` and proceed to "What 'complete' means" below.
   - Option 2: write `"local_app_command": "<the command>"` to `.co-dwerker.json`. Re-run detection treating the command as a `CLAUDE.md`-style override.
   - Option 3: use the command in-memory only; do not modify `.co-dwerker.json`. Re-run detection treating it as a one-shot override.

## Diff against baseline

If `.co-dwerker.baseline-localapp.json` exists in the working directory (written by Step 1b), read it and diff the current run against it. If the baseline file is absent or has `boot_status: "skipped"` for an app, treat all current errors and warnings for that app as "no baseline available" — report them but do not block. If the baseline file is absent because the repo has no runnable app (`local_app_skip: true`), there is nothing to diff.

### Boot-status comparison

Use the same equivalence classes as `references/baseline-localapp.md` Step 5a section: `started` and `started_no_signal` are "healthy boot"; `failed_to_start`, `timeout`, `crashed_during_idle`, and `preflight_failed` are "boot failure".

| Baseline | Current | Outcome |
|----------|---------|---------|
| healthy | healthy | proceed to log-entry diff |
| healthy | boot failure | **REGRESSION — block.** Report the current `boot_status` and the first 3 error entries. Force fix and re-run Step 5a. |
| boot failure | healthy | positive side effect — report enthusiastically |
| boot failure | boot failure | report both statuses; do not block. If the specific failure mode differs (e.g., baseline `timeout` → current `crashed_during_idle`), flag for user attention but still do not block. |
| `skipped` (user opted out at Step 1b gate) | any | no baseline comparison; report current state without baseline framing; treat all errors as potentially new but do not auto-block — instead apply the "New warnings" rule below to all current warnings, and surface all current errors with the same per-entry user prompt that "New warnings" uses |

### Log-entry diff

Apply separately to each app's `log_errors[]` and `log_warnings[]`, matching on the `normalized` field within the same app `name`. Before the diff, filter out any warning whose `normalized` form is in `.co-dwerker.json`'s `dismissed_warnings` array — treat them as if they were pre-existing in the baseline.

| Class | Definition | Treatment |
|-------|------------|-----------|
| Pre-existing errors | error entries in both baseline and current | informational, do not block |
| New errors | error entries in current `log_errors[]` only | **BLOCK.** Force fix, then re-run Step 5a from the top. |
| Resolved errors | error entries in baseline only | positive side effect, report under "Resolved" |
| Pre-existing warnings | warning entries in both | informational, do not block |
| New warnings | warning entries in current `log_warnings[]` only | **BLOCK by default, with per-warning dismissal** — see below |
| Resolved warnings | warning entries in baseline only | positive side effect |

### Per-warning dismissal flow (new warnings only)

Group new warnings by their `normalized` form (so identical lines that repeated N times surface as one prompt with an `× N` count). For each unique new warning, present `AskUserQuestion`:

> "New warning detected after implementation:
>
> ```
> {raw line, truncated to 500 chars if longer}
> ```
>
> {if multiline, append: "(multi-line entry, {K} lines)"}
>
> {if × N: append "Appeared {N} times during the 90s idle window."}
>
> 1. **Treat as regression** — block and fix this warning before continuing. Re-run Step 5a after the fix.
> 2. **Dismiss for this PR only** — give me a one-line reason; I'll record it in the run report and include it in the PR test plan. The warning stays unfiltered in future sessions.
> 3. **Dismiss permanently for this repo** — appends the normalized form to `.co-dwerker.json`'s `dismissed_warnings: []` array. Future baseline+verification diffs treat it as if it were always present."

On choice 1, this app's verification is incomplete — collect all "regression" warnings across the prompt sequence, then exit the loop, fix them, and re-run Step 5a from the top.

On choice 2, capture the reason for this warning and continue to the next.

On choice 3, append the `normalized` value to `dismissed_warnings` in `.co-dwerker.json` immediately (before the next prompt) so a re-run of the same step within the same session no longer asks. Continue to the next warning.

After all new warnings have been resolved (regressed-and-fixed, dismissed-this-PR, or dismissed-permanently), the warning diff is considered complete.

## What "complete" means

Step 5a is complete only when one of these is true:

- **Clean pass** — every detected app booted to a "healthy boot" status, the 90-second idle watch ran to completion, no new errors appeared, and every new warning was either dismissed for this PR or dismissed permanently.
- **User-acknowledged skip** — the user chose "Skip with a documented reason" at the blocker gate, the reason is recorded in `$STATE_FILE.last_session.local_app_skip_reason`, and the PR description test plan includes the reason.
- **No-runnable-app** — `.co-dwerker.json` has `local_app_skip: true`, or the user just selected option 1 at the no-app-detected gate.

If none of these is true, Step 5a is **not complete** and the agent must not advance to Step 6 (Changelog). The Step Tracking GATE enforcement in `commands/work.md` applies: the Step 5a task in the TaskList stays `in_progress` until one of the completion conditions is met.

## Schema additions

### `.co-dwerker.json` (repo-local config)

```json
{
  "docs_repo": "<org/repo or null>",
  "docs_path": "<path within docs repo or null>",
  "local_app_command": "<custom run command string, or absent>",
  "local_app_skip": false,
  "dismissed_warnings": [
    "<normalized warning line>",
    "<another normalized warning line>"
  ]
}
```

Field notes:

- `local_app_command` — present only when the user selected "Provide a custom run command" at the no-app-detected gate. Used in place of framework detection on subsequent sessions.
- `local_app_skip` — `true` only when the user selected "No runnable app" at the no-app-detected gate. Step 5a (and Step 1b) skip cleanly when this is set.
- `dismissed_warnings` — array of normalized warning strings the user permanently dismissed. The baseline-localapp normalization pipeline treats anything in this list as if it were in the baseline.

### `.co-dwerker.state.json` `last_session` additions

```json
{
  "last_session": {
    "...existing fields...",
    "local_app_pids": [12345, 12346],
    "local_app_skip_reason": "Azure Functions can't boot without prod storage connection string; reviewer will run locally"
  }
}
```

Field notes:

- `local_app_pids` — PIDs spawned during Step 1b and Step 5a in the current session, used by the auto-remediation port-conflict logic to recognize stale processes the agent itself owns.
- `local_app_skip_reason` — the one-line user reason captured at the blocker-gate "Skip with documented reason" option. `null` (or absent) when no skip happened. The PR creation step in Phase 3 Step 7 reads this and embeds it in the PR body.

## PR description integration

When Step 5a completes with a user-acknowledged skip, Step 7 (Create PR) must include a line in the PR body's Test Plan section:

```
- [ ] Local app verification: SKIPPED — <reason from local_app_skip_reason>
```

When Step 5a completes with one or more dismiss-for-this-PR warnings, Step 7 must include:

```
- [ ] Local app verification: PASS with dismissed warnings:
  - "<raw warning>" — dismissed: <reason>
  - "<raw warning>" — dismissed: <reason>
```

When Step 5a completes clean, the existing "All existing tests pass" checklist line is sufficient — no extra annotation needed.

## Time cap

Same 15-minute cumulative cap as `references/baseline-localapp.md`, scoped separately to this run. The cap covers boot + idle watch + probe time across all detected apps in the post-implementation run, but does not include the time the user spends at any `AskUserQuestion` gate.

If the cap is reached mid-boot or mid-idle, terminate the process, record what was captured with `boot_status: "timeout"`, and trigger the blocker gate with "verification time cap reached" as the blocker description. The user can then choose to retry (perhaps with more time available), document a skip, or cancel.

## Edge cases

| Case | Behavior |
|------|----------|
| Baseline file exists but is for a different commit / branch | Diff still proceeds; the `commit` field in the baseline is informational. Most repos will see no issue. If the user is on a branch that diverged significantly from the baseline branch, surface this as a soft note ("baseline was captured on commit X; current commit is Y") but do not block. |
| Multiple apps in the repo (monorepo) | Verify each app independently with its own diff. Aggregate the outcomes — if ANY app has an unresolved new error or undismissed new warning, Step 5a is not complete. |
| User selects "dismiss permanently for this repo" but the same warning was already in baseline | Idempotent: appending to `dismissed_warnings` when the value is already present is a no-op. |
| User selects option 1 (fix and retry) at the blocker gate but doesn't actually fix anything before saying "ready" | Re-run detects the same blocker; gate fires again. No infinite loop because each pass is gated by the user's explicit "ready" signal. |
| Auto-remediation succeeded but the boot still fails for a different reason | Treat as a new blocker; run remediation again on the new error class, then escalate if it can't be remediated. |
| Baseline had `boot_status: "skipped"` and current run also has a blocker | Cannot diff; surface the current blocker via the standard gate. The user already knows there is no baseline. |
| `.co-dwerker.json` has both `local_app_command` and `local_app_skip: true` | Honor `local_app_skip` (skip wins). Surface a soft warning to the user that the config is contradictory. |
| User dismissed a warning permanently in a prior session but the warning is no longer appearing | The entry stays in `dismissed_warnings` — it's a no-op cost. No automatic cleanup. |

## What to do after the step completes

Return control to `commands/work.md` Step 5a, which surfaces the appropriate summary to the user (templates defined there) and continues to Step 6 (Changelog).
