---
description: Wind down the current work session — save state across all memory systems, update docs, write summary
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
REPO_REMOTE=$(git remote get-url origin 2>/dev/null)
REPO_OWNER_NAME=$(echo "$REPO_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
MEMORY_DIR="$HOME/.claude/projects/$(echo $PROJECT_ROOT | sed 's|[/:\\]|-|g')/memory"
```

## Process

### 1. Gather Session Summary

Before persisting anything, collect the facts about this session:

- **Issues completed:** Which issues moved to "Done" this session
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
  "github_project_number": <number>,
  "github_project_title": "<title>",
  "planned_issues": [<remaining issue numbers>],
  "last_session": {
    "date": "$TODAY",
    "completed_issues": [<issue numbers completed today>],
    "current_issue": <active issue number or null>,
    "current_phase": "<phase name or null>",
    "branch": "<active branch name or null>",
    "worktree": "<worktree path or null>",
    "prs_created": [<PR numbers>],
    "prs_merged": [<PR numbers>]
  }
}
```

This file should be gitignored. If `.gitignore` doesn't already exclude it, add the entry:

```bash
echo ".co-dwerker.state.json" >> .gitignore
```

### 3. Update GitHub Project Board

Verify board items reflect current reality:

```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --limit 100
```

For each issue worked on this session:
- Completed issues → confirm status is "Done"
- Issues mid-work → confirm status is "In Progress" (not accidentally reset)
- Issues with PRs ready → confirm status is "In Review"

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

### 5. Update Claude Built-in Memories

Save non-obvious learnings to Claude's built-in memory system. These persist across ALL future Claude Code sessions, not just this project.

**Project memories** (save if applicable):
- Current work state: active issue, branch, phase
- Important deadlines or blockers discovered
- Dependencies between issues that aren't obvious from the board

**Feedback memories** (save if applicable):
- Workflow adjustments the user requested during this session
- Approaches that worked well or poorly
- Tool/skill usage patterns to repeat or avoid

**Reference memories** (save if applicable):
- External resources discovered (URLs, dashboards, docs)
- API endpoints or service locations learned

Only save memories that will be useful in future sessions. Don't save things derivable from code, git history, or existing documentation.

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

Invoke the `episodic-memory` plugin to record the full session. This is the richest context store and enables future sessions to search for specific decisions and outcomes.

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

> **Session Summary — $TODAY**
>
> **Completed:**
> - Issue #$N: $TITLE (PR #$PR merged)
>
> **In Progress:**
> - Issue #$N: $TITLE — Phase $PHASE (branch `$BRANCH`)
>   - Next step: <what to do when resuming>
>
> **Tomorrow's Starting Point:**
> - Resume Issue #$N from Phase $PHASE
> - Then tackle: #$A, #$B
>
> **Open Items:**
> - <any blockers, pending reviews, or follow-ups>

This summary should be concise but complete enough that someone reading it tomorrow can immediately understand where things stand.
