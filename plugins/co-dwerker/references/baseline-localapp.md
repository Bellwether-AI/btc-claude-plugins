# Baseline Local App Reference

This document specifies how `/co-dwerker:work` Phase 3 Step 1b (Baseline Local App) captures the unmodified branch's local-app boot behavior, errors, and warnings before any code changes. It is invoked from the brief Step 1b stub in `commands/work.md`. The downstream diff treatment is in `commands/work.md` Step 5a Local App Testing, which reads the file produced here.

## Purpose

Capture which boot-time and runtime errors/warnings already exist on the unmodified target branch when the app is run locally, so post-implementation local testing can distinguish regressions (caused by this work) from pre-existing issues (already broken, not this PR's problem). Boot failure on the unmodified branch is treated specially — see "Gate behavior on boot failure" below.

Run in the current working directory before the worktree is created in Phase 3 Step 3. The CWD reflects the target branch state with no co-dwerker edits.

## Detection

In this order, picking the first match. If multiple heuristics match, prefer the more specific one (e.g., `host.json` for Azure Functions wins over `package.json`):

1. **Azure Functions** — `host.json` in repo root or one level down. Command: `func start` (or project-configured equivalent).
2. **.NET (Azure App Services / generic web)** — `Program.cs` / `Startup.cs` / `*.csproj`. Command: `dotnet run` or `dotnet watch run` if configured.
3. **Python web** — `app.py`, `manage.py` (Django), `wsgi.py` / `asgi.py`, or `pyproject.toml` with `uvicorn`/`gunicorn`/`flask`/`fastapi` dependencies. Command picked by framework: `flask run`, `uvicorn app:app`, `python manage.py runserver`, `python app.py`.
4. **Node.js** — `package.json` with a `scripts.start` key. Command: `npm start` / `yarn start` / `pnpm start` based on lockfile.
5. **Docker Compose** — `docker-compose.yml` or `compose.yml`. Command: `docker compose up`.
6. **Project `CLAUDE.md` override** — if the repo's `CLAUDE.md` documents a specific local-run command (e.g., "to run locally use `make dev`"), prefer that over the detected default.

If nothing detected, do **not** write a baseline file. Tell the user (using the Step 1b skip template in `commands/work.md`): "No runnable application detected. Skipping local app baseline. Step 5a will skip the after-impl run as well." Return control to `commands/work.md` to continue to Step 2.

## Pre-flight checks

Before booting, verify the environment. **Only port conflicts and Azure Functions' missing `local.settings.json` are hard preflight failures** — everything else is recorded as informational metadata and the boot attempt proceeds.

- **Port availability** — Azure Functions defaults to 7071, Flask 5000, .NET varies. Run `lsof -i :<port>` (macOS/Linux) or framework default. **Port conflict → `preflight_failed` (always gates).** If the port is occupied, the boot will fail with a confusing error — better to detect now.
- **Required local config (Azure Functions only)** — check `local.settings.json` exists in the function-app directory. Missing `local.settings.json` is a **hard** preflight failure because `func start` will refuse to start without it. **Missing → `preflight_failed` (gates).**
- **Optional config files** (e.g., `.env` for Python, `appsettings.Development.json` for .NET) — record their presence/absence in the `preflight.config_checks[]` array but **do not treat missing files as preflight failures**. Many apps run fine without them, and we let the app's own startup fail naturally with a real error message rather than guessing what's required.

If preflight fails, do not attempt boot. Set `boot_status: "preflight_failed"` and proceed directly to the gate (see "Gate behavior on boot failure" below).

## Boot detection

Start the app as a background process. Determine "successfully booted" by combining a ready-signal scan with an HTTP probe:

### Ready signal scan

Watch the process's stdout/stderr for a framework-specific ready signal:

- **Azure Functions**: `Job host started` or `Worker process started`
- **.NET (Kestrel)**: `Now listening on:` or `Application started`
- **Flask**: `Running on http://`
- **uvicorn/gunicorn**: `Uvicorn running on` / `Started server process`
- **Django dev server**: `Starting development server at`
- **Node.js (Express, Next.js, etc.)**: best-effort match on `listening`, `server started`, or `ready on http`
- **Docker Compose**: each service prints its own ready signal; require all `up` services to log something matching the per-service patterns above, with a max wait of 60s

If the ready signal appears within the boot timeout (60 seconds default, configurable per framework), boot is considered successful. Record `boot_duration_seconds` as the elapsed time from process start to ready signal.

### HTTP probe (fallback / confirmation)

After ready signal (or after 60s if no signal detected), make an HTTP probe to the conventional health endpoint:

- Azure Functions: skip if no HTTP triggers; otherwise GET to the first HTTP-trigger route detected in `function.json` or function decorators
- Web frameworks: GET `/health`, then `/healthz`, then `/` in order — first non-5xx response wins
- Docker Compose: probe each service that exposes a port

Record probe results in the schema (endpoint, method, status code, duration). A probe is *informational* — it doesn't change `boot_status` unless ready-signal scan also failed.

### Boot status enum

- `started` — ready signal detected within boot timeout, OR HTTP probe returned non-5xx
- `started_no_signal` — ready signal not detected but HTTP probe succeeded (fallback path)
- `failed_to_start` — process exited within boot timeout with non-zero exit code, OR ready signal not detected AND HTTP probe failed
- `timeout` — boot timeout exceeded with no ready signal and no responsive probe
- `crashed_during_idle` — boot succeeded but process exited (with any code, zero or non-zero) during the 90s idle watch window
- `preflight_failed` — port conflict, missing required local config, etc. (no boot attempt made)
- `skipped` — detected but explicitly skipped by user choice (gate option 2)

## Idle watch (90 seconds)

After `boot_status == "started"` or `"started_no_signal"`, watch the process's stdout/stderr for **90 seconds** capturing error and warning entries. Rationale: some errors only surface from background timers, scheduled functions firing, queue consumers connecting, or lazy initialization. The agentic flow tolerates wall-clock time; we'd rather take 90s and catch real issues than rush and miss them.

During the watch:

- Capture lines matching error patterns (see "Log capture rules" below).
- Capture lines matching warning patterns.
- For Python tracebacks (header line `Traceback (most recent call last):` followed by indented frames), capture as a single multi-line entry.
- For .NET unhandled exceptions (`Unhandled exception:` followed by stack), capture as a single multi-line entry.
- For .NET ASP.NET error logs (`fail:` or `error:` prefix with brace block), capture the whole block.
- Stop capture after 90s and shut down the process cleanly (SIGTERM, then SIGKILL after 10s if still alive).

If the process exits *during* the idle watch (crash), capture the exit code, the last 50 lines of output, and any error/warning entries up to the exit point. Set `boot_status = "crashed_during_idle"`.

## Log capture rules

**Error patterns** (case-insensitive line match, anchored or substring):

- `error`, `err:`, `[error]`, `error:`, `\bERR\b`
- `exception`, `Exception:`, `exception:`
- `traceback (most recent call last)` (Python)
- `unhandled exception` (.NET)
- `fatal`, `FATAL`
- `panic:` (Go)
- `[critical]`, `critical:`

**Warning patterns** (case-insensitive):

- `warn`, `warning`, `[warn]`, `[warning]`
- `deprecated`, `deprecation`
- Framework-specific: `RuntimeWarning`, `DeprecationWarning`, `UserWarning` (Python); `warn:` (npm/Node); `[WARN]` (logback/.NET)

**Multi-line entry detection** (apply in order):

1. If a line starts with `Traceback (most recent call last):`, capture it and all subsequent indented lines + the final exception-type line as one entry.
2. If a line starts with `Unhandled exception` or matches `^System\.\w+Exception:`, capture it and subsequent indented stack frames as one entry.
3. If a line starts with `at <something>` (.NET/Java stack frame) and the previous captured line ended with an exception type, fold it into that previous entry.
4. Otherwise, each match is a single-line entry.

**Severity ordering for diff**: errors are more important than warnings. The downstream diff treatment in `commands/work.md` Step 5a will report new errors first, then new warnings.

## Normalization for diff

Raw log lines include volatile fields that would defeat exact-match diffing. Normalize before storing the diff key — keep BOTH raw and normalized in the schema so the user sees real text but the diff matches on normalized:

**Strip patterns** (apply in order, each is a regex replace with empty string except where noted):

1. **ANSI escape codes**: `\x1b\[[0-9;]*[a-zA-Z]`
2. **ISO 8601 timestamps at line start**: `^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}([.,]\d+)?(Z|[+-]\d{2}:?\d{2})?\s*`
3. **Other timestamp formats at line start**: `^\[\d{2}/[A-Za-z]+/\d{4} \d{2}:\d{2}:\d{2}\]\s*` (Apache/nginx style), `^\[\d{2}:\d{2}:\d{2}\]\s*` (short time)
4. **UUIDs**: `\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b` → `<uuid>`
5. **Long hex strings (request IDs, hashes)**: `\b[0-9a-fA-F]{16,}\b` → `<hex>`
6. **PIDs in common formats**: `\bPID[: ]?\d+\b` → `PID <pid>`, `\bpid=\d+\b` → `pid=<pid>`, `\[\d+\](?=\s)` → `[<pid>]`
7. **Port numbers in URLs**: `:(\d{4,5})\b` → `:<port>` (only when preceded by a host or `://`)
8. **Memory addresses**: `0x[0-9a-fA-F]+` → `<addr>`
9. **Whitespace collapse**: multiple internal spaces → single space, strip leading/trailing whitespace.

**Keep**: line content, error/exception type names, file paths (within the repo — these are stable across boots), function names, error messages.

The normalized form is what the downstream Step 5a diff matches on. The raw form is what gets printed to the user in summaries.

## Gate behavior on boot failure

This is the **key difference from the test baseline**. Pre-existing test failures are common and worth working around (capture-and-continue). Pre-existing local-app boot failures mean the agent's after-impl Step 5a has nothing meaningful to compare against, and silently continuing would defeat the whole point.

If `boot_status` is `failed_to_start`, `timeout`, `preflight_failed`, or `crashed_during_idle`, **stop** and present to the user via `AskUserQuestion`:

> "Local app baseline failed on the unmodified branch:
>
> **{boot_status}**: {reason — for `preflight_failed` include the failing check; for `timeout` include elapsed seconds; for `failed_to_start` include the exit code; for `crashed_during_idle` include the exit code and time-into-watch}
>
> {if any error entries were captured before the failure, include the first 3; otherwise include "No error entries captured before failure — check stdout/stderr of `{command}` manually."}
>
> The post-implementation comparison won't be meaningful without a successful baseline. How do you want to proceed?
>
> 1. **Fix the environment and retry baseline** — I'll pause while you address the issue (start a missing service, free the port, set local config), then re-run Step 1b.
> 2. **Skip the baseline capture for this session** — a baseline file with `boot_status: "skipped"` is written so Step 5a knows you opted out; Step 5a will still run after implementation but will treat all errors and warnings as potentially new (not blocking).
> 3. **Cancel this session** — abort `/co-dwerker:work` so you can address the environment issue without the workflow waiting on you."

On choice 1, loop back to pre-flight and retry. On choice 2, write a baseline file with `boot_status: "skipped"`, empty `log_errors` / `log_warnings`, and return to `commands/work.md` Step 1b to continue. On choice 3, exit `/co-dwerker:work` cleanly.

This is the **only** `AskUserQuestion` gate added by the v0.3.4 changes — every other branch in this reference and in Step 1 Baseline Tests is capture-and-continue.

## Time cap

15 minutes cumulative across all detected apps (most repos have one; Docker Compose may have several services counted together as one app for cap purposes). The cap covers boot + idle watch + probe time, not detection.

If the cap is reached while a single app is mid-boot or mid-idle, terminate the process, record what was captured with `boot_status: "timeout"`, mark any undetected/unstarted apps `timeout` with empty captures, and gate (boot-failure rules above apply).

## Write the baseline file

Before writing, add the file to the repo's local git exclude so intermediate `superpowers:executing-plans` commits do not accidentally include it:

```bash
grep -qxF '.co-dwerker.baseline-localapp.json' .git/info/exclude 2>/dev/null \
  || echo '.co-dwerker.baseline-localapp.json' >> .git/info/exclude
```

(This only affects the local clone; the repo's `.gitignore` is not modified.)

Write `.co-dwerker.baseline-localapp.json` to the repo root using the schema below:

## Schema

```json
{
  "captured_at": "<ISO 8601 UTC>",
  "branch": "<current branch>",
  "commit": "<git rev-parse HEAD>",
  "issue_number": <ACTIVE_ISSUE>,
  "apps": [
    {
      "name": "azure_functions",
      "type": "azure_functions",
      "command": "func start",
      "start_path": ".",
      "boot_status": "started",
      "boot_duration_seconds": 14,
      "ready_signal_detected": true,
      "ready_signal_match": "Job host started",
      "preflight": {
        "port_checks": [{"port": 7071, "available": true}],
        "config_checks": [{"file": "local.settings.json", "present": true}]
      },
      "http_probes": [
        {"endpoint": "/api/HelloWorld", "method": "GET", "status_code": 200, "duration_ms": 47}
      ],
      "log_errors": [
        {
          "captured_at_offset_seconds": 8,
          "raw": "2026-05-15T14:23:00.123Z [Error] AuthMiddleware: failed to load JWT signing key (request abc-123-def)",
          "normalized": "[Error] AuthMiddleware: failed to load JWT signing key (request <uuid>)",
          "multiline": false
        }
      ],
      "log_warnings": [
        {
          "captured_at_offset_seconds": 2,
          "raw": "WARNING:root:Deprecated config key `legacy_mode` will be removed in v2.0",
          "normalized": "WARNING:root:Deprecated config key `legacy_mode` will be removed in v2.0",
          "multiline": false
        }
      ],
      "idle_watch_seconds_observed": 90,
      "exit_code": null
    }
  ]
}
```

### Field notes

- `type` enum: `azure_functions`, `dotnet`, `python_flask`, `python_django`, `python_fastapi`, `python_uvicorn`, `python_generic`, `node`, `docker_compose`, `custom` (when driven by `CLAUDE.md` override).
- `boot_status` enum: `started`, `started_no_signal`, `failed_to_start`, `timeout`, `crashed_during_idle`, `preflight_failed`, `skipped`.
- `log_errors[].multiline` / `log_warnings[].multiline`: `true` when the entry spans multiple lines (Python tracebacks, .NET stacks).
- `idle_watch_seconds_observed`: actual seconds watched (may be less than 90 if the process exited early or the cumulative cap hit).
- `exit_code`: `null` while running, integer if the process exited during boot or idle watch.
- `preflight.port_checks[]`: every port the framework needs, with `available: true` if free at preflight time. Any `false` entry means port conflict and `boot_status: "preflight_failed"`.
- `preflight.config_checks[]`: framework-relevant config files with `present: true` / `false`. For Azure Functions, `local.settings.json` missing triggers `preflight_failed`. For other frameworks, this is informational only.

## Edge cases

| Case | Behavior |
|------|----------|
| Multiple apps in repo (e.g., monorepo with `frontend/` and `backend/`) | Detect each as a separate entry in `apps[]`. Same precedence rules; baseline each independently. |
| Docker Compose with 5 services | One `apps[]` entry with `type: "docker_compose"`. The per-service ready signals are aggregated; if any service fails, the whole entry is `failed_to_start`. |
| App requires external dependencies (database, queue) | If detected (e.g., `.env` references `DATABASE_URL`), attempt boot anyway. If boot fails due to connection refused, the gate question shows the error so the user knows to start the dependency. |
| App boots but produces 200+ warnings | Capture all of them; the schema doesn't truncate warnings. If file size becomes problematic (>1MB), revisit. |
| Process never exits (long-running) | Always SIGTERM after the 90s idle window. SIGKILL fallback at +10s. |
| Boot takes longer than 60s but eventually succeeds | Mark `boot_status: "timeout"` and gate. User can choose to fix or skip. |
| Repo has `host.json` AND `package.json` with start script | Azure Functions wins (more specific). |
| `CLAUDE.md` says `make dev` to run locally | Override wins; framework detection is bypassed; `type: "custom"`. |
| User has the app already running on the port from another terminal | `preflight_failed` with reason "port in use"; gate. |

## What to do after capture

Return control to `commands/work.md` Step 1b, which will surface a summary to the user (using the templates defined there) and continue to Step 2 (Plan).
