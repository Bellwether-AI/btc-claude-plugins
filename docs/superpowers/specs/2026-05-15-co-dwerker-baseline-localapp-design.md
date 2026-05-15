# Design: co-dwerker Phase 3 Step 1b — Baseline Local App

**Status:** Approved in conversation (2026-05-15), pending written-spec review.
**Target release:** co-dwerker v0.3.4.
**Builds on:** v0.3.3's Phase 3 Step 1 (Baseline Tests), which established the capture-and-continue pattern this design extends.

## Context

`/co-dwerker:work` Phase 3 today has a Step 5a (Local App Testing) that boots the application after implementation and watches the logs for errors. The agent has no way to tell a *pre-existing* startup warning or runtime error from a *new* one introduced by this issue's work. This mirrors the test-baseline gap we closed in v0.3.3 — and the fix is the same shape: capture the unmodified branch's local-app behavior up front, diff against it after implementation.

The motivating asymmetry: tests have determinism (a failing test is a failing test). Local apps have *log volume* — every boot produces dozens of lines, many of which are deprecation warnings, info-level noise, or framework chatter that's been there for months. Without a baseline, the agent either reports every line as a potential issue (spam) or ignores log content entirely (missed regressions). With a baseline, it reports only what *changed* since the unmodified branch.

## Goal

Add a new **Phase 3 Step 1b: Baseline Local App** that:

1. Detects whether the repo contains a runnable application using the same heuristics as Step 5a.
2. Boots the app in the working directory before any planning or coding.
3. Captures boot status, boot duration, log errors, log warnings, and HTTP probe results.
4. Writes the result to `.co-dwerker.baseline-localapp.json`.
5. **Gates the workflow** if the unmodified branch can't boot the app — surfaces to the user via `AskUserQuestion` so they can fix the environment, skip baseline for this session, or cancel.
6. Provides Step 5a with a normalized diff target so it can classify post-implementation log entries as pre-existing, new, or resolved.

## Non-goals

- **Not** a full log capture to file. We capture only error-level and warning-level entries plus structural metadata (boot duration, probe results). Full log streams stay in process stdout and are discarded after the watch window.
- **Not** a replacement for Step 5a. Step 5a still runs after implementation; this new step only establishes the baseline it will diff against.
- **Not** a continuous integration substitute. This is local, single-machine, single-run. Flaky failures will produce noisy baselines; that's accepted.
- **Not** environment provisioning. If local secrets, port binds, or external services aren't ready, we gate and ask the user — we don't try to fix the environment.

## High-level flow

```
Phase 3 Execute (v0.3.4):
  Step 1   Baseline Tests           (refactored — inline stub points to references/baseline-tests.md)
  Step 1b  Baseline Local App       (NEW — inline stub points to references/baseline-localapp.md)
  Step 2   Plan
  Step 3   Isolate (worktree)       — copies BOTH baseline files into worktree
  Step 4   Implement
  Step 5   Verify                   — reads test baseline; diff logic stays inline (downstream consumer)
  Step 5a  Local App Testing        — reads localapp baseline; diff logic stays inline (UPDATED)
  Step 6   Changelog
  Step 7   Create PR
  Step 8   Review
```

## Skill-file organization (Option B — reference file extraction)

Per skill-creator's <500-line guideline and the user's explicit preference, this release uses the **reference file extraction pattern** rather than inlining all detail in work.md. Precedent: `plugins/co-dwerker/references/setup-project-board.md` is already loaded on demand from work.md.

**What stays inline in `commands/work.md` (Step 1 and Step 1b):**

- Brief description (1-2 sentences) of what the step does and why.
- The three user-facing summary templates (failure / clean / skip variants) — these are short, frequently referenced by other steps, and benefit from being visible during the workflow.
- A single pointer: "Read `references/baseline-tests.md` (or `baseline-localapp.md`) for the detection cascade, schema, capture rules, and gate behavior. Follow its instructions to perform the capture, then return to Step 2."

**What moves to `references/baseline-tests.md`** (extracted from current v0.3.3 work.md Step 1):

