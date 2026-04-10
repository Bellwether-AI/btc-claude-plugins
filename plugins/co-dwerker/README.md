# co-dwerker

Structured daily development workflow plugin for Claude Code. Orchestrates a full issue-to-merge cycle with multi-layer session persistence. Supports two work modes:

- **Repo mode** -- work directly from GitHub Issues with priority labels (no project board required)
- **Project mode** -- work from a GitHub Projects board with Status and Priority fields

## Commands

| Command | Description |
|---------|-------------|
| `/co-dwerker:work` | Full workflow session -- mode select, standup, brainstorm, execute, docs, close, next |
| `/co-dwerker:docs` | Create or update companion documentation for a PR or Issue (standalone or from workflow) |
| `/co-dwerker:new-issue` | Create a GitHub Issue and optionally add it to the active project board |
| `/co-dwerker:exit` | Wind down the session -- save state across all memory systems |
| `/co-dwerker:work-bellwether-project` | *Deprecated* -- redirects to `/co-dwerker:work` |

## Work Modes

### Repo Mode

Works directly from GitHub Issues. No project board required.

- Priority is tracked via **GitHub labels**: P0-Critical, P1-High, P2-Medium, P3-Low
- Labels are created automatically on first run if missing
- Standup sorts issues by priority label, then milestone, then age
- Board update steps are skipped entirely

### Project Mode

Works from a GitHub Projects board (the original v0.1.0 behavior).

- Priority and status tracked via **project board fields**
- Board items are updated throughout the workflow (In Progress, In Review, Done)
- New issues created mid-session are added to the board with priority/status prompts

## Workflow

```
Resume Check --> Mode Select --> Project Select* --> Standup --> Brainstorm --> Execute --> Docs** --> Close --> Next
                                                       ^                                                     |
                                                       +------------------------ loop -----------------------+
```

*Project Select only runs in project mode.
**Docs can also be run standalone via `/co-dwerker:docs`.

1. **Resume Check** -- Detect prior session state, offer to resume or start fresh
2. **Mode Select** -- Choose repo mode or project mode (remembered per folder)
3. **Project Select** -- Confirm which GitHub Project board to work from (project mode only)
4. **Standup** -- Read issues/board, present status, recommend today's issues
5. **Brainstorm** -- Collaborative design for the active issue (invokes `superpowers:brainstorming`)
6. **Execute** -- Autonomous implementation: plan, isolate, implement, verify, changelog, PR, review
7. **Docs** -- Update companion documentation repo (if configured)
8. **Close** -- Merge PRs, verify CI, clean up branches
9. **Next** -- Loop to next issue, create new issues, or exit

## Issue Creation

New issues can be created at any time during a session:

- **Inline** -- During brainstorm or execution, when new bugs/tasks/sub-tasks are discovered
- **Standalone** -- Via `/co-dwerker:new-issue` at any point

In project mode, new issues are automatically added to the project board with user-selected priority and status. In both modes, priority labels are applied to the issue.

## Model Preference

co-dwerker is designed for the most capable model available. On session start, it recommends running `/model opus` if you're not already on it. All subagent dispatches via the Agent tool use `model: "opus"`. Haiku is never used.

## Prerequisites

These plugins/skills must be installed separately:

- **superpowers** -- `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:executing-plans` (or `superpowers:subagent-driven-development`), `superpowers:verification-before-completion`, `superpowers:using-git-worktrees`
- **pr-review-toolkit** -- `pr-review-toolkit:review-pr`
- **commit-commands** -- `commit-commands:commit`
- **episodic-memory** -- `episodic-memory:search-conversations`

## Per-Project Configuration

### `.co-dwerker.json` (committed to repo)

Created automatically by the exit skill on first run.

```json
{
  "docs_repo": "Org/RepoName",
  "docs_path": "path/to/docs"
}
```

- `docs_repo` -- GitHub org/repo for companion documentation. `null` if none.
- `docs_path` -- Path within docs repo for this project's docs. `null` if none.

### `.co-dwerker.state.json` (gitignored)

Managed automatically by the exit skill. Contains session state for resume detection.

```json
{
  "work_mode": "repo or project",
  "repo_owner_name": "owner/repo",
  "repo_local_path": "/absolute/path/to/repo",
  "github_project_number": null,
  "github_project_title": null,
  "planned_issues": [],
  "last_session": {
    "date": "2026-04-06",
    "completed_issues": [],
    "current_issue": null,
    "current_phase": null,
    "branch": null,
    "worktree": null,
    "prs_created": [],
    "prs_merged": [],
    "issues_created": []
  }
}
```

- `work_mode` persists across sessions (repo or project)
- `repo_owner_name` stored for display in resume prompt
- `repo_local_path` absolute path to repo on disk (enables launching from non-repo directories)
- `github_project_number` / `github_project_title` are null in repo mode
- `issues_created` tracks issues created via `/co-dwerker:new-issue`

## GitHub Project Board (project mode only)

The skill expects these fields on the project board (offers to create them on first run):

| Field | Type | Values |
|-------|------|--------|
| Status | Single select | Backlog, Ready, In Progress, In Review, Done |
| Priority | Single select | P0-Critical, P1-High, P2-Medium, P3-Low |

## GitHub Labels (repo mode)

The skill expects these priority labels (creates them on first run if missing):

| Label | Color | Description |
|-------|-------|-------------|
| P0-Critical | #B60205 | Critical priority |
| P1-High | #D93F0B | High priority |
| P2-Medium | #FBCA04 | Medium priority |
| P3-Low | #0E8A16 | Low priority |

## Installation

```bash
/install co-dwerker@btc-claude-plugins
```
