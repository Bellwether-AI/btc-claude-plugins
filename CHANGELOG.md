# Changelog

All notable changes to the btc-claude-plugins repository.

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