- Detection cascade (CLAUDE.md → manifests → skip).
- Run-each-suite mechanics, timeout semantics, tooling-missing handling.
- `.git/info/exclude` write pattern.
- Full schema for `.co-dwerker.baseline-tests.json` (including field notes, enum values, `kind`, `failing_tests_truncated`).
- The skip-case rule (no file written when nothing detected).

**What moves to `references/baseline-localapp.md` (NEW):**

- Detection heuristics (5 framework types + `CLAUDE.md` override).
- Pre-flight checks and which are hard failures vs informational.
- Boot detection (ready-signal scan + HTTP probe fallback) with framework-specific patterns.
- 90-second idle watch mechanics, multi-line entry detection.
- Log capture rules (error patterns, warning patterns).
- Normalization pipeline (9 strip patterns, multi-line detection).
- Full schema for `.co-dwerker.baseline-localapp.json` with field notes.
- Gate behavior on baseline boot failure (the `AskUserQuestion` with 3 options).
- Cumulative 15-min cap mechanics.
- Edge-case table.

**What stays inline in `commands/work.md` (Step 5 and Step 5a — downstream consumers):**

- The diff treatment logic. This is tightly coupled to the consuming phase step, is short enough to read in place, and benefits from being adjacent to the rest of the verify/test-app instructions. Moving it to a reference would require Step 5 / Step 5a to read TWO files (their own phase content + the diff reference), which adds friction without saving meaningful space.

**Rationale for this split:**

The capture mechanics (detection, boot, log capture, normalization, schema, gate) are detail-heavy implementation specs — exactly the kind of content that drowns out surrounding step instructions if inlined. The diff treatment is consumer logic that lives naturally inside the consuming step. This split preserves locality where it matters and abstracts where it bloats.

## Detection

Reuse the existing Step 5a detection heuristics in detection-priority order:

1. **Azure Functions** — `host.json` in repo root or one level down. Command: `func start` (or project-configured equivalent).
2. **.NET (Azure App Services / generic web)** — `Program.cs` / `Startup.cs` / `*.csproj`. Command: `dotnet run` or `dotnet watch run` if configured.
3. **Python web** — `app.py`, `manage.py` (Django), `wsgi.py` / `asgi.py`, or `pyproject.toml` with `uvicorn`/`gunicorn`/`flask`/`fastapi` dependencies. Command picked by framework: `flask run`, `uvicorn app:app`, `python manage.py runserver`, `python app.py`.
4. **Node.js** — `package.json` with a `scripts.start` key. Command: `npm start` / `yarn start` / `pnpm start` based on lockfile.
5. **Docker Compose** — `docker-compose.yml` or `compose.yml`. Command: `docker compose up`.
6. **Project `CLAUDE.md` override** — if the repo's `CLAUDE.md` documents a specific local-run command (e.g., "to run locally use `make dev`"), prefer that over the detected default.

If multiple detection heuristics match (e.g., both `host.json` and `package.json`), prefer the more specific one — same precedence rule Step 5a already uses.

If nothing detected, write **no** baseline file and tell the user: "No runnable application detected. Skipping local app baseline. Step 5a will skip the after-impl run as well." Continue to Step 2 Plan.

## Pre-flight checks

Before booting, verify the environment is ready. If any check fails, **gate** (see "Gate behavior" below):

- **Port availability** — Azure Functions defaults to 7071, Flask 5000, .NET varies. Run `lsof -i :<port>` (macOS/Linux) or framework default. If the port is occupied, the boot will fail with a confusing error — better to detect now. **Port conflict → `preflight_failed` (always gates).**
- **Required local config (Azure Functions only)** — check `local.settings.json` exists in the function-app directory. Missing `local.settings.json` is a **hard** preflight failure for Azure Functions because `func start` will refuse to start without it. **Missing → `preflight_failed` (gates).**
- **Optional config files** (e.g., `.env` for Python, `appsettings.Development.json` for .NET) — record their presence/absence in the `preflight.config_checks[]` array but **do not treat missing files as preflight failures**. Many apps run fine without them, and we let the app's own startup fail naturally with a real error message rather than guessing what's required.

Only port conflicts and Azure Functions' missing `local.settings.json` are hard preflight failures. Everything else is recorded as informational metadata and the boot attempt proceeds.

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

