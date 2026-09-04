# Release Notes

## co-dwerker v1.0.0

### What's New

**Built for current Claude Code on Fable-class models.** An audit against the live Claude Code
harness found that several v0.3.x mechanisms had gone stale, and one of them had stopped working
entirely. v1.0.0 fixes all of them and takes the opportunity to cut the main workflow file in half.

**Step tracking that actually runs.** The old step-skipping guard asked the agent to create a task
per step with `TaskCreate`. Those tools are disabled by default on Fable 5, Opus 4.8 and Sonnet 5,
so since Claude Code 2.1.233 the guard was a no-op. It is replaced by `scripts/checkpoint.py`,
which records progress in `.co-dwerker.state.json` at every step boundary and refuses to open a
phase gate while steps are missing. A crash or a compacted context now resumes at the exact step,
in the recorded worktree.

**Local app verification is now script-driven.** One Python script boots the app, pre-flights
ports and required config, waits for the framework's ready signal (or probes HTTP), watches for 90
seconds, shuts down cleanly, and records normalized errors and warnings. The same script runs
before implementation (baseline) and after (verification), so the diff compares like with like. A
second script does the diff, groups repeated warnings, respects permanent dismissals, and exits
with a code the agent acts on: clean, needs your decision, or blocked. Booting the app before a PR
exists remains a hard gate; the only ways past it are a clean diff, a skip you choose with a
recorded reason, or a repo marked as having no runnable app.

**The best model, everywhere.** The plugin no longer tells you to run `/model opus` (a downgrade
on a Fable session). It suggests `/model best`, which resolves to the latest Fable model where your
account has it and Opus otherwise, and subagents inherit whatever the session runs. Haiku is never
used. Cost is controlled by running at most two subagents at a time, never by lowering quality.

**Modern plugin layout.** Skills live in `skills/<name>/SKILL.md` (the layout Claude Code now
recommends), reference files are addressed with `${CLAUDE_PLUGIN_ROOT}`, the bundled scripts are
pre-approved via `allowed-tools`, and the deprecated `work-bellwether-project` alias is hidden from
the model's skill list while still working if you type it.

**Half the size, one source of truth.** The work skill went from 786 to about 345 lines. Repo
detection has its own reference. Environment setup, model policy, checkpoints, waiting rules,
worktree handling, and every file schema live once in `references/conventions.md` instead of being
copied into five files. Skill descriptions now say when to use the skill rather than summarizing
its workflow, which testing has shown makes agents read the body instead of improvising from the
description.

### Behavior Changes

- Every `/co-dwerker:work` step writes a checkpoint to `.co-dwerker.state.json` in the main
  checkout during the session, not only at exit. The script keeps the file out of `git status`
  through the clone's `.git/info/exclude`; nothing is added to your committed `.gitignore`.
- Gates are presented as structured choices (`AskUserQuestion` options) with the recommended
  option first.
- Phase 5 cleanup uses `ExitWorktree` when the worktree was created natively and `git worktree
  remove` otherwise. `git branch -D` is used after a squash merge since `-d` would refuse.
- CI is watched with `gh run watch --exit-status` under a 10-minute timeout rather than a polling
  loop with `sleep`.
- New per-issue files appear beside the baseline JSON: `.co-dwerker.verify-localapp.json`,
  `.co-dwerker.localapp-diff.json`, and `.co-dwerker.localapp-<app>-<mode>.log`. All are excluded
  from git by the scripts and deleted at Phase 5 cleanup.
- `/co-dwerker:exit` no longer derives the auto-memory directory with a `sed` transform; it uses
  the directory your session already loads `MEMORY.md` from.
- Dismissed-for-this-PR warning reasons are now persisted in the state file, so exiting between
  Step 3.5a and Step 3.7 no longer loses them, and the verification diff honors them.
- Steps are referred to by their checkpoint ids (Step 3.1b, Step 3.5a) throughout the skill text.

