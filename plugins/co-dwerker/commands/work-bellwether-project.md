---
description: Start a structured work session — standup, brainstorm, execute, docs, close
---
# Co-Dwerker: Work Bellwether Project

Run a structured daily development session on a Bellwether project. This skill orchestrates a full issue-to-merge workflow by composing existing superpowers and pr-review-toolkit skills with GitHub Projects board management.

**Workflow:** Resume Check → Project Select → Standup → Brainstorm → Execute → Docs → Close → Next

**Required skills (must be installed separately):**
- `superpowers:brainstorming`
- `superpowers:writing-plans`
- `superpowers:executing-plans` or `superpowers:subagent-driven-development`
- `superpowers:verification-before-completion`
- `superpowers:finishing-a-development-branch`
- `pr-review-toolkit:review-pr`
- `commit-commands:commit`
- `episodic-memory:search-conversations`

## Environment

```bash
TODAY=$(date +%Y-%m-%d)
STATE_FILE=".co-dwerker.state.json"
CONFIG_FILE=".co-dwerker.json"
REPO_REMOTE=$(git remote get-url origin 2>/dev/null)
REPO_OWNER_NAME=$(echo "$REPO_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
```

---

## Resume Check

Before starting fresh, check for prior session state.

### 1. Read Local State

Use `Read` to check if `$STATE_FILE` exists in the project root. If it does, parse the JSON for:
- `last_session.date` — when the last session was
- `last_session.current_issue` — issue number in progress
- `last_session.current_phase` — which phase was active
- `last_session.branch` — branch name
- `planned_issues` — the remaining work queue
- `github_project_number` — the project board used

### 2. Search Episodic Memory

Invoke `episodic-memory:search-conversations` to find recent sessions tagged with this project. Look for:
- What was accomplished last session
- Any blockers or decisions that carry forward
- Context about the current issue if mid-work

### 3. Check Git State

```bash
git branch --list | head -20
git status --short
git worktree list
```

Look for:
- Uncommitted changes on a feature branch
- Open worktrees from prior sessions
- Branches that match issue numbers from the state file

### 4. Present Resume Option

If mid-work state is detected, present to the user:

> "Last session ($DATE) we were working on Issue #$NUMBER — Phase $PHASE (branch `$BRANCH`). Resume where we left off, or start fresh with standup?"

Use `AskUserQuestion` to get the user's choice:
- **Resume** → Jump directly to the phase recorded in state
- **Fresh start** → Proceed to Phase 0

If no prior state exists, proceed directly to Phase 0.

---

## Phase 0: Project Select

Every session confirms which GitHub Project board to work from.

### 1. List Available Projects

```bash
gh project list --owner "$REPO_OWNER_NAME" --format json --limit 20
```

If the org has no projects, try listing for the repo owner:
```bash
gh project list --format json --limit 20
```

### 2. Offer Default

If `$STATE_FILE` has a `github_project_number`, highlight it:

> "Last session used Project #$NUMBER — '$TITLE'. Use the same project?"

### 3. User Confirms

Use `AskUserQuestion` to confirm or pick a different project. Store the selection:

```bash
PROJECT_NUMBER=<selected>
PROJECT_TITLE="<selected title>"
```

### 4. Load Project Fields

```bash
gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json
```

Look for the required fields:
- **Status** — single select with values: Backlog, Ready, In Progress, In Review, Done
- **Priority** — single select with values: P0-Critical, P1-High, P2-Medium, P3-Low

If fields are missing, offer to create them:

> "The project board is missing the '$FIELD' field. Want me to create it?"

Store field IDs and option IDs for use throughout the session:
```
STATUS_FIELD_ID=<id>
PRIORITY_FIELD_ID=<id>
STATUS_OPTIONS={backlog: <id>, ready: <id>, in_progress: <id>, in_review: <id>, done: <id>}
PRIORITY_OPTIONS={p0: <id>, p1: <id>, p2: <id>, p3: <id>}
```

---

## Phase 1: Standup

Read the project board and present an organized status report.

### 1. Fetch Board Items

```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --limit 100
```

Parse each item for: title, status, priority, issue number, assignee, linked PR.

### 2. Determine "Last Session" Boundary

Use `last_session.date` from `$STATE_FILE` if available. Otherwise use `$TODAY` minus 1 day. Items moved to "Done" after this date count as "shipped since last session."

### 3. Present Standup Report

Format the board state into these categories:

**What shipped since last session:**
- List items in "Done" status that changed since the last session date
- Include PR links if available

**What's in progress:**
- Items in "In Progress" or "In Review"
- Note current branch/PR status

**What's next by priority:**
- Items in "Ready" status, sorted: P0 > P1 > P2 > P3
- Within same priority, sort by issue number (lower = older = higher precedence)

