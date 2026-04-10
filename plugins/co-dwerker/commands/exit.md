---
description: Wind down and save the current work session -- persist state, update project board, save memories, write summary. Use when done for the day, wrapping up, stopping work, or ending a session.
---
# Co-Dwerker: Exit

Gracefully wind down a co-dwerker work session. This skill persists state across **every** available memory and documentation system so the next session can reconstruct full context regardless of how it starts.

**Persistence layers written to:**
1. Local state file (`.co-dwerker.state.json`)
2. GitHub Project board
3. Superpowers auto-memory (`~/.claude/projects/.../memory/`)
4. Claude built-in memories (project, feedback, reference types)
5. Project status files (CLAUDE.md, project_state.md, `.co-dwerker.json`)
6. Episodic memory (full session history)

## Environment

```bash
TODAY=$(date +%Y-%m-%d)
STATE_FILE=".co-dwerker.state.json"
CONFIG_FILE=".co-dwerker.json"
GLOBAL_STATE_FILE="$HOME/.claude/co-dwerker-last-repo.json"
GLOBAL_STATE_FILE_LEGACY="$HOME/.co-dwerker-last-repo.json"
REPO_REMOTE=$(git remote get-url origin 2>/dev/null)
REPO_OWNER_NAME=$(echo "$REPO_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
# Assumes HTTPS or git@github.com SSH remote format
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
# Match the auto-memory directory convention used by Claude Code.
# The exact path varies by platform — check for existing memory files first:
#   ls ~/.claude/projects/*/memory/MEMORY.md
# Use the matching directory. If none exists, derive from project root.
MEMORY_DIR="$HOME/.claude/projects/$(echo $PROJECT_ROOT | sed 's|[/:\\]|-|g')/memory"
```

## Model Preference

When dispatching subagents via the `Agent` tool during exit, always set `model: "opus"`. Never use `model: "haiku"`. Use `"sonnet"` as minimum fallback.

## Process

### 1. Gather Session Summary

Before persisting anything, collect the facts about this session:

- **Issues completed:** Which issues moved to "Done" this session
- **Issues created:** New issues created via `/co-dwerker:new-issue` this session
- **Issues in progress:** Current active issue, what phase it's in
- **PRs created:** PR numbers and URLs from this session
- **PRs merged:** Which PRs were merged this session
- **Branches active:** Feature branches with uncommitted or unpushed work
- **Worktrees open:** Any git worktrees created this session
- **Decisions made:** Non-obvious choices that affect future work
- **Blockers found:** Anything that blocked progress or needs follow-up

### 2. Save Local State (.co-dwerker.state.json)

Write the state file to the project root:

```json
{
  "work_mode": "repo or project",
  "repo_owner_name": "owner/repo",
  "repo_local_path": "/absolute/path/to/repo",
  "github_project_number": null or number,
  "github_project_title": null or "title string",
  "planned_issues": [<remaining issue numbers>],
  "last_session": {
    "date": "$TODAY",
    "completed_issues": [<issue numbers completed today>],
    "current_issue": <active issue number or null>,
    "current_phase": "<phase name or null>",
    "branch": "<active branch name or null>",
    "worktree": "<worktree path or null>",
    "prs_created": [<PR numbers>],
    "prs_merged": [<PR numbers>],
    "issues_created": [<issue numbers created this session>]
  }
}
```

Notes:
- `work_mode` persists across sessions so the user doesn't have to re-select each time
- `repo_owner_name` is stored for display in the resume prompt
- `repo_local_path` is the absolute path to the repo on disk (from `git rev-parse --show-toplevel`). This enables `/co-dwerker:work` to navigate to the repo when launched from a different directory.
- `github_project_number` and `github_project_title` are null when `work_mode == "repo"`
- `issues_created` tracks issues created via `/co-dwerker:new-issue` during this session

This file should be gitignored. If `.gitignore` doesn't already exclude it, add the entry:

```bash
echo ".co-dwerker.state.json" >> .gitignore
```

Also write a **global last-repo file** at `$GLOBAL_STATE_FILE` (`~/.claude/co-dwerker-last-repo.json`) so that `/co-dwerker:work` can find the repo when launched from a non-project directory:

```bash
mkdir -p "$HOME/.claude"
```

```json
{
  "repo_owner_name": "owner/repo",
  "repo_local_path": "/absolute/path/to/repo"
}
```

This file is intentionally minimal -- it only stores enough to navigate back to the project. The full session state remains in the project-local `$STATE_FILE`.

**Legacy cleanup:** If a file exists at `$GLOBAL_STATE_FILE_LEGACY` (`~/.co-dwerker-last-repo.json`, the pre-v0.3.1 location), delete it after writing the new file:
```bash
rm -f "$HOME/.co-dwerker-last-repo.json"
```

### 3. Update GitHub Project Board (project mode only)

**Skip this step if `work_mode == "repo"`.**

If `work_mode == "project"`, verify board items reflect current reality:

```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --limit 100
```

For each issue worked on this session:
- Completed issues --> confirm status is "Done"
- Issues mid-work --> confirm status is "In Progress" (not accidentally reset)
- Issues with PRs ready --> confirm status is "In Review"