**Reviewed before release.** Four independent review passes (skill-creator framework,
superpowers writing-skills, a Python code review, and a live dry run that executed the
instructions in a scratch repo with a real worktree) caught and fixed defects before this shipped.
Two are worth knowing about: every project-mode `gh project` command had passed `owner/repo` where
GitHub wants the owner login, so project mode had been failing at the first board call since
v0.3.x; and the capture script could leave an app's child processes running when a launcher
exited early, which would have made the next verification blame "a process that is not ours".
See the CHANGELOG "Fixed" list.

### Requirements

- `python3` 3.9 or newer on PATH (the scripts are stdlib-only; no packages to install).
- superpowers, pr-review-toolkit, commit-commands, and episodic-memory plugins, as before.

### Known Issues

- `allowed-tools` substitution of `${CLAUDE_PLUGIN_ROOT}` in frontmatter is documented but not yet
  observed in daily use. If Claude Code still prompts for permission to run the scripts, that is
  the first thing to report.
- Shell variables do not persist between the agent's Bash calls; the skills now say so and treat
  `$NAME` as "the value you determined earlier", but an agent that forgets will get an empty
  variable rather than an error.
- `localapp_capture.py` has best-effort Windows handling (no process groups) and has only been
  exercised on macOS.
- The test baseline (Phase 3 Step 1) is still captured by the agent following prose; only the
  local-app side has scripts.
- The capture script's log classifier treats "error(s)", "err", "warning(s)" and "warn" as level
  words only when they stand alone (`ERROR:app`, `[warn]`, `npm ERR!`, `2 errors`). Prose such as
  "error handler registered" is still captured; it appears in both runs and diffs out, but it
  inflates the pre-existing counts. Captures made by an older script version carry a lower
  `schema_version`; re-run the baseline rather than diffing across versions.

### Upgrade Notes

- No data migration. Existing `.co-dwerker.json` and `.co-dwerker.state.json` files continue to
  work; `progress` and the new context keys are added on first use.
- If you had `/co-dwerker:work-bellwether-project` in muscle memory it still works; it simply
  redirects.

---

## azure-appservice-cert-rollout v0.1.0

### What's New

A new plugin for rolling out a Bring-Your-Own-Certificate (BYOC) TLS certificate to Azure App Services across one or many subscriptions in a tenant. Designed for the MSP / multi-client case: one operator with access to many tenants and subscriptions, rolling out a renewed wildcard or hostname cert across an arbitrary set of App Services, with production-safety bias turned all the way up.

The plugin ships one skill — `azure-appservice-cert-rollout` — that auto-triggers on phrases like "renew the wildcard cert across all our Azure web apps", "push the new PFX to the App Services", "fix the cert chain on the App Service", "the GoDaddy/DigiCert cert is expiring", or mentions of `az webapp config ssl`.

### Why it exists

The straightforward Azure CLI sequence for renewing an uploaded cert (`az webapp config ssl upload` → `bind` → `delete`) has three real failure modes:

1. **Silent chain-less PFX.** `az webapp config ssl upload` accepts a leaf-only PFX without warning. Browsers cache common intermediates so the missing chain isn't visible from the operator's laptop, but mobile apps, headless clients, and minimal-trust-store environments fail TLS validation.
2. **Wrong tenant / subscription scope.** MSP operators have CLI access to many clients' tenants. One mis-targeted command can rebind certs in the wrong client's environment.
3. **Untested batch loops.** Writing a shell loop to "do all 20 apps at once" adds a new failure surface (shell quoting, set-e behavior, error swallowing) separate from whether the per-resource operation works.

This plugin encodes defenses against all three.

### What it does

A 9-step workflow with three operator gates:

