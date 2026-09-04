# Local App: Baseline (Step 3.1b) and Verification (Step 3.5a)

Unit tests do not catch missing wiring, bad config, a dependency that fails at startup, or a
background timer that throws thirty seconds in. Booting the application locally does. co-dwerker
boots it twice per issue:

- **Step 3.1b, baseline**, on the unmodified branch before any code changes, so we know what was
  already broken.
- **Step 3.5a, verification**, on the implemented branch after tests pass, diffed against the
  baseline so only *new* problems block the PR.

Both runs use `localapp_capture.py`; the diff is `localapp_diff.py`. Script names below are
shorthand for `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py`, written out in full when you run
them (conventions §1). Because one script does both captures, the normalization that makes the
diff work is symmetric by construction, and your job is the judgment the script cannot make: what
command runs this app, whether a blocker is safe to fix yourself, and what a new warning means for
this PR.

Non-destructive only: local mocks and dev configs. Never point a local boot at production
services or mutate anything observable outside the developer's machine.

**Contents:** 1 Detection · 2 Running the capture · 3 Step 3.1b baseline · 4 Step 3.5a
verification (flow, pre-flight remediation, blocker gate, no-app gate, diff, warning decisions) ·
5 Completion · 6 PR description · 7 Reference (JSON fields, edge cases)

---

## 1. Detection

Decide what to run and how to describe it to the script. Check `.co-dwerker.json` first:

- `local_app_skip: true` → the repo has no runnable app. Step 3.1b: say so and continue. Step 3.5a:
  complete (see §5). Nothing else in this file applies.
- `local_app_command` set → use it verbatim with `--type custom`; skip framework detection.

Otherwise detect, most specific first. The repo's `CLAUDE.md` wins if it documents a local-run
command (use `--type custom`, or the matching type if it is obviously one of these).

| Signal | `--type` | Typical `--command` | Default port |
|--------|----------|---------------------|--------------|
| `host.json` (root or one level down) | `azure_functions` | `func start` | 7071 |
| `Program.cs` / `Startup.cs` / `*.csproj` | `dotnet` | `dotnet run` | parsed from output |
| `manage.py` | `python_django` | `python manage.py runserver` | 8000 |
| `pyproject.toml` with fastapi/uvicorn | `python_fastapi` | `uvicorn app:app` | 8000 |
| `app.py` / `wsgi.py` with flask | `python_flask` | `flask run` | 5000 (on macOS use `--port 5001` and `flask run --port 5001`; AirPlay holds 5000) |
| other Python entry point | `python_generic` | `python app.py` | parsed from output |
| `package.json` with `scripts.start` | `node` | `npm start` (or yarn/pnpm by lockfile) | 3000 |
| `docker-compose.yml` / `compose.yml` | `docker_compose` | `docker compose up` | per service |
| anything else you can justify | `custom` | whatever runs it | give `--port` |

- Monorepo with several apps: run the script once per app with a distinct `--name` and `--cwd`;
  the JSON accumulates one entry per name.
- `host.json` plus `package.json`: Azure Functions wins (more specific).
- The script knows each type's ready signal and default port. Pass `--port` when the app does not
  use the default, `--ready-pattern` when the framework prints something unusual, and `--probe`
  when there is a better health path than `/health`, `/healthz`, `/`.
- Nothing detected and no cached config: Step 3.1b writes nothing and moves on; Step 3.5a asks the
  user (§4.3). Neither step invents a command.

---

