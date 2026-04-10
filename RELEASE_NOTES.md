# Release Notes

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