If the process exits *during* the idle watch (crash), capture the exit code, the last 50 lines of output, and any error/warning entries up to the exit point. Set `boot_status = "crashed_during_idle"` (new enum value).

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

**Severity ordering for diff**: errors are more important than warnings. Step 5a will report new errors first, then new warnings.

## Normalization for diff

Raw log lines include volatile fields that would defeat exact-match diffing. Normalize before storing the diff key (we keep BOTH raw and normalized in the schema so the user sees real text but the diff matches on normalized):

**Strip patterns** (apply in order, each is a regex replace with empty string):

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

The normalized form is what Step 5a's diff matches on. The raw form is what gets printed to the user in summaries.

## Gate behavior on boot failure

This is the **key difference from test baseline**. Pre-existing test failures are common and worth working around (capture-and-continue). Pre-existing local-app boot failures mean the agent's after-impl Step 5a has nothing meaningful to compare against, and silently continuing would defeat the whole point.

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
> 2. **Skip local app baseline for this session** — Step 5a still runs after implementation but has no baseline to diff against; all errors and warnings will be treated as potentially new.
> 3. **Cancel this session** — abort `/co-dwerker:work` so you can address the environment issue without the workflow waiting on you."

On choice 1, loop back to Step 1b pre-flight. On choice 2, write a baseline file with `boot_status` recorded and an empty `log_errors` / `log_warnings` array, then continue to Step 2. On choice 3, exit cleanly.

This is the **only** AskUserQuestion gate added by this change — every other branch is capture-and-continue.

## Time cap

15 minutes cumulative across all detected apps (most repos have one; Docker Compose may have several services counted together as one app for cap purposes). The cap covers boot + idle watch + probe time, not detection.

If the cap is reached while a single app is mid-boot or mid-idle, terminate the process, record what was captured with `boot_status: "timeout"`, mark any undetected/unstarted apps `timeout` with empty captures, and gate (boot failure rules above apply).

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

Field notes:

- `type` enum: `azure_functions`, `dotnet`, `python_flask`, `python_django`, `python_fastapi`, `python_uvicorn`, `python_generic`, `node`, `docker_compose`, `custom` (when driven by `CLAUDE.md` override).
- `boot_status` enum: `started`, `started_no_signal`, `failed_to_start`, `timeout`, `crashed_during_idle`, `preflight_failed`, `skipped`.
- `log_errors[].multiline`: true when the entry spans multiple lines (Python tracebacks, .NET stacks).
- `idle_watch_seconds_observed`: actual seconds watched (may be less than 90 if the process exited early or the cumulative cap hit).
- `exit_code`: null while running, integer if the process exited during boot or watch.

## Step 5a diff (post-implementation)

After implementation completes (current Step 5a behavior, updated):

1. **Run the same detection** to find the app(s) to boot.
2. **Boot and watch** using the same logic as Step 1b (90s idle, 15min cap, same enum semantics). This produces a "current" snapshot.
3. **If no baseline file exists** (Step 1b skipped or was opted out): report all errors/warnings as potentially new, prefixed with a "no baseline available" warning. Do not block.
4. **If baseline file exists**: diff the current snapshot against the baseline on the normalized form of each entry:
   - **Pre-existing** (in both) → report under "Pre-existing (was broken before this work)" — informational, do not block.
   - **New** (in current only) → report under "New errors / warnings (likely caused by this work)" — **errors block; warnings do not**.
   - **Resolved** (in baseline only) → report under "Resolved (was failing in baseline, clean now)" — positive side effect.