## 2. Running the capture

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/localapp_capture.py --mode baseline --name api --type azure_functions --command "func start" --issue $ISSUE_NUMBER
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/localapp_capture.py --mode verify   --name api --type azure_functions --command "func start" --issue $ISSUE_NUMBER
```

- Run it from the root of the branch under test (main checkout for baseline, worktree for
  verify). It waits internally, so give the Bash call a `timeout` of
  `(boot_timeout + idle_seconds + 90) * 1000` ms: **240000** with the defaults (60 s boot,
  90 s idle). Never wrap it in `sleep`.
- Useful flags: `--cwd sub/dir`, `--port N` (repeatable), `--env-file .env.local` and
  `--env KEY=VALUE` for the remediation in §4.1, `--required-config FILE`, `--boot-timeout`,
  `--idle-seconds`, `--write-skipped` (records `boot_status: "skipped"` without running),
  `--json` (machine-readable instead of the summary).
- Exit codes: **0** healthy (`started` / `started_no_signal` / `skipped`), **2** boot failure
  (`failed_to_start`, `timeout`, `crashed_during_idle`), **3** `preflight_failed`, **4** usage
  error. The last line is always `RESULT: <boot_status>`.
- The summary prints the `pid:` line, the first three errors and, on failure, the last output
  lines. The full log is `.co-dwerker.localapp-<name>-<mode>.log`; read it before deciding
  anything about a failure.
- Record the PID from the summary so a later run can recognise a stale process of ours:
  `checkpoint.py set --append local_app_pids=<pid>` (the script kills its own process group on
  exit, so this matters only if the script itself was killed).
- Time cap: 15 minutes per step across all apps in the repo. If you hit it, stop starting new
  apps, mark the rest as not run, and treat the situation as a boot failure for gating.

---

## 3. Step 3.1b: baseline

Run the capture in `--mode baseline` for each detected app.

**Healthy boot** (exit 0): tell the user in a sentence or two what booted, how long it took, and
how many errors and warnings were recorded as pre-existing. No gate. Continue to Step 3.2.

**No app detected** (nothing to run): say so and continue to Step 3.2. Step 3.5a will ask the
user what to do about it.

**Boot failure or preflight failure** (exit 2 or 3): this is the one place the baseline stops.
Pre-existing *test* failures are common and tolerable, but without a successful baseline boot
the Step 3.5a comparison has nothing to compare against, and continuing silently would defeat the
purpose of the step. Read the log, then ask with `AskUserQuestion`. Put the status, the reason
(failing preflight check, exit code, elapsed time), and the first few captured errors in the
question. Options:

1. **Fix the environment and retry (Recommended)** — the user frees the port, starts the
   dependency, or adds the config; when they say ready, re-run Step 3.1b from detection.
2. **Skip the baseline for this session** — run the capture again with `--write-skipped` so
   Step 3.5a knows there is no baseline, then continue to Step 3.2. Step 3.5a will still run,
   treating every error and warning as needing a decision rather than as a regression.
3. **Cancel this session** — exit `/co-dwerker:work` cleanly so they can fix things outside the
   workflow.

Then `checkpoint.py mark 3.1b completed --set baseline_localapp_file=.co-dwerker.baseline-localapp.json`
(or `--set baseline_localapp_file=null` when nothing ran).

---

## 4. Step 3.5a: verification

This is the last fully local checkpoint before a PR exists. It is a phase gate: Step 3.6 does not
start until one of the completion conditions in §5 is true. The point is not to make skipping
impossible; it is to make sure skipping is a decision the user takes on the record, with the
reason visible to the PR reviewer.

Run in the worktree after `superpowers:verification-before-completion` reports clean. Verify the
same set of apps Step 3.1b baselined so the diff is well defined.

**Flow:** detect (§1) → run the capture (§4.4) → on exit 2 or 3, apply the remediation in §4.1
once and re-run → still failing, blocker gate (§4.2) → nothing to run at all, no-app gate (§4.3) →
healthy, run the diff (§4.4) and work through any decisions (§4.5) → record completion (§5).

### 4.1 Pre-flight: fix what is safely fixable before asking

Every remediation here is local and reversible. Log what you tried; if you end up at the blocker
gate the user should see it.

- **Port in use.** `lsof -nP -iTCP:<port> -sTCP:LISTEN` shows the holder. If its PID is in
  `progress.context.local_app_pids`, it is a stale process of ours: `kill -TERM <pid>`, wait a
  few seconds, re-check once. If it is not ours, look at `ps -p <pid> -o comm=,user=,lstart=`.
  Anything the user might have started on purpose, especially a process older than this session,
  gets escalated, not killed.
- **Missing environment variables.** When startup fails on a missing variable, or a template
  (`.env.example`, `local.settings.json.example`) lists variables the environment lacks: first
  check whether the shell already has it (`printenv NAME`) or a non-template file next to the
  template (`.env.local`, `local.settings.json`) already defines it; pass that file with
  `--env-file`. For variables still missing, copy a template value only when it is obviously a
  safe local default (`"changeme"`, empty, `UseDevelopmentStorage=true`, a `localhost` URL).
  Never invent a value for anything whose name suggests a real credential (`*_SECRET`, `*_KEY`,
  `*_TOKEN`, `*_PASSWORD`, `*_CONNECTION_STRING` with a non-default literal); a made-up secret
  that happens to work locally hides a real deployment problem. Escalate with the list, and record
  every variable you sourced and from where.
- **Missing tool** (`func`, `dotnet`, `node`, `python`, `docker` not on PATH). Installing runtimes
  changes the user's machine in ways they did not ask for, so escalate instead, with the tool name
  and the install command from the repo's `CLAUDE.md` if it documents one.
- **Stale build artifacts.** If the boot error matches a known stale-artifact pattern and the
  framework documents a clean command (`dotnet clean`, `rm -rf .next`, `npm run clean`), run it
  once and retry. A second failure escalates.

### 4.2 Blocker gate

When remediation cannot get the app to boot, ask with `AskUserQuestion`. The question carries the
one-line blocker (for example "port 7071 is held by PID 12345, a `func` process started two hours
before this session; not killing it") and what you already tried. Options:

1. **I'll fix it, then retry (Recommended)** — pause; when the user says ready, re-run Step 3.5a
   from detection.
2. **Skip with a documented reason** — ask for a one-line reason (or take it from their reply),
   record it with `checkpoint.py set --set local_app_skip_reason="<reason>"`, and go to §5.
   Step 3.7 puts the reason in the PR test plan.
3. **Cancel this session** — exit `/co-dwerker:work` cleanly.

### 4.3 No app detected

If detection finds nothing and `.co-dwerker.json` has neither `local_app_command` nor
`local_app_skip`, ask once. List what you looked for. Options:

1. **No runnable app here** — library, CLI, or tooling repo. Merge `"local_app_skip": true` into
   `.co-dwerker.json`, commit that change on the feature branch (it is repo config and should ship
   with the PR), and go to §5. Steps 3.1b and 3.5a skip cleanly from now on.
2. **Use this command and remember it** — the user gives a command (`make dev`,
   `./scripts/serve.sh`, `docker compose -f compose.dev.yml up`). Merge it into `.co-dwerker.json`
   as `local_app_command`, commit on the feature branch, then run the capture with `--type custom`.
3. **Use a command just this once** — run it now with `--type custom`; do not write config.

### 4.4 Run and diff

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/localapp_capture.py --mode verify --name <app> --type <type> --command "<cmd>" --issue $ISSUE_NUMBER   # per app
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/localapp_diff.py diff
```