Do not change statuses that are already correct. Only fix discrepancies.

### 4. Update Superpowers Auto-Memory

Check if a project memory file exists for this repo:

```bash
ls "$MEMORY_DIR"/*.md 2>/dev/null
```

**If memory files exist for this project**, update the relevant ones with current state:
- Active branches, current issue, what phase we're in
- Any patterns or conventions learned during the session
- Update MEMORY.md index if descriptions changed

**If no memory files exist yet**, create a new project memory file:

Write to `$MEMORY_DIR/<project-name>.md`:

```markdown
---
name: <Project Name> Status
description: Current development state for <project> — active issues, branches, and next steps
type: project
---

## Current State (as of $TODAY)

- **Active issue:** #<number> — <title> (Phase: <phase>)
- **Branch:** <branch-name>
- **PRs open:** #<number> (<status>)
- **Next up:** #<number>, #<number>

## Session History
- $TODAY: <1-2 sentence summary of what was accomplished>

**Why:** Enables session continuity across Claude Code conversations.
**How to apply:** Read this at session start to resume context.
```

Update the `MEMORY.md` index file if a new memory file was created.

### 5. Save Session Learnings to Auto-Memory

Save non-obvious learnings as markdown files in the auto-memory directory (`$MEMORY_DIR`). These files persist across all future Claude Code sessions for this project.

Use the `Write` tool to create files in `$MEMORY_DIR/` with YAML frontmatter containing `name`, `description`, and `type` fields. Update `$MEMORY_DIR/MEMORY.md` if adding new files.

**Project memories** (type: project, save if applicable):
- Current work state: active issue, branch, phase
- Important deadlines or blockers discovered
- Dependencies between issues that aren't obvious from the board

**Feedback memories** (type: feedback, save if applicable):
- Workflow adjustments the user requested during this session
- Approaches that worked well or poorly
- Tool/skill usage patterns to repeat or avoid

**Reference memories** (type: reference, save if applicable):
- External resources discovered (URLs, dashboards, docs)
- API endpoints or service locations learned

Only save memories that will be useful in future sessions. Don't save things derivable from code, git history, or existing documentation.

Also state key learnings explicitly in the conversation text so they are captured by episodic memory (Step 7).

### 6. Update Project Status Files

**`.co-dwerker.json`** — Create if it doesn't exist (first session), update if changed:

```json
{
  "docs_repo": "<org/repo or null>",
  "docs_path": "<path within docs repo or null>"
}
```

If this is the first session and no docs repo is known, ask the user:

> "Does this project have a companion documentation repo? If so, what's the org/repo and the path within it for this project's docs?"

If the user says no or skips, write `null` for both fields.

**`CLAUDE.md`** — If project conventions changed during the session (new test commands, lint config, etc.), update the relevant sections.

**`project_state.md`** (if the project uses one) — Update with current status, open PRs, active branches.

### 7. Save Full Session to Episodic Memory

The episodic-memory plugin automatically captures conversation history. To ensure this session is searchable and useful in future sessions, explicitly state a structured session summary in the conversation before ending. This makes the session discoverable via `episodic-memory:search-conversations`.

Format the summary as a clear text block in conversation (not a file write) so the episodic memory system indexes it:

The session record should include:
- **Project:** repository name and project board title
- **Date:** today's date
- **Issues worked:** numbers, titles, and outcomes (completed, in-progress, blocked)
- **PRs:** numbers, URLs, and status (created, merged, pending review)
- **Key decisions:** design choices, approach selections, trade-offs made
- **Blockers:** anything that prevented progress, with context
- **What's next:** the recommended starting point for the next session
- **Patterns/learnings:** anything surprising or non-obvious discovered

### 8. Git Hygiene Check

Review the state of the local repository:

```bash
git status --short
git branch --list
git worktree list
git stash list
```

**If there's uncommitted work:**
- If changes are meaningful and safe to commit, suggest a WIP commit:
  > "There are uncommitted changes on branch `$BRANCH`. Want me to create a WIP commit?"
- If changes are scratch/exploratory, just note them

**If there are stale branches:**
- List branches that aren't associated with open PRs
- Don't delete anything — just note them for the user

**If there are open worktrees:**
- List them with their branch associations
- Note which ones are from this session vs. prior sessions

### 9. Present Exit Summary

Format a clear summary for the user:

> **Session Summary -- $TODAY** ($WORK_MODE mode on $REPO_OWNER_NAME)
>
> **Completed:**
> - Issue #$N: $TITLE (PR #$PR merged)
>
> **Created:**
> - Issue #$N: $TITLE (priority / status)
>
> **In Progress:**
> - Issue #$N: $TITLE -- Phase $PHASE (branch `$BRANCH`)
>   - Next step: <what to do when resuming>
>
> **Tomorrow's Starting Point:**
> - Resume Issue #$N from Phase $PHASE
> - Then tackle: #$A, #$B
>
> **Open Items:**
> - <any blockers, pending reviews, or follow-ups>

This summary should be concise but complete enough that someone reading it tomorrow can immediately understand where things stand.
