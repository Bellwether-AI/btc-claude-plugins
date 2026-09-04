# Changelog

All notable changes to the btc-claude-plugins repository.

## [azure-appservice-cert-rollout v0.1.0] - 2026-06-25

### Post-review revisions (during initial PR review cycle)
- **Added `check_pfx.ps1`** — PowerShell port of the chain-check script for Windows operators. Uses .NET's native `X509Certificate2Collection` (no openssl dependency) and the SAN parser handles both Windows (`DNS Name=...`) and macOS/Linux (`DNS:...`) format variants. Works with PowerShell 5.1+ on Windows and PowerShell 7+ cross-platform. Smoke-tested on macOS against known-good and known-chain-less PFXes.
- **Fixed PFX_PWD env-var leak in SKILL.md Step 2 example** — was showing `PFX_PWD='...' bash script.sh` (still visible to `ps`) rather than the correct two-step pattern (export in a separate command, then call the script which inherits from env).
- **Step 1 now documents env-var setup for all three shells** — bash/zsh, PowerShell, and cmd.exe — so a Windows operator using PowerShell knows to use `$env:PFX_PWD = '...'` rather than `export`.
- **KQL `endswith '<suffix>'` tightened to `endswith '.<suffix>'`** with a literal leading dot, in every discovery and verification query. Without the dot, `endswith 'example.com'` would also match `notexample.com`. Matching anchor added in the openssl SAN coverage check in both chain-check scripts for the same reason.
- **`--first 1000` added to every in-body Resource Graph query** in `resource-graph-queries.md`, not just the "tip" section. Avoids silent result truncation on tenants with 200+ App Services.
- **Terminology drift resolved** — "prior thumbprint" / "prior cert" → "old thumbprint" / "old cert" throughout the skill, matching the `<old-thumbprint>` variable name used in `per-app-procedure.md`.
- **Step 6 table row for Step A** now describes the actual validation step (tenant context still matches Step 0 approval) rather than the misleading "(no failure mode)".
- **Managed Cert pre-check query** in `managed-certs.md` no longer claims to be "Query 2 from resource-graph-queries.md" (Query 2 is suffix-based; the pre-check is thumbprint-based).
- **Cross-platform tested** — both `check_pfx.sh` (bash on macOS) and `check_pfx.ps1` (PowerShell 7 on macOS) verified against a chain-bundled PFX (exit 0, full chain walked) and a synthesized chain-less PFX (exit 1, FAIL message).

### Added
- **New plugin `azure-appservice-cert-rollout`** at `plugins/azure-appservice-cert-rollout/`. Ships one skill — `azure-appservice-cert-rollout` — codifying a production-safe BYOC TLS certificate rollout workflow for Azure App Services across one or many subscriptions in a tenant. Built from two real-world rollout sessions (May 2026 initial cross-subscription deploy; June 2026 chain-fix follow-up after a leaf-only PFX was discovered to have been uploaded). Designed for the MSP / multi-client case.
- **Three hard invariants encoded into the skill**: (1) PFX chain validation BEFORE upload via portable openssl script, (2) tenant + subscription scope confirmation gate BEFORE any write, (3) manual one-step-at-a-time execution — separate tool calls per step, no batch loops, stop-on-first-failure.
- **9-step workflow**: tenant scope confirmation → input gathering (with `PFX_PWD` env var pattern to keep password off argv and out of shell history) → PFX validation gate → Resource Graph discovery → plan presentation gate → pilot → bulk execution with explicit post-bind chain-probe rollback path → inline old-cert cleanup with sibling-binding safety pre-check → final Resource Graph verification sweep → redacted markdown work record.
- **`check_pfx.sh`** — portable PFX chain validation script. Reads password from `PFX_PWD` env var via `openssl -passin env:PFX_PWD` (never argv). Uses awk for per-certificate splitting to avoid GNU-only `csplit` flags that silently fail on macOS BSD. Walks the chain validating each child issuer matches its parent subject. Exits 1 if chain is leaf-only (the silent-chain-less-upload failure mode), 2 if PFX can't be parsed, 3 on other validation failures, 0 on success. Optional second arg checks SAN coverage against an expected hostname suffix.
- **`resource-graph-queries.md`** — four KQL discovery queries plus two final-verification queries. Uses `mv-expand` + `endswith` patterns (rather than `tostring()` + `contains`) to avoid substring-match false positives on short domain suffixes. Includes the subscription-list resolution guidance with explicit operator-eyeball approval before any name-prefix match is trusted.
- **`per-app-procedure.md`** — five-step per-app sequence (account-set → upload → bind → openssl chain probe → delete-old) with the explicit post-bind chain-probe failure rollback procedure (re-bind to prior thumbprint, do not run the delete), pre-delete safety check (query for any sibling app in the same webspace still bound to the old thumbprint before deleting), and the canonical "stop on first failure" invariant.
- **`managed-certs.md`** — recognizing App Service Managed Certificates (which `az webapp config ssl delete` cannot touch despite Resource Graph showing them) and the required pre-check before any `az resource delete` against a Managed Cert.
- **`work-record-template.md`** — structure for the Step 9 markdown work record, including required PFX-password redaction in any echoed commands and a plain-text-paste-friendly summary block at the end.
- **README + plugin.json** registered in `.claude-plugin/marketplace.json`.