The diff reads `.co-dwerker.baseline-localapp.json`, `.co-dwerker.verify-localapp.json`,
`.co-dwerker.json` (permanent dismissals), and the main checkout's state file (per-PR dismissals,
§4.5). It prints a per-app report, writes `.co-dwerker.localapp-diff.json`, and exits:

| Exit | Meaning | What you do |
|------|---------|-------------|
| **0** | clean: boot ok, no new errors, no undecided warnings | Step 3.5a is complete (§5). |
| **2** | block: a healthy→failing boot regression, or new errors | Read the log, fix the cause, `checkpoint.py mark 3.5a in_progress`, re-run from detection. Pre-existing errors are listed for information only; never "fix" a baseline error to get a green diff unless it is the point of the issue. |
| **1** | decisions needed: new warnings, entries with no baseline, or an app the baseline had that this run did not verify | Work through §4.5, then re-run the diff. |
| **4** | usage error: the verify capture never produced its file | Go back to the capture; this is not a decision. |

A `fixed` boot outcome or `resolved` entries are good news; say so. `still_failing` with a
changed failure mode is worth a sentence to the user but does not block.

### 4.5 New-warning decisions

New warnings block by default because a warning nobody looked at is how regressions ship. But
many are noise, so each unique new warning (the report groups repeats and shows an `xN` count)
gets one `AskUserQuestion`. Show the raw line (and line count if multi-line) and the
`normalized:` text from the report, so the user sees exactly what a dismissal would match.
Options:

1. **Treat as a regression** — collect all such warnings across the prompts, fix them,
   `checkpoint.py mark 3.5a in_progress`, re-run from detection.
2. **Dismiss for this PR only** — take a one-line reason and record
   `checkpoint.py set --append dismissed_for_pr='{"normalized": "<normalized text>", "warning": "<raw first line>", "reason": "<reason>"}'`.
   The diff reads these from the state file, so the re-run comes out clean; future sessions still
   see the warning.
