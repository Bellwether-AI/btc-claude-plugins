# Changelog

All notable changes to the btc-claude-plugins repository.

## [co-dwerker v0.3.2] - 2026-04-10

### Added
- **Step Tracking section**: New top-level instruction in `work.md` requiring task creation (via `TaskCreate`) for every numbered step in each phase. GATEs now enforce that all prior steps are completed before proceeding. Prevents step-skipping when implementation work consumes large amounts of context.
- **`/co-dwerker:pr-review` command**: Extracted PR review, finding resolution, board update, and user approval from Phase 3 into a standalone command (`commands/pr-review.md`). Can be invoked standalone for any PR, or is called by `/co-dwerker:work` Phase 3 after PR creation. Fresh skill invocation ensures review instructions are loaded into context right when they're needed.

### Changed
- **Phase 3 (Execute) restructured**: Steps 7-10 + GATE replaced with a single delegation to `/co-dwerker:pr-review`. Phase 3 now has 7 steps (Plan through Create PR) plus the delegation, down from 12 steps + GATE. This is the fix for the step-skipping bug.
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