**Blockers:**
- Items with labels containing "blocked" or "waiting"
- Issues with unresolved dependency references in the body

**Recommendation:**
- Propose 2-4 issues for today's work based on priority
- Include more than can realistically be completed so there's always a clear "what's next"
- Explain why each is recommended (priority, dependency chain, quick win, etc.)

### 4. GATE: User Picks Work Queue

Use `AskUserQuestion`:

> "Here's my recommendation for today: #$A (P1), #$B (P1), #$C (P2). Which issues do you want to work on today, and in what order?"

The user's response defines the ordered work queue. The first item becomes the **active issue**.

---

## Phase 2: Brainstorm

Collaborative design for the active issue.

### 1. Load Issue Context

```bash
gh issue view $ISSUE_NUMBER --repo "$REPO_OWNER_NAME" --json title,body,comments,labels,assignees,milestone
```

Also read:
- Any source files referenced in the issue body
- Linked issues or PRs mentioned in comments
- Related test files if the issue is a bug fix

### 2. Invoke Brainstorming

Use the `Skill` tool to invoke `superpowers:brainstorming`.

The brainstorming skill will:
- Explore the problem space
- Ask clarifying questions
- Propose approaches
- Present a design for approval
- Save a design doc to `docs/superpowers/specs/$TODAY-<topic>-design.md`

Follow the brainstorming skill's complete flow. Do not shortcut it.

### 3. Update Board Status

After design is approved, update the project board item to "In Progress":

```bash
# Find the item ID for this issue
ITEM_ID=$(gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json | jq -r '.items[] | select(.content.number == '$ISSUE_NUMBER') | .id')

# Update status to "In Progress"
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_IN_PROGRESS_ID
```

### GATE: Design Approval

The brainstorming skill handles its own approval gate. Once the user approves the design doc, proceed to Phase 3.

---

## Phase 3: Execute

Autonomous implementation. After design approval, the following happens without user intervention until the PR is ready.

### 1. Plan

Use the `Skill` tool to invoke `superpowers:writing-plans`.

The writing-plans skill will create a detailed implementation plan from the design doc. Follow its full flow.

### 2. Isolate

Use the `Skill` tool to invoke `superpowers:using-git-worktrees` to create an isolated worktree for this work.

Record the worktree path and branch name for the state file.

### 3. Implement

Use the `Skill` tool to invoke `superpowers:executing-plans` (or `superpowers:subagent-driven-development` if the plan has independent tasks).

Follow the execution skill's full flow including TDD cycles and commits.

### 4. Verify

Use the `Skill` tool to invoke `superpowers:verification-before-completion`.