5. **Boot status comparison** (treat `started` and `started_no_signal` as equivalent "healthy boot" for comparison purposes; treat `failed_to_start`, `timeout`, `crashed_during_idle`, and `preflight_failed` as equivalent "boot failure"):
   - Baseline healthy → current healthy: normal log-entry diff applies.
   - Baseline healthy → current boot failure: **REGRESSION**, block, force fix before proceeding. Report the specific current `boot_status` and the first 3 error entries from the current snapshot.
   - Baseline boot failure → current healthy: positive side effect, report enthusiastically.
   - Baseline boot failure → current boot failure: report both statuses but do not block (the baseline was already failing; this work didn't change that). Special case: if the *specific* failure mode differs (e.g., baseline was `timeout` and current is `crashed_during_idle`), flag for user attention.
   - Baseline `skipped` (user opted out at Step 1b gate): no comparison possible; report current state without baseline framing, treat all errors as potentially new but do not block.

The block-on-new-errors rule mirrors the test-baseline regression rule. Warnings stay informational because warning churn is high and unactionable churn would block too often.

## Lifecycle

- **Step 1b** (NEW): writes `.co-dwerker.baseline-localapp.json` to repo root; appends filename to `.git/info/exclude` (same idempotent grep-or-echo pattern as test baseline).
- **Step 3 Isolate**: copies BOTH `.co-dwerker.baseline-tests.json` AND `.co-dwerker.baseline-localapp.json` into the worktree root, and ensures both filenames are in the worktree's `.git/info/exclude`.
- **Step 5a** (UPDATED): reads `.co-dwerker.baseline-localapp.json` from worktree, performs diff.
- **Phase 5 Step 6 Clean Up**: `rm -f` both baseline files from BOTH the worktree path and the main repo root (same pattern v0.3.3 introduced for the test baseline).

## Configuration knobs (none for this release)

To keep scope tight, this release has **no** new config keys in `.co-dwerker.json`. The 90s idle watch, 15min cap, and detection heuristics are baked in. If real-world use surfaces a need (e.g., a project where 90s is too short or 60s is plenty), we'll add config keys in a follow-up.

## Edge cases

| Case | Behavior |
|------|----------|
| Multiple apps in repo (e.g., monorepo with `frontend/` and `backend/`) | Detect each as a separate entry in `apps[]`. Same precedence rules; baseline each independently. |
| Docker Compose with 5 services | One `apps[]` entry with `type: "docker_compose"`. The per-service ready signals are aggregated; if any service fails, the whole entry is `failed_to_start`. |
| App requires external dependencies (database, queue) | If detected (e.g., `.env` references `DATABASE_URL`), we attempt boot anyway. If boot fails due to connection refused, the gate question shows the error so the user knows to start the dependency. |
| App boots but produces 200+ warnings | Capture all of them; the schema doesn't truncate warnings. If file size becomes problematic (>1MB), revisit. |
| Process never exits (long-running) | Always SIGTERM after the 90s idle window. SIGKILL fallback at +10s. |
| Boot takes longer than 60s but eventually succeeds | Mark `boot_status: "timeout"` and gate. User can choose to fix or skip. (Future config knob could extend boot timeout; not in this release.) |
| Repo has `host.json` AND `package.json` with start script | Azure Functions wins (more specific). |
| `CLAUDE.md` says `make dev` to run locally | Override wins; framework detection is bypassed; `type: "custom"`. |
| User has the app already running on the port from another terminal | `preflight_failed` with reason "port in use"; gate. |

## Testing approach

Since this is markdown skill content (instructions to the LLM agent), there is no unit test suite. Verification is:

1. **Self-review of work.md** after edits: read end-to-end, confirm all step numbers cross-reference correctly, no dangling references.
2. **JSON schema example** must parse as valid JSON.
3. **Self-consistency**: every field referenced in the Step 5a diff section must exist in the schema.
4. **PR code review and skill review** via the same multi-agent pipeline used for v0.3.3.
5. **Smoke test (manual, optional after merge)**: run `/co-dwerker:work` against `btc-claude-plugins` itself (no app to detect — should skip silently) and against a known Azure Functions repo (should boot, capture, diff).

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Idle watch too short — misses background errors | Medium | Medium | Set to 90s (generous default); revisit if real-world feedback shows misses. |
| Normalization regex strips too much (false matches) | Low | Medium | Keep both raw and normalized in schema so user can verify diff judgments. |
| Normalization regex strips too little (false negatives in diff) | Medium | Low | Iterate normalization rules based on real-world misses; same raw-and-normalized escape hatch helps. |
| Gate on boot failure annoys users with flaky local environments | Medium | Low | Gate offers a "skip baseline this session" option — single click to bypass. |
| Multi-line traceback detection misses some frameworks | Low | Medium | Document fallback: any unrecognized error format gets captured as single-line; the LLM agent can adapt if a real case emerges. |
| Cumulative 15min cap insufficient for slow boots | Low | Medium | Gate behavior surfaces this clearly; user can choose to skip baseline if their environment is just slow. |
| Baseline file grows large in warning-heavy environments | Low | Low | No truncation in initial release; revisit if file > 1MB in real use. |

## Out of scope (future iteration)

- **Config knobs** in `.co-dwerker.json` for idle-watch duration, boot timeout, custom log patterns.
- **Per-app caps** (currently only cumulative cap exists).
- **Snapshot-based ready detection** (instead of substring match — e.g., wait for process to reach steady CPU/memory).
- **Custom probe paths** beyond `/health`, `/healthz`, `/` (would need config).
- **Distinguishing "warning we always see" from "warning we should fix someday"** — out of scope; the diff treats both the same.
- **Cross-session learning** — using prior baselines from past sessions to detect chronic issues. Out of scope; baselines are per-issue ephemeral.

## Versioning and release

- Bump `co-dwerker` to **v0.3.4** in both `plugins/co-dwerker/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.
- CHANGELOG.md and RELEASE_NOTES.md updates following the same pattern as v0.3.3.
- Single PR, same multi-stage pipeline: functional commit → docs commit → PR → code review + skill review in parallel → address findings → re-verify → merge.

## Files modified

- `plugins/co-dwerker/commands/work.md` —
  - **Step 1 Baseline Tests**: refactor from ~100 lines inline to ~15-line stub (description + summary templates + pointer to reference). Retroactive extraction of v0.3.3 content as part of this PR.
  - **Step 1b Baseline Local App**: NEW stub (~15 lines) pointing to `references/baseline-localapp.md`.
  - **Step 3 Isolate**: extend the existing copy-to-worktree block to handle BOTH baseline files (test and localapp); same `.git/info/exclude` propagation pattern.
  - **Step 5 Verify**: no structural change — diff treatment logic remains inline as today.
  - **Step 5a Local App Testing**: extend with localapp baseline diff treatment (inline, mirrors Step 5's pattern). Detection of "no baseline file present" handled here too.
  - **Phase 5 Step 6 Clean Up**: extend `rm -f` to remove `.co-dwerker.baseline-localapp.json` from both worktree and main repo root.

## Files created

- `plugins/co-dwerker/references/baseline-tests.md` — NEW. ~100 lines of detail extracted from current v0.3.3 work.md Step 1.
- `plugins/co-dwerker/references/baseline-localapp.md` — NEW. ~250 lines covering detection / preflight / boot / idle watch / log capture / normalization / schema / gate behavior / 15-min cap / edge cases.

## Files modified (versioning + docs)

- `plugins/co-dwerker/.claude-plugin/plugin.json` — version bump to 0.3.4.
- `.claude-plugin/marketplace.json` — version bump to 0.3.4.
- `CHANGELOG.md` — v0.3.4 entry. Must mention BOTH the new Step 1b feature AND the v0.3.3 Step 1 retroactive extraction to reference file (since work.md content shifts in this PR even for existing functionality).
- `RELEASE_NOTES.md` — v0.3.4 entry. User-facing framing of the local-app baseline; the reference-file extraction is an internal cleanup and gets a brief "internal: skill-file organization" note rather than top-billing.

## Files NOT modified

- `plugins/co-dwerker/commands/pr-review.md` — no PR review changes needed.
- `plugins/co-dwerker/commands/exit.md` — no state changes (baseline files are ephemeral, don't persist via exit).
- `plugins/co-dwerker/commands/docs.md` — unrelated.
- `plugins/co-dwerker/commands/new-issue.md` — unrelated.
- `plugins/co-dwerker/README.md` — README is high-level; baseline mechanism is an internal Phase 3 detail.

## work.md line-count math

- v0.3.3 work.md: ~780 lines.
- After this PR: ~660 lines (despite adding Step 1b feature) because Step 1 extraction nets out larger than Step 1b's stub addition.
- This drops work.md below the v0.3.2 baseline (~678 lines) and represents the first time work.md trends DOWN while gaining features since v0.3.0.