3. **Dismiss permanently for this repo** — run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/localapp_diff.py dismiss --normalized "<normalized text>"`
   immediately, so a re-run in this session no longer asks, and commit the `.co-dwerker.json`
   change on the feature branch.

Entries reported as **unbaselined** (the baseline was skipped or missing) get the same three
options, errors included; without a baseline you cannot tell new from old, so the user decides.
An app the baseline captured but this run did not verify needs either a verify run or an explicit
user OK.

When every new warning has been fixed, dismissed for the PR, or dismissed permanently, run the
diff again; it exits 0.

---

## 5. What "complete" means for Step 3.5a

Exactly one of:

- **Clean pass** — every app booted healthy, the idle watch ran to completion, `localapp_diff.py`
  exits 0 (after any dismissals). `local_app_result=clean`.
- **User-acknowledged skip** — option 2 at the blocker gate; `local_app_skip_reason` is recorded.
  `local_app_result=skipped`.
- **No runnable app** — `.co-dwerker.json` has `local_app_skip: true`, whether cached or just set.
  `local_app_result=no_app`.

Whichever holds, record it: `checkpoint.py mark 3.5a completed --set local_app_result=<value>`.
`gate 3` needs the mark, not just the condition, and this reference is often read after the ground
rules in `skills/work/SKILL.md` have left the context. Do not mark the step from any other state.

---

## 6. PR description (Step 3.7)

Read `progress.context` and add to the PR test plan:

- skip: `- [ ] Local app verification: SKIPPED — <local_app_skip_reason>`
- dismissals for this PR: `- [x] Local app verification: PASS with dismissed warnings:` followed
  by one indented bullet per entry, `"<warning>" — dismissed: <reason>`
- no runnable app: `- [x] Local app verification: N/A — repo has no runnable application`
- clean: nothing extra; the standard checklist covers it.

---

## 7. Reference

### JSON produced by `localapp_capture.py`

Top level: `schema_version`, `mode`, `captured_at`, `branch`, `commit`, `issue_number`,
`boot_timeout_seconds`, `idle_seconds`, `apps[]`. Each app: `name`, `type`, `mode`, `command`,
`start_path`, `pid`, `boot_status`, `boot_duration_seconds`, `ready_signal_detected`,
`ready_signal_match`, `preflight.port_checks[]`, `preflight.config_checks[]`,
`preflight.failure_reasons[]` (when it failed), `http_probes[]`, `log_errors[]`,
`log_warnings[]`, `idle_watch_seconds_observed`, `exit_code`, `log_file`, and on failure
`last_output_lines[]`. Log entries carry `captured_at_offset_seconds`, `raw`, `normalized`,
`multiline`, `line_count`.

`boot_status`: `started` (ready signal seen) · `started_no_signal` (no signal, HTTP probe
answered) · `failed_to_start` (process exited during boot) · `timeout` (still running, no signal,
no probe response) · `crashed_during_idle` · `preflight_failed` · `skipped`.

Normalization strips ANSI codes, leading timestamps, UUIDs, long hex ids, PIDs, ports after a
host, memory addresses, and collapses whitespace. It keeps message text, exception types, and
in-repo file paths, so the same event on two boots produces the same key. The classifier matches
words like "error" and "warning" anywhere in a line, so "0 errors" or "error handler registered"
are captured too; they appear in both runs and diff out, but they inflate pre-existing counts.

### Edge cases

| Case | Behavior |
|------|----------|
| Baseline captured on an older commit than the verify run | Expected; the diff notes it and proceeds. |
| Several apps in one repo | Each has its own diff. Step 3.5a is complete only when every app is. |
| Baseline was `skipped` and the verify run also has a blocker | Nothing to diff; use the blocker gate. |
| `.co-dwerker.json` has both `local_app_command` and `local_app_skip: true` | Skip wins; mention the contradiction to the user. |
| Dismissing a warning that is no longer appearing | Harmless; the entry stays in `dismissed_warnings`. |
| Option 1 at a gate but the user did not actually fix anything | The same gate fires again; there is no loop because each pass waits for the user. |
| App keeps running after the capture | The script kills its process group (TERM, then KILL after 10 s). If a port is still busy afterwards, that process is not ours. |