The verification skill will:
- Run the full test suite (per project's CLAUDE.md — typically `uv run pytest`)
- Run linters (typically `uv run ruff check . && uv run black --check .`)
- Verify no regressions
- Confirm all success criteria from the design doc are met

If verification fails, fix the issues and re-verify. Do not proceed until clean.

### 5. Changelog

Update `CHANGELOG.md` and `RELEASE_NOTES.md` per the project's CLAUDE.md conventions:
- CHANGELOG.md: line-by-line technical changes with reasons
- RELEASE_NOTES.md: human-readable feature/fix descriptions

Commit changelog updates separately from implementation code.

### 6. Create PR

```bash
gh pr create --title "<concise title>" --body "$(cat <<'EOF'
## Summary
<bullet points describing what changed and why>

Closes #$ISSUE_NUMBER

## Test plan
- [ ] All existing tests pass
- [ ] New tests cover the changes
- [ ] Linting passes (ruff + black)

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### 7. Review

Use the `Skill` tool to invoke `pr-review-toolkit:review-pr` on the new PR.

### 8. Address Review Findings

If the review identifies issues:
1. Fix each finding
2. Re-run verification (tests + lint)
3. Commit fixes
4. Push to the PR branch

Repeat until the review is clean.

### 9. Update Board

Update the project board item status to "In Review":

```bash
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_IN_REVIEW_ID
```

### GATE: User Approval

Use `AskUserQuestion`:

> "PR #$PR_NUMBER is ready for your review: $PR_URL
>
> Changes: <1-2 sentence summary>
>
> All tests pass, linting clean, review findings addressed. Ready for you to confirm."

Wait for user approval before proceeding to Phase 4.

---

## Phase 4: Docs

Update user-facing documentation in the companion docs repo. This phase is autonomous after user approves the code PR.

### 1. Check Docs Config

Read `$CONFIG_FILE` (`.co-dwerker.json`) for `docs_repo` and `docs_path`.

If no config file exists or `docs_repo` is null/missing, skip this phase entirely and proceed to Phase 5.

### 2. Locate or Clone Docs Repo

Check if the docs repo is already cloned locally:

```bash
# Check common sibling locations
ls -d "../$(basename $DOCS_REPO)" 2>/dev/null
ls -d "../../$(basename $DOCS_REPO)" 2>/dev/null
```

If not found, clone it:

```bash
gh repo clone "$DOCS_REPO" "../$(basename $DOCS_REPO)"
```

Create a feature branch in the docs repo:

```bash
cd "../$(basename $DOCS_REPO)"
git checkout -b "docs/$ISSUE_NUMBER-<short-description>"
```

### 3. Analyze Doc Impact

Read the code PR diff to determine what documentation needs updating:

- **New feature** → create a new doc file in `$DOCS_PATH`
- **Changed behavior** → update existing docs that reference the changed component
- **Bug fix** → update known issues section if applicable
- **No user-facing impact** → skip with a note

### 4. Create or Update Docs

Write documentation in the configured `$DOCS_PATH`. Follow the existing documentation style in that directory.

### 5. Create Docs PR

```bash
cd "../$(basename $DOCS_REPO)"
git add -A
git commit -m "docs: update documentation for $REPO_OWNER_NAME#$ISSUE_NUMBER"
git push -u origin "docs/$ISSUE_NUMBER-<short-description>"
gh pr create --title "docs: <description>" --body "$(cat <<'EOF'
## Summary
Documentation update for $REPO_OWNER_NAME#$ISSUE_NUMBER

<bullet points describing doc changes>

## Related
- Code PR: $REPO_OWNER_NAME#$PR_NUMBER
EOF
)"
```

### 6. Cross-Reference

Back in the code repo, update CHANGELOG.md to reference the docs PR.

### GATE: User Approval

Use `AskUserQuestion`:

> "Docs PR created: $DOCS_PR_URL
>
> Changes: <summary of doc updates>
>
> Ready for your review."

Wait for user approval before proceeding to Phase 5.

---

## Phase 5: Close

Merge approved PRs, verify CI, and clean up.

### 1. Merge Code PR

```bash
gh pr merge $PR_NUMBER --squash --delete-branch
```

### 2. Verify CI

```bash
# Wait for CI to complete (check up to 5 times with 30s intervals)
gh run list --branch main --limit 1 --json status,conclusion
```

If CI fails, alert the user immediately:

> "CI failed after merging PR #$PR_NUMBER. Run: $RUN_URL. This needs attention before continuing."

### 3. Merge Docs PR (if exists)

```bash
gh pr merge $DOCS_PR_NUMBER --repo "$DOCS_REPO" --squash --delete-branch
```

### 4. Close Issue

If the issue wasn't auto-closed by the PR merge:

```bash
gh issue close $ISSUE_NUMBER --repo "$REPO_OWNER_NAME" --reason completed
```

### 5. Update Board

Update the project board item status to "Done":

```bash
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_DONE_ID
```

### 6. Clean Up

```bash
# Delete local feature branch if it still exists
git branch -d "$BRANCH_NAME" 2>/dev/null

# Remove worktree if one was created
git worktree remove "$WORKTREE_PATH" 2>/dev/null

# Clean up docs repo clone if we created one
# (only if it was freshly cloned for this session)
```

---

## Phase 6: Next

Loop back or wrap up.

### 1. Show Updated Board

Run a quick board refresh:

```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --limit 100
```

Present a condensed view:
- Completed today: issue numbers and titles
- Remaining in queue: ordered list

### 2. Check Work Queue

If there are remaining issues in today's planned work queue:

> "Issue #$ISSUE_NUMBER ($TITLE) is next in the queue. Ready to start brainstorming?"

Use `AskUserQuestion` for confirmation. If confirmed, loop back to **Phase 2** with the next issue as the active issue.

### 3. Queue Empty

If all planned issues are done:

> "All planned issues for today are complete! You can:
> 1. Add another issue to work on
> 2. Run `/co-dwerker:exit` to wrap up the session"

### 4. User Options

At any point in the Next phase, the user can:
- Pick a new issue not in the original queue
- Re-prioritize remaining items
- Invoke `/co-dwerker:exit` to end the session

---

## GitHub Project Board Setup

On first run, if the project board is missing expected fields, offer to create them.

### Required Fields

| Field | Type | Options |
|-------|------|---------|
| Status | Single select | Backlog, Ready, In Progress, In Review, Done |
| Priority | Single select | P0-Critical, P1-High, P2-Medium, P3-Low |

### Optional Fields

These are used if present but not required:
- **Sprint** — iteration field for grouping work by time period
- **Agent** — single select for categorizing by agent/component
- **Docs PR** — text field for linking companion documentation PRs

### Creating Missing Fields

```bash
# Create Status field
gh project field-create $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --name "Status" --data-type "SINGLE_SELECT"

# Create Priority field
gh project field-create $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --name "Priority" --data-type "SINGLE_SELECT"
```

After creating fields, add the option values and store their IDs for the session.