### Notes
- Skill went through a 3-reviewer cycle (design / discoverability, technical correctness, operational safety) with all critical and high-severity findings addressed before initial release. Notable issues caught and fixed during review: GNU-only csplit flags in the chain-check script (would have silently turned the entire chain check into a no-op on the operator's macOS workstation); PFX password leaking via argv into shell history; tenant-scope confirmation present as suggestion rather than gate; the "one step at a time" rule worded as persuasive prose rather than a hard guardrail.

## [co-dwerker v0.3.5] - 2026-05-21

### Changed
- **Phase 3 Step 5a renamed and enforced**: "Local App Testing" is now "Local App Verification" and is an explicitly phase-gating step. The previous language ("Do NOT block on this step generally") that allowed silent bail-outs on missing env vars, port conflicts, or undetected apps has been removed. Step 5a now has exactly three valid completion states: clean diff against the Step 1b baseline, an `AskUserQuestion`-confirmed skip with a recorded reason, or a `.co-dwerker.json`-cached "no runnable app" decision.
- **Step 5a idle watch extended from 30s to 90s**: matches `references/baseline-localapp.md` exactly, so the diff between Step 1b baseline and Step 5a verification compares apples to apples. The agentic flow tolerates the extra wall-clock time.
- **Step Tracking section** in `commands/work.md` now calls out Step 5a as phase-gating with an explicit rule that Step 6 (Changelog) cannot start while Step 5a is `in_progress`.
- **Step 7 (Create PR)** now reads `local_app_skip_reason` and the in-memory per-PR dismissed-warning reasons from Step 5a and embeds them in the PR description's test plan so reviewers see what was skipped or dismissed and why.
- **Skill frontmatter description** updated to advertise the enforced verification phase so the LLM agent's triggering accounts for the new user-gate behavior.

### Added
- **`plugins/co-dwerker/references/local-app-verification.md`**: NEW reference file (parallel to `references/baseline-localapp.md` but for post-implementation verification). Contains: detection-cascade reuse, auto-remediation pre-flight (stale-PID port-conflict resolution scoped to co-dwerker-spawned PIDs, env-var sourcing from `.env.example` / `local.settings.json.example` templates with credential-name safeguards, missing-tool escalation without auto-install, stale-build-artifact cleanup), boot/idle/log capture (mirrors baseline exactly), blocker gate via `AskUserQuestion` with three standardized options (fix-and-retry / skip-with-reason / cancel), no-app-detected gate that writes a cached decision to `.co-dwerker.json`, baseline diff rules including the new per-warning dismissal flow, schema for the new state and config fields, PR-description integration rules, edge cases.
- **Per-warning dismissal flow**: New warnings now block by default but can be dismissed per-PR (recorded in PR test plan) or dismissed permanently for the repo (appended to `.co-dwerker.json`'s `dismissed_warnings: []` array and filtered from future baseline+verification diffs). Identical normalized warnings are grouped into a single prompt with an `× N` count rather than asking the user N times.
- **`.co-dwerker.json` schema additions**: `local_app_command` (custom run command from no-app-detected gate option 2), `local_app_skip` (boolean from no-app-detected gate option 1), `dismissed_warnings` (string array of normalized warnings the user permanently dismissed). `commands/exit.md` updated to preserve these on session-end merge rather than overwriting.
- **`.co-dwerker.state.json last_session` additions**: `local_app_pids` (array of PIDs spawned during Step 1b and Step 5a so the next remediation pass can recognize stale processes co-dwerker itself owns; processes owned externally are never killed), `local_app_skip_reason` (one-line user reason from the blocker-gate skip option). `commands/exit.md` updated to persist these fields.

### Why
- The previous Step 5a was effectively opt-out — silent skip on no-detect, missing env, or port conflict. The user reported that this defeated the purpose of the automated agentic testing phase, where the agent should exhaust every locally available means of validating its work before opening a PR. v0.3.5 makes the step opt-out only when the user explicitly opts out (and the reason is recorded for the PR reviewer).
- The 30s idle watch in old Step 5a was inconsistent with the 90s in Step 1b, breaking the diff symmetry. Same-window observation matters: a slow-firing background timer caught in the baseline at second 70 would never reappear in a 30s post-impl window, falsely showing as "resolved".

## [co-dwerker v0.3.4] - 2026-05-15

### Added
- **Phase 3 Step 1b — Baseline Local App**: New step in the Execute phase of `/co-dwerker:work`. Runs after Step 1 Baseline Tests and before Plan. Detects runnable apps (Azure Functions via `host.json`, .NET via `Program.cs`/`Startup.cs`, Python web via `app.py`/`manage.py` and framework signals, Node via `package.json` start script, Docker Compose via `docker-compose.yml`, plus `CLAUDE.md` override). Boots the app in the current working directory and captures: boot status (7-value enum including `started`, `failed_to_start`, `timeout`, `crashed_during_idle`, `preflight_failed`), boot duration, ready-signal match, HTTP probe results, log errors and warnings observed during a 90-second idle watch window. Results are written to `.co-dwerker.baseline-localapp.json`.
- **Log normalization pipeline**: Before storing log entries in the baseline, raw log lines are normalized (strip ANSI codes, ISO 8601 and bracket timestamps, UUIDs, long hex strings, PIDs in common formats, port numbers in URLs, memory addresses, whitespace collapse). Both raw and normalized forms are kept in the schema so the user-facing summary shows real text but the Step 5a diff matches on stable normalized forms.
- **Multi-line entry capture**: Python tracebacks (`Traceback (most recent call last):` + indented frames), .NET unhandled exceptions (`Unhandled exception` / `System.X.Exception:` + stack frames), and .NET ASP.NET error blocks are captured as single multi-line entries rather than as fragmented lines.
- **Step 5a baseline diff**: Local App Testing now reads `.co-dwerker.baseline-localapp.json` and classifies post-implementation issues as pre-existing (don't block), new errors (block as regressions), new warnings (informational), resolved (positive side effect), with separate boot-status comparison treating `started`/`started_no_signal` as equivalent healthy and `failed_to_start`/`timeout`/`crashed_during_idle`/`preflight_failed` as equivalent boot-failure.
- **`AskUserQuestion` gate on baseline boot failure**: This is the one place v0.3.4 diverges from v0.3.3's capture-and-continue rule. If the unmodified branch cannot boot the app cleanly, Step 1b stops with a 3-option prompt (fix-environment-and-retry / skip-baseline-for-this-session / cancel-session) because without a successful boot there is nothing meaningful to compare against later.
- **Cumulative 15-minute cap** across all detected apps. After cap, remaining apps are marked `timeout` and the gate behavior applies.
- **`plugins/co-dwerker/references/baseline-localapp.md`**: NEW reference file with the full detail for Step 1b (detection, preflight, boot, idle watch, log capture, normalization, schema, gate, edge cases).

### Changed
- **Skill-file organization (work.md slimmed)**: Per skill-creator's <500-line guideline and explicit user preference, the detailed instructions for BOTH baseline steps (Step 1 and Step 1b) are extracted to `plugins/co-dwerker/references/baseline-tests.md` (NEW — retroactive extraction of v0.3.3 Step 1 content) and `plugins/co-dwerker/references/baseline-localapp.md` (NEW). `commands/work.md` keeps brief Step 1 / Step 1b stubs that point to these references, plus the downstream diff treatment in Step 5 / Step 5a inline where it is used. Net result: `work.md` lands at 785 lines despite adding a major new feature (was 806 in v0.3.3 with only the test baseline; without extraction it would have grown to ~950+).
- **Phase 3 Step 3 Isolate**: the copy-to-worktree block now handles BOTH `.co-dwerker.baseline-tests.json` and `.co-dwerker.baseline-localapp.json` via a single loop. Same `.git/info/exclude` propagation rules apply to both files.
- **Phase 5 Step 6 Clean Up**: extended to `rm -f` `.co-dwerker.baseline-localapp.json` from both worktree path and main repo root.
- **Frontmatter description**: `commands/work.md` description now hints at the new boot-failure gate behavior so the LLM agent's triggering accounts for the possibility that `/co-dwerker:work` may pause to ask for environment fixes.
- **Reference self-containedness**: `references/baseline-localapp.md` now includes the file-write + `.git/info/exclude` propagation block directly (previously the write step lived only in the `work.md` stub, which broke the symmetry with `baseline-tests.md` and meant the reference could not be executed in isolation).
- **Schema field correctness in Step 5a diff**: post-implementation log-entry diff now correctly references the schema's separate `log_errors[]` and `log_warnings[]` arrays (the initial commit had used `kind: error` / `kind: warning` filter language, but no `kind` field exists on log entries — only on test-baseline suites).
- **Gate option 2 wording**: now consistent across `work.md` Step 1b and `references/baseline-localapp.md` — both reflect that a `boot_status: "skipped"` baseline file is written so Step 5a knows the user opted out.
- **Step 1b gate-effect routing**: 3-way branching presented as a clear bulleted list (was previously a dense paragraph that could obscure individual branches under context pressure).
- **Step 5 truncation warning**: tightened wording to make explicit that the truncation flag is not a license to skip regression fixes — the agent must verify a "new failure" was pre-existing before treating the truncation warning as a carve-out.

## [co-dwerker v0.3.3] - 2026-05-15

### Added
- **Phase 3 Step 1 -- Baseline Tests**: New first step in the Execute phase of `/co-dwerker:work`. Before any planning or coding, the workflow now runs all available test suites and lint commands in the current working directory and captures the result to `.co-dwerker.baseline-tests.json`. Detects test commands from the repo's `CLAUDE.md` first, falling back to manifest heuristics for Python (`pyproject.toml` → `uv run pytest`), Node (`package.json` → `npm test`), .NET (`*.csproj` → `dotnet test`), PowerShell (`*.Tests.ps1` → `Invoke-Pester`), and Go (`go.mod` → `go test ./...`). Captures per-suite totals, exit code, duration, and the first 50 failing test identifiers. Capture-and-continue semantics — failures are reported but never gate the workflow.
- **Baseline diff in Step 5 Verify**: The verification step now reads `.co-dwerker.baseline-tests.json` (if present) and classifies current failures as pre-existing (don't block), regressions caused by this work (must fix), or newly-passing tests (positive side effect). Pre-existing failures alone no longer block the workflow.
- **Baseline file propagation in Step 3 Isolate**: When the worktree is created, the baseline JSON is copied into the worktree root so verification reads it from the same working directory the implementation happens in.
- **Baseline cleanup in Phase 5 Step 6**: `rm -f .co-dwerker.baseline-tests.json` added to the clean-up commands so the per-issue artifact does not leak between sessions.
- **Local git exclude entry**: Step 1 appends `.co-dwerker.baseline-tests.json` to `.git/info/exclude` (idempotently) so intermediate commits from `superpowers:executing-plans` do not include the baseline file. Step 3 (Isolate) repeats the same exclude write inside the worktree's gitdir (`$WORKTREE_PATH/.git/info/exclude`) after copying the file in. The repo's tracked `.gitignore` is not modified.
- **Schema fields**: `kind` (`"test"` or `"lint"`) and `failing_tests_truncated` (boolean) added to per-suite schema. `kind` lets Step 5 Verify treat linters differently (no baseline diff, only exit-code check). `failing_tests_truncated` warns when the 50-entry truncation could cause false-positive regressions.
- **Skip-case downstream behavior**: Step 5 Verify now explicitly handles the case where no baseline file exists -- all current test failures are treated as regressions and must be fixed. Without this rule the agent's behavior was ambiguous when Step 1 found no tests.
- **Timeout semantics**: The 10-minute cap is explicitly cumulative across all suites (not per-suite); a single suite still running when the cap is reached is terminated with `status: "timeout"` and `null` totals.

### Changed
- **Phase 3 step numbering**: Plan/Isolate/Implement/Verify/Local-App/Changelog/Create-PR/Review renumbered from 1-7 to 2-8 (with Local App Testing now Step 5a) to accommodate the new Step 1 Baseline Tests at the top of the phase.
- **Stale cross-reference fixed**: Phase 2 Step 3 used to say `$ITEM_ID` is reused in "Phase 3 (step 9) and Phase 5 (step 5)" -- corrected to "Phase 3 (Step 8 PR Review, via `/co-dwerker:pr-review`) and Phase 5 (Step 5 Board Update)".

## [agent-eval-updates v0.1.0] - 2026-04-24

### Added
- **New plugin `agent-eval-updates`**: high-autonomy tuning iteration for BTC Azure Function Agents in the `btc_agent_evals` project. Ships a single skill (`agent-eval-updates`) plus five reference files and one helper script.
- **`plugins/agent-eval-updates/skills/agent-eval-updates/SKILL.md`** (503 lines): main workflow covering 10 phases (0–9) with 4 user gates (scope, proposal, coding approval, wrap-up). 12 critical invariants including the pre-fix artifact filter, per-agent branch convention, prompt-vs-code analysis requirement, and the final lint+test gate after the PR review loop.
- **`references/cosmos-query.md`**: `query_evals.py` usage, CosmosDB document schema, the critical distinction between `_ts` (when agent ran) and `content.ratingDetails.timestamp` (when human rated).
- **`references/local-testing.md`**: scratch prompt overlay pattern (avoids blob uploads), azurite + func startup with nvm semantics, webhook replay crafting with `member_id` rewrite for safety, debounce timing (120s default), `TICKET_*_RESOURCE_FILTER=mlax` semantics.
- **`references/triage-patterns.md`**: catalog of failure patterns from prior rounds with prompt-vs-code heuristics for each category.
- **`references/pr-workflow.md`**: per-agent branch naming (`tuning/<agent>-YYYY-MM-DD`), CHANGELOG/RELEASE_NOTES conflict resolution recipe (keep both sections), GH issue + PR body templates.
- **`references/btc-python-agents-coding.md`**: BTC-Python-Agents architectural invariants (handler/agent separation, CosmosDB RU rules, testing-never-mutates-production) + the full superpowers-skill-driven code-change flow (steps A–K) with required `pr-review-toolkit:review-pr` loop and final lint + test gate.
- **`scripts/filter_prefix_artifacts.py`**: helper that takes an eval JSON + list of prior fix-PR numbers across both repos, fetches `mergedAt` via `gh pr view`, filters items by `_ts`, and emits post-fix-only JSON plus a summary. Avoids manually cross-referencing merge times each round.

### Changed
- **`.claude-plugin/marketplace.json`**: added `agent-eval-updates` entry pointing at `./plugins/agent-eval-updates` at version `0.1.0`.

## [co-dwerker v0.3.2] - 2026-04-10

### Added
- **Step Tracking section**: New top-level instruction in `work.md` requiring task creation (via `TaskCreate`) for every numbered step in each phase. GATEs now enforce that all prior steps are completed before proceeding. Prevents step-skipping when implementation work consumes large amounts of context.
- **`/co-dwerker:pr-review` command**: Extracted PR review, finding resolution, board update, and user approval from Phase 3 into a standalone command (`commands/pr-review.md`). Can be invoked standalone for any PR, or is called by `/co-dwerker:work` Phase 3 after PR creation. Fresh skill invocation ensures review instructions are loaded into context right when they're needed.

### Changed
- **Phase 3 (Execute) restructured**: Steps 7-10 + GATE replaced with a single delegation to `/co-dwerker:pr-review`. Phase 3 now has 7 steps (Plan through Create PR, plus the PR review delegation), down from 10 numbered steps + step 4a + GATE. This is the fix for the step-skipping bug.
- **work.md line count**: Reduced from ~695 to ~678 lines. The Step Tracking section added ~10 lines, but Phase 3 extraction removed ~27 lines.

### Fixed
- **Phase 3 steps skipped after PR creation**: The PR review (step 7) and address-findings (step 8) steps were being skipped because the agent lost track of its position after the context-heavy implementation work in steps 1-6. Fixed by both the task-list checkpoint enforcement and the extraction of post-PR steps into a freshly-loaded command.

## [co-dwerker v0.3.1] - 2026-04-10

### Added
- **Multi-repo workspace scanning**: When launched from a directory containing multiple git repos as subdirectories (e.g., a project root with Frontend and Functions repos), `/co-dwerker:work` now scans immediate child directories for git repos with GitHub remotes and presents them as selectable options. Previously this fell through to an unhelpful "provide the path" prompt.
- **Single-repo shortcut**: When exactly one sub-repo is found, it is used directly with a confirmation message instead of presenting a list of one.
- **Local app testing step (Phase 3, Step 4a)**: After unit tests and linting pass, `/co-dwerker:work` now attempts to run the application locally. Detects Azure Functions (`host.json` → `func start`), Azure App Services / web apps (.NET `dotnet run`, Python `flask run`/`uvicorn`, Node.js `npm start`), and other web apps (`docker-compose.yml`, `Makefile`). Reports results but does not block the workflow if local testing fails.

### Changed
- **Global state file location**: Moved `~/.co-dwerker-last-repo.json` to `~/.claude/co-dwerker-last-repo.json` to keep the home directory clean. Reads fall back to the legacy location for backward compatibility; writes always go to the new location.
- **Legacy cleanup**: `/co-dwerker:exit` now deletes the old `~/.co-dwerker-last-repo.json` after writing the new location.
- **Repo detection expanded from 4 cases to 6**: New Cases C (sub-repos found, saved repo matches one) and D (sub-repos found, no saved match) handle the multi-repo workspace scenario. Original Cases A, B, E, F are unchanged.
- **Environment variables**: Added `GLOBAL_STATE_FILE` and `GLOBAL_STATE_FILE_LEGACY` to both `work.md` and `exit.md` for explicit path references.

### Fixed
- **Multi-repo workspace launch failure**: Launching `/co-dwerker:work` from a workspace root containing multiple repos (e.g., `policy_conductor/` with `PolicyConductor-Frontend-AppService/` and `PolicyConductorFunctions/`) no longer fails with an unhelpful prompt. The skill discovers sub-repos and lets the user pick, with the last-session repo highlighted as default.

## [co-dwerker v0.3.0] - 2026-04-09

### Added
- **`/co-dwerker:docs` command**: Standalone companion documentation creation. Can be invoked independently for any PR or Issue, or is called by the work workflow's Phase 4. Asks the user what to document when run standalone, auto-detects context when called from the workflow.
- **Model preference enforcement**: All commands now recommend Opus model on session start and instruct subagent dispatches to always use `model: "opus"`. Haiku is explicitly prohibited; Sonnet is the minimum fallback.
- **`repo_local_path` in state file**: New field stores the absolute path to the repo on disk, enabling session resume when launching from a different directory.
- **Resilient repo detection in `/co-dwerker:work`**: New Repo Detection subsection in the Environment block handles non-repo CWDs gracefully -- checks state file for previous repo path, offers to navigate there automatically, or asks the user to provide the path.

### Changed
- **Phase 4 (Docs) delegated**: `work.md` Phase 4 is now a thin delegation to the standalone `/co-dwerker:docs` command, reducing work.md by ~60 lines.
- **State file schema**: Added `repo_local_path` field (absolute path to repo on disk, from `git rev-parse --show-toplevel`).
- **Plugin description**: Updated plugin.json and marketplace.json to v0.3.0 with mentions of standalone docs and Opus preference.
- **README**: Added docs command to commands table, added Model Preference section, updated workflow diagram with standalone docs footnote, added `repo_local_path` to state file schema docs.

### Fixed
- **Non-repo CWD launch failure**: `/co-dwerker:work` no longer fails when launched from a directory that is not a git repo or is a different repo than intended. It checks saved state, offers navigation, and asks for user confirmation.
- **work.md line count**: Reduced from 654 to ~626 lines. Phase 4 extraction saved ~60 lines, but the new repo detection section added ~30 lines back. Still closer to the 500-line guideline.

## [co-dwerker v0.2.0] - 2026-04-06

### Added
- **Repo mode**: New work mode that operates directly from GitHub Issues with P0-P3 priority labels, no project board required. Users choose repo or project mode on first run, and the choice is remembered per folder.
- **`/co-dwerker:work` command**: Unified entry point replacing `/co-dwerker:work-bellwether-project`. Supports both repo and project modes with conditional standup format, board updates, and label management.
- **`/co-dwerker:new-issue` command**: Standalone issue creation at any time. Asks for priority in both modes, applies priority labels, and adds to project board with status selection in project mode.
- **Inline issue creation**: During brainstorm (Phase 2) and execute (Phase 3) phases, discovered bugs/tasks are prompted for issue creation with optional queue addition.
- **Priority labels auto-creation**: Repo mode standup checks for P0-P3 labels on first run and creates any that are missing.
- **`issues_created` tracking**: New field in state file tracks issues created during each session.
- **`references/setup-project-board.md`**: Extracted project board and label setup instructions to a reference file, reducing work.md from 745 to 654 lines for better context window efficiency.
- **GitHub hosting guard**: Environment section now validates that the git remote is on github.com before proceeding.
- **Error handling guidance**: All command files now include guidance to report `gh` CLI failures to the user rather than silently continuing.

### Changed
- **State file schema**: Added `work_mode`, `repo_owner_name` (top-level), and `issues_created` (in last_session). Made `github_project_number` and `github_project_title` nullable for repo mode.
- **Frontmatter descriptions**: Improved all command descriptions to be more "pushy" for reliable skill triggering (includes natural trigger phrases like "start work", "resume", "standup", "done for the day").
- **Plugin description**: Updated plugin.json and marketplace.json to v0.2.0 with broader, trigger-friendly descriptions.
- **Board updates conditional**: All `gh project item-edit` calls in work.md and exit.md are now wrapped in project-mode conditionals -- skipped entirely in repo mode.
- **Memory system clarity**: exit.md Step 5 now clearly describes the auto-memory file mechanism rather than conflating it with implicit conversation memory.
- **Docs phase staging**: Changed `git add -A` to specific file staging in the docs PR creation step.

### Fixed
- **`gh project field-create` missing option values**: Field creation now uses GraphQL `updateProjectV2Field` mutation to populate dropdown option values (Status: Backlog/Ready/In Progress/In Review/Done, Priority: P0-P3) after field creation.
- **`ITEM_ID` extraction fragility**: Added retry logic with 2-second delay when querying for newly added project board items.
- **`--label` comma syntax**: Changed to separate `--label` flags per gh CLI documentation.
- **Priority labels not applied in repo mode**: Extracted priority selection to run before issue creation in both modes, ensuring labels are always applied.
- **v0.1.0 state migration**: Missing `work_mode` field now triggers first-time mode selection instead of silently defaulting to project mode.
- **marketplace.json version sync**: Marketplace manifest now matches plugin.json version (0.2.0).
- **`.co-dwerker.state.json` gitignore**: Added to repo `.gitignore` proactively instead of relying on exit skill to add it at runtime.

### Deprecated
- **`/co-dwerker:work-bellwether-project`**: Replaced with `/co-dwerker:work`. Old command now shows a redirect message.

## [co-dwerker v0.1.0] - 2026-04-01

### Added
- Initial co-dwerker plugin with structured daily development workflow
- `/co-dwerker:work-bellwether-project` command with 8-phase issue-to-merge workflow
- `/co-dwerker:exit` command with 6-layer session state persistence
- GitHub Projects board integration with Status and Priority fields
- Session resume detection from local state, episodic memory, and git state