1. **Tenant + scope confirmation** (gate) — confirm signed-in tenant matches operator intent, resolve subscription scope to a concrete list, explicit approval.
2. **Gather remaining inputs** — PFX path, password via `PFX_PWD` env var (never argv), friendly name.
3. **PFX validation** (gate) — chain check + SAN coverage + validity via portable openssl script.
4. **Discovery** — Resource Graph queries enumerate hostnames, bindings, ASP SKUs, cert clutter.
5. **Plan presentation** (gate) — categorized table, explicit approval before any write.
6. **Pilot** — one app, full sequence, pause for review.
7. **Bulk execution** — same sequence per app, separate tool calls per step, stop-on-first-failure, explicit post-bind rollback path.
8. **Inline cleanup** — delete prior cert from each webspace with sibling-binding pre-check.
9. **Final verification** — re-run Resource Graph queries, repeat chain probe on a sample, write redacted markdown work record.

### Platform support

The chain-check ships in two equivalent forms:

- `check_pfx.sh` — bash + openssl, for macOS / Linux / WSL / Git Bash.
- `check_pfx.ps1` — PowerShell 5.1+ / 7+, for Windows or cross-platform. Uses .NET's native cert handling, no openssl dependency.

Both scripts read the PFX password from the `PFX_PWD` environment variable, exit with the same codes (0=good, 1=chain-less, 2=parse error, 3=other validation failure), and produce equivalent diagnostic output. Operator picks whichever shell they're comfortable in.

### Known Issues

- Operator must run from a workstation. There is no fallback path that uses Azure Key Vault or any other in-cloud mechanism.
- The "one step at a time" rule is binding on the AI executor — a future Claude that decides to write a loop "because the operator approved the plan and this is just 20 iterations of a verified pattern" will be violating the skill's invariants. Hard-rule language is present but not externally enforced.
- `check_pfx.ps1` smoke-tested on macOS PowerShell 7; Windows native PowerShell 5.1/7 are expected to work but not yet validated on hardware.

## co-dwerker v0.3.5

### What's New

**Local app verification is now actually enforced.** In v0.3.4 the post-implementation Step 5a ("Local App Testing") had soft-skip language: if it couldn't detect a runnable app, if a port was busy, or if env vars were missing, it would silently move on and the agent could open a PR without ever booting the application. v0.3.5 makes Step 5a a real phase gate — the only ways past it are a clean local boot+diff, an explicit user-confirmed skip with a recorded reason, or a one-time "this repo has no runnable app" decision that gets cached for future sessions.

The step is renamed to **Local App Verification** to make the intent clear.

**Auto-remediation first, then ask.** When a blocker shows up (port conflict, missing env var, missing tool), the agent tries safe local fixes before interrupting you: it kills stale processes it itself spawned earlier in the session, sources `.env.example` / `local.settings.json.example` values when they're obviously safe defaults (literal `"changeme"`, empty strings, framework dev-defaults), and prefers `.env.local` / `local.settings.json` files already on disk over template defaults. Variables whose names suggest real credentials (`*_SECRET`, `*_KEY`, `*_TOKEN`, `*_PASSWORD`) are never auto-populated — the agent escalates instead. Missing tools (`func`, `dotnet`, `node`) are never auto-installed; the agent escalates with the install command from your `CLAUDE.md`.

