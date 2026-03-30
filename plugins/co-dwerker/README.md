# co-dwerker

Structured daily development workflow plugin for Claude Code. Orchestrates a full issue-to-merge cycle using GitHub Projects, superpowers skills, and multi-layer session persistence.

## Commands

| Command | Description |
|---------|-------------|
| `/co-dwerker:work-bellwether-project` | Start a work session — standup, brainstorm, execute, docs, close |
| `/co-dwerker:exit` | Wind down the session — save state across all memory systems |

## Workflow

```
Resume Check → Project Select → Standup → Brainstorm → Execute → Docs → Close → Next
                                  ↑                                              │
                                  └──────────────── loop ────────────────────────┘
```

1. **Resume Check** — Detect prior session state, offer to resume or start fresh
2. **Project Select** — Confirm which GitHub Project board to work from
3. **Standup** — Read the board, present status, recommend today's issues
4. **Brainstorm** — Collaborative design for the active issue (invokes `superpowers:brainstorming`)
5. **Execute** — Autonomous implementation: plan → isolate → implement → verify → PR → review
6. **Docs** — Update companion documentation repo (if configured)
7. **Close** — Merge PRs, verify CI, clean up branches
8. **Next** — Loop to next issue or exit

## Prerequisites

These plugins/skills must be installed separately:

- **superpowers** — brainstorming, writing-plans, executing-plans, verification, git worktrees
- **pr-review-toolkit** — automated PR review
- **commit-commands** — standardized commits
- **episodic-memory** — session history recall

## Per-Project Configuration

### `.co-dwerker.json` (committed to repo)

Created automatically by the exit skill on first run.

```json
{
  "docs_repo": "Org/RepoName",
  "docs_path": "path/to/docs"
}
```

- `docs_repo` — GitHub org/repo for companion documentation. `null` if none.
- `docs_path` — Path within docs repo for this project's docs. `null` if none.

### `.co-dwerker.state.json` (gitignored)

Managed automatically by the exit skill. Contains session state for resume detection.

## GitHub Project Board

The skill expects these fields on the project board (offers to create them on first run):

| Field | Type | Values |
|-------|------|--------|
| Status | Single select | Backlog, Ready, In Progress, In Review, Done |
| Priority | Single select | P0-Critical, P1-High, P2-Medium, P3-Low |

## Installation

```bash
/install co-dwerker@btc-claude-plugins
```