**When the agent has to ask, you get three clear options.** "Fix it and retry" (pause-and-resume), "Skip with a documented reason" (your one-line reason gets recorded in the PR's test plan so reviewers see exactly what was skipped and why), or "Cancel the session" (exit cleanly to fix outside the workflow).

**New warnings block by default, but you can dismiss them.** Previously new warnings were informational-only. They now block, but with a per-warning prompt: "Treat as regression / Dismiss for this PR with a reason / Dismiss permanently for this repo." Permanent dismissals get appended to `.co-dwerker.json` so the same warning won't ask again. Identical warnings that repeated N times during the idle window are grouped into one prompt with an `× N` count.

**Step 5a idle watch is now 90 seconds** (was 30s), matching the Step 1b baseline exactly so the diff is symmetric.

**No-app-detected is now surfaced**, not silently skipped. The first time you run `/co-dwerker:work` in a library/CLI repo, you'll get a one-time prompt: "no runnable app" (cached), "provide a custom run command" (cached), or "use a command just this once" (not cached). Future sessions skip the prompt.

### Behavior Changes

- Phase 3 Step 5a is now phase-gating. The Step Tracking GATE enforcement in `commands/work.md` blocks Step 6 (Changelog) until Step 5a reaches one of three valid completion states.
- A new reference file `plugins/co-dwerker/references/local-app-verification.md` owns the post-impl verification logic (parallel to v0.3.4's `references/baseline-localapp.md` for pre-impl).
- New `.co-dwerker.json` keys: `local_app_command` (custom command), `local_app_skip` (no-app flag), `dismissed_warnings` (array). `commands/exit.md` preserves these on session-end merge.
- New `.co-dwerker.state.json` `last_session` keys: `local_app_pids` (for stale-process recognition), `local_app_skip_reason` (one-line skip reason).
- PR descriptions created by Step 7 now include a "Local app verification" line in the test plan when relevant (skipped with reason, passed with dismissed warnings, or N/A because the repo has no runnable app).
- The frontmatter `description:` of `/co-dwerker:work` now advertises the enforced verification phase so triggering accounts for the possibility that the workflow pauses to ask about env/port/tool blockers.

### Known Issues

- The auto-remediation port-conflict pass only kills PIDs co-dwerker itself recorded in `local_app_pids` during the current session. If you ran a stray `func start` or `uvicorn` in another terminal that's holding the port, the agent will surface it rather than guess.
- The credential-name allowlist for env-var auto-sourcing is heuristic (`*_SECRET` / `*_KEY` / `*_TOKEN` / `*_PASSWORD` / `*_CONNECTION_STRING`). Names outside this pattern that happen to be credentials may be auto-sourced from templates. Verify your `.env.example` doesn't contain real values you wouldn't want copied into a local `.env`.
- Per-warning dismissal can be tedious if your run produces dozens of distinct new warnings. The grouping-by-normalized-form helps, but a session with high warning churn will see many prompts. Consider dismissing common known-noise warnings permanently early so they stop showing up.
- The 15-minute cumulative cap is shared across all detected apps in the verification run. Slow-booting `.NET` cold-MSBuild stacks may eat into the cap.

### Upgrade Notes

- No migration required. Existing `.co-dwerker.json` and `.co-dwerker.state.json` files continue to work; the new keys are added as they become relevant.
- Repos that previously silently skipped Step 5a (no runnable app) will get the one-time no-app-detected prompt on the next `/co-dwerker:work` run. Picking "No runnable app" caches the decision permanently.

---

## co-dwerker v0.3.4

### What's New

**Pre-existing app errors no longer get blamed on you.** Before any coding starts, `/co-dwerker:work` now also boots your application locally and captures which errors and warnings were already present on the unmodified branch — extending the test-baseline idea from v0.3.3 to local app behavior. After implementation, the local-app testing step compares the new run against that baseline, so it can tell regressions (caused by this work) from pre-existing issues (already broken).

Detection covers Azure Functions, .NET, Python web frameworks (Flask, Django, FastAPI, uvicorn, gunicorn), Node.js apps with `npm start`, and Docker Compose. Your repo's `CLAUDE.md` can override the detected command if you have a custom way to run locally.

The baseline watches the app for 90 seconds after it boots so background timers, scheduled functions, and queue consumers have time to surface their own errors. Log lines are normalized before diffing (timestamps, UUIDs, PIDs stripped) so a per-request ID doesn't show up as a "new" error every time.

**Cleaner skill organization.** As part of this release, the detailed instructions for both baseline steps (Test Baseline from v0.3.3 and the new Local App Baseline) moved out of the main `work.md` skill file into reference files (`references/baseline-tests.md` and `references/baseline-localapp.md`). This makes `work.md` less likely to overwhelm the LLM agent reading it, reducing the risk of phase-by-phase steps getting skipped amidst surrounding context.

### Behavior Changes

- Phase 3 (Execute) now has a Step 1b Baseline Local App between Step 1 Baseline Tests and Step 2 Plan.
- One workflow gate: if the unmodified branch can't boot the app (port conflict, missing config, crash), Step 1b stops and asks you to fix-and-retry / skip-baseline / cancel. This is intentional — without a successful boot there is nothing meaningful to compare against later. The test baseline still uses capture-and-continue (pre-existing test failures don't gate); only the local-app boot failure does.
- A new file `.co-dwerker.baseline-localapp.json` is written to the repo root during Phase 3 and removed in Phase 5 cleanup. It is added to `.git/info/exclude` automatically so intermediate commits don't pick it up.
- The detection list in the existing Local App Testing step (Step 5a) is unchanged, but Step 5a's reporting is now baseline-aware.

### Known Issues

- 15-minute cumulative cap across all detected apps. Slow boots (e.g., .NET with cold MSBuild) may eat into the cap. The gate behavior surfaces this clearly when it happens.
- The boot-failure gate is sensitive to local environment state. If your workflow assumes the app won't boot locally (e.g., the app requires Azure-only services), use the "skip baseline for this session" option from the gate.
- Normalization regex strips port numbers in URLs. If your app emits error messages where the specific port is load-bearing, the diff may treat semantically-different lines as equivalent. Raw lines are still preserved in the schema for manual inspection.

---

## co-dwerker v0.3.3

### What's New

**Pre-existing failing tests no longer get blamed on you.** Before any coding starts, `/co-dwerker:work` now runs all of your repo's tests and linters and captures a baseline -- which tests were already broken before this work began. After implementation, the verification step compares the new test run against that baseline so it can tell regressions (caused by this work) apart from pre-existing failures (already broken, not your problem this PR). Pre-existing failures are reported but don't block the workflow; new regressions still must be fixed before proceeding.

Detection covers Python (`uv run pytest`), Node (`npm test`), .NET (`dotnet test`), PowerShell (`Invoke-Pester`), and Go (`go test ./...`). The repo's `CLAUDE.md` is checked first for explicit commands; manifests are fallback. If no tests are detected, the step skips quietly.

### Behavior Changes

- Phase 3 (Execute) now starts with Step 1 Baseline Tests. Existing steps renumbered to 2-8 (Plan, Isolate, Implement, Verify, Local App Testing as 5a, Changelog, Create PR, Review).
- A new file `.co-dwerker.baseline-tests.json` is written to the repo root during Phase 3. It is automatically removed during Phase 5 cleanup, so it should not appear in commits. If you see it in your working tree, you can safely delete it.
- The verification step now distinguishes pre-existing failures from regressions in its output.

### Known Issues

- Baseline runs are capped at 10 minutes of cumulative wall-clock time; very large test suites may not capture every test before the timeout.
- The baseline file is added to `.git/info/exclude` automatically so intermediate commits don't pick it up, but if you've already committed one from an earlier version, you'll need to remove it manually.

---

## agent-eval-updates v0.1.0 — 2026-04-24

### What's New

**New plugin.** `agent-eval-updates` joins the marketplace as the third plugin (after `flywheel` and `co-dwerker`). It encapsulates the full end-to-end tuning iteration for BTC Azure Function Agents — the same workflow that's been iterated on through four rounds of real-world use against `ticket_prioritizer` and `ticket_reviewer` in the `btc_agent_evals` project.

**High-autonomy design.** The skill runs most of the work — CosmosDB queries, git archaeology, pre-fix artifact filtering, prompt-vs-code analysis, worktree setup, local soak testing, PR opening, cleanup — without asking for input. The user is consulted at exactly four gates: which agents to tune this round, whether the proposed fix set looks right, approval to start coding, and approval to merge + clean up.

**Prompt-vs-code analysis baked in.** Every failure pattern gets categorized as `{prompt | code | both}` with a cross-check against the repo's recent changelog to avoid re-fixing already-solved issues. The skill ships with a catalog of common failure patterns from prior rounds and heuristics for which language in an evaluator comment maps to which fix type.

**Disciplined code PR flow.** When a round includes changes to `BTC-Python-Agents` (not just prompt edits), the skill follows the full superpowers-driven flow: brainstorming → writing-plans → test-driven-development → executing-plans → verification-before-completion → `pr-review-toolkit:review-pr` loop → **final lint + test gate** before handing the PR to the user. The final gate re-runs `ruff check`, `black --check`, and `pytest` even after the review loop reports clean, specifically to catch drift from small post-review edits.

**BTC-Python-Agents architectural invariants.** The plugin's reference file carries the non-negotiable rules from the BTC-Python-Agents repo's own CLAUDE.md: handler-vs-agent separation (business logic only in `btc_agents/`), CosmosDB RU optimization (two writes max, `logger.info()` for progress), never mutate production code to make tests pass, agent factory/registry for new agents.

**Expected CHANGELOG conflict is intentional.** Per-agent branches result in conflicts in `CHANGELOG.md` and `RELEASE_NOTES.md` when the second PR in a repo merges. This is accepted friction — resolve at merge time by keeping both sections. The per-agent split enables per-agent revert and audit.

### Known Issues / Notes

- Depends on **superpowers**, **pr-review-toolkit**, and **commit-commands** being installed for the full flow. `episodic-memory` integration is optional.
- CosmosDB access requires the user to be logged in with `az` on a subscription that can reach `btc-ai-cosmosdb` (currently `BTC - Sponsored - 6000 annual`).
- Initial release. Will iterate based on feedback from real Round 5+ use.

---

## co-dwerker v0.3.2

### What's New

**Steps don't get skipped anymore.** The workflow now uses task-list checkpoints to track progress through each phase. Before any GATE (user approval point), the agent verifies that every step in the current phase is completed. If something was missed, it goes back and finishes it before asking for your approval.

**PR review is its own command.** The review, fix-findings, board-update, and user-approval steps that used to be buried at the end of Phase 3 are now a standalone `/co-dwerker:pr-review` command. This forces a fresh load of focused instructions right after the context-heavy implementation work, preventing the exact scenario where steps 7-8 were skipped. You can also invoke `/co-dwerker:pr-review` directly on any PR.

### Behavior Changes

- Phase 3 now has 7 steps (Plan through Create PR) plus a delegation to `/co-dwerker:pr-review`, down from 12 steps + a GATE.
- All phases now create task-list items for their steps, making progress visible in the Claude Code task list.
- GATEs enforce completion of all prior steps before presenting approval questions.

### Known Issues

- `work.md` is ~678 lines (still above the 500-line skill guideline, but improved from ~695 in v0.3.1). The Step Tracking section added ~10 lines while Phase 3 extraction removed ~27.
- The `REPO_OWNER_NAME` derivation only supports GitHub.com remotes (not GitHub Enterprise or other hosts).

---

## co-dwerker v0.3.1

### What's New

**Works from multi-repo workspaces.** When you launch `/co-dwerker:work` from a directory that contains multiple git repos as subdirectories (like a project root with separate Frontend and Functions repos), the plugin now discovers those repos automatically and lets you pick which one to work on. Your last session's repo is highlighted as the default for quick selection. If only one repo is found, it's used automatically.

**Local app testing during execution.** After unit tests and linting pass, the work workflow now attempts to run your application locally to catch runtime issues. It detects Azure Functions (via `host.json`), Azure App Services and web apps (.NET, Python, Node.js), and other common app types. Results are reported but won't block the workflow -- you decide whether to fix local testing issues before creating the PR.

**Cleaner home directory.** The global state file has moved from `~/.co-dwerker-last-repo.json` to `~/.claude/co-dwerker-last-repo.json`. The old file is read as a fallback and cleaned up automatically on next exit.

### Behavior Changes

- Repo detection now has 6 cases instead of 4, with new handling for workspace roots containing multiple git repos.
- The verification phase now includes a local app testing step (Step 4a) between automated tests and changelog creation.
- `/co-dwerker:exit` writes the global state file to `~/.claude/` and deletes the legacy file in `~/` if present.

### Known Issues

- `work.md` is now ~695 lines (above the 500-line skill guideline, up from ~626 in v0.3.0) due to the expanded repo detection and local testing sections. May benefit from extraction to a reference file in a future version.
- The `REPO_OWNER_NAME` derivation only supports GitHub.com remotes (not GitHub Enterprise or other hosts).

---

## co-dwerker v0.3.0

### What's New

**Always uses the best model.** co-dwerker now recommends switching to Opus at the start of every session and ensures all subagent dispatches use the most capable model. Haiku is never used; Sonnet is the minimum fallback.

**Create docs independently.** The new `/co-dwerker:docs` command lets you generate companion documentation for any PR or Issue at any time -- not just as part of the full workflow. When run standalone, it asks what PR or Issue to document. When called from the work workflow, it automatically picks up the current context.

**Works from any directory.** You no longer need to be inside the target repo when launching `/co-dwerker:work`. If the current directory is a different repo or not a repo at all, the plugin checks your last session state for the repo path, offers to navigate there automatically, or asks you to provide the path.

### Behavior Changes

- Phase 4 (Docs) in the work workflow now delegates to `/co-dwerker:docs` instead of having inline logic.
- The state file now includes `repo_local_path` (the absolute path to the repo on disk). This is saved automatically by `/co-dwerker:exit`.

### Known Issues

- `work.md` is ~626 lines (still above the 500-line skill guideline, improved from 654). Phase 4 extraction saved lines but the new repo detection section added some back. Further extraction may help in future versions.
- The `REPO_OWNER_NAME` derivation only supports GitHub.com remotes (not GitHub Enterprise or other hosts).

---

## co-dwerker v0.2.0

### What's New

**Work any GitHub repo, not just ones with project boards.** The new `/co-dwerker:work` command now asks whether you want to work in **repo mode** (just GitHub Issues) or **project mode** (GitHub Projects board). Your choice is remembered per folder so you only pick once.

**Create issues on the fly.** Use `/co-dwerker:new-issue` at any time to create a GitHub Issue. During brainstorm and execution phases, the plugin also proactively asks if newly discovered bugs or tasks should be filed as issues. In project mode, new issues are automatically added to the board with your chosen priority and status.

**Priority labels everywhere.** In repo mode, issues are sorted by P0-P3 priority labels (created automatically if missing). In project mode, priority labels are also applied to issues to keep everything in sync.

### Behavior Changes

- `/co-dwerker:work-bellwether-project` is deprecated -- use `/co-dwerker:work` instead (the old command shows a redirect).
- The standup format differs by mode: project mode shows the board view, repo mode shows issues grouped by priority labels and milestones.
- Board update steps (In Progress, In Review, Done) are skipped entirely in repo mode.
- The plugin now validates that the repo is GitHub-hosted before starting.

### Bug Fixes

- Fixed: Creating project board fields (Status, Priority) now properly populates the dropdown option values.
- Fixed: Priority labels are now applied in both repo and project mode when creating issues.
- Fixed: Upgrading from v0.1.0 state files no longer silently assumes project mode -- you'll be asked to choose.

### Known Issues

- `work.md` is 654 lines (above the 500-line skill guideline). The setup section has been extracted to a reference file but the core workflow phases are inherently long. May benefit from further extraction in a future version.
- The `REPO_OWNER_NAME` derivation only supports GitHub.com remotes (not GitHub Enterprise or other hosts).

## co-dwerker v0.1.0

Initial release with structured daily development workflow, GitHub Projects integration, and 6-layer session persistence.
