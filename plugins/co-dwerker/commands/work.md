---
description: Start a structured work session -- standup, brainstorm, execute, docs, close
---
# Co-Dwerker: Work

Run a structured development session. This skill orchestrates a full issue-to-merge workflow by composing existing superpowers and pr-review-toolkit skills. Supports two work modes:

- **Repo mode** — work directly from GitHub Issues (no project board required)
- **Project mode** — work from a GitHub Projects board with status/priority tracking

The mode is remembered per project folder so you only choose once.

**Workflow:** Resume Check --> Mode Select --> Project Select (project mode only) --> Standup --> Brainstorm --> Execute --> Docs --> Close --> Next

**Required skills (must be installed separately):**
- `superpowers:brainstorming`
- `superpowers:writing-plans`
- `superpowers:executing-plans` or `superpowers:subagent-driven-development`
- `superpowers:verification-before-completion`
- `superpowers:using-git-worktrees`
- `pr-review-toolkit:review-pr`
- `commit-commands:commit`
- `episodic-memory:search-conversations`

## Environment

```bash
TODAY=$(date +%Y-%m-%d)
STATE_FILE=".co-dwerker.state.json"
CONFIG_FILE=".co-dwerker.json"
REPO_REMOTE=$(git remote get-url origin 2>/dev/null)
# Assumes HTTPS or git@github.com SSH remote format
REPO_OWNER_NAME=$(echo "$REPO_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
```

---

## Resume Check

Before starting fresh, check for prior session state.

### 1. Read Local State

Use `Read` to check if `$STATE_FILE` exists in the project root. If it does, parse the JSON for:
- `work_mode` — "repo" or "project" (default to "project" if missing for backward compat)
- `repo_owner_name` — the repo used last time (derive from git remote if missing)
- `github_project_number` — the project board used (null in repo mode)
- `github_project_title` — project board display name (null in repo mode)
- `planned_issues` — the remaining work queue
- `last_session.date` — when the last session was
- `last_session.current_issue` — issue number in progress
- `last_session.current_phase` — which phase was active
- `last_session.branch` — branch name
- `last_session.worktree` — worktree path (avoid creating duplicates)
- `last_session.completed_issues` — what was finished last time
- `last_session.prs_created` — PRs opened last session
- `last_session.prs_merged` — PRs merged last session
- `last_session.issues_created` — issues created last session

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

> "Last session ($DATE) you were working in **$WORK_MODE mode** on $REPO_OWNER_NAME.
> Active issue: #$NUMBER -- Phase $PHASE (branch `$BRANCH`).
> Resume where we left off, or start fresh with standup?"

Use `AskUserQuestion` to get the user's choice:
- **Resume** --> Jump directly to the phase recorded in state
- **Fresh start** --> Proceed to Phase 0a

If no prior state exists, proceed directly to Phase 0a.

---

## Phase 0a: Mode Selection

Choose how to work this repo.

### 1. Check State for Previous Mode

If `$STATE_FILE` has a `work_mode` value, offer to continue:

> "Last session used **$WORK_MODE mode**. Continue with the same mode?"
>
> - **Repo mode** -- work from GitHub Issues directly (no project board)
> - **Project mode** -- work from a GitHub Projects board with status/priority columns

### 2. First-Time Selection

If no state file exists or `work_mode` is missing, ask:

> "How do you want to work this repo?"
>
> - **Repo mode** -- GitHub Issues only. Priority via P0-P3 labels. No project board needed.
> - **Project mode** -- GitHub Projects board with Status and Priority fields.

Use `AskUserQuestion` to get the user's choice.

### 3. Store Mode

```
WORK_MODE=<selected: "repo" or "project">
```

If `WORK_MODE == "repo"`, skip Phase 0b and proceed directly to Phase 1.
If `WORK_MODE == "project"`, proceed to Phase 0b.

---

## Phase 0b: Project Select (project mode only)

This phase runs only when `WORK_MODE == "project"`.

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

> "Last session used Project #$NUMBER -- '$TITLE'. Use the same project?"

### 3. User Confirms

Use `AskUserQuestion` to confirm or pick a different project. Store the selection:

```bash
PROJECT_NUMBER=<selected>
PROJECT_TITLE="<selected title>"
```

### 4. Fetch Project Node ID

The `gh project item-edit` command requires the GraphQL node ID, not the project number. Fetch it now:

```bash
PROJECT_ID=$(gh project view $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --jq '.id')
```

Store `PROJECT_ID` for all board update operations throughout the session.

### 5. Load Project Fields

```bash
gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json
```

Look for the required fields:
- **Status** — single select with values: Backlog, Ready, In Progress, In Review, Done
- **Priority** — single select with values: P0-Critical, P1-High, P2-Medium, P3-Low

If fields are missing, offer to create them (see "GitHub Project Board Setup" section at the end).

Store field IDs and option IDs for use throughout the session:
```
STATUS_FIELD_ID=<id>
PRIORITY_FIELD_ID=<id>
STATUS_OPTIONS={backlog: <id>, ready: <id>, in_progress: <id>, in_review: <id>, done: <id>}
PRIORITY_OPTIONS={p0: <id>, p1: <id>, p2: <id>, p3: <id>}
```

---

## Phase 1: Standup

Read the current state and present an organized status report. The format depends on the work mode.

### Project Mode Standup

*Runs when `WORK_MODE == "project"`.*

#### 1. Fetch Board Items

```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --limit 100
```

Parse each item for: title, status, priority, issue number, assignee, linked PR.

#### 2. Determine "Last Session" Boundary

Use `last_session.date` from `$STATE_FILE` if available. Otherwise use `$TODAY` minus 1 day. Items moved to "Done" after this date count as "shipped since last session."

#### 3. Present Standup Report

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

### Repo Mode Standup

*Runs when `WORK_MODE == "repo"`.*

#### 1. Fetch Issues

```bash
# Recently closed issues (shipped since last session)
gh issue list --repo "$REPO_OWNER_NAME" --state closed --json number,title,closedAt,labels --limit 20

# Open issues assigned to current user
gh issue list --repo "$REPO_OWNER_NAME" --state open --assignee @me --json number,title,labels,milestone --limit 50

# All open issues
gh issue list --repo "$REPO_OWNER_NAME" --state open --json number,title,labels,milestone,assignees,createdAt --limit 50
```

#### 2. Present Standup Report

**What shipped since last session:**
- Issues closed after `last_session.date`
- Include linked PR if available

**What's in progress:**
- Open issues assigned to current user
- Cross-reference with `last_session.current_issue` and active branches

**What's next by priority:**
- Open issues with priority labels, sorted: P0-Critical > P1-High > P2-Medium > P3-Low
- Within same priority, sort by milestone due date (closest first), then issue number (oldest first)
- Issues without priority labels listed last

**Blockers:**
- Issues with "blocked" or "waiting" labels

### Recommendation (both modes)

- Propose 2-4 issues for today's work based on priority
- Include more than can realistically be completed so there's always a clear "what's next"
- Explain why each is recommended (priority, dependency chain, quick win, etc.)

### GATE: User Picks Work Queue

Use `AskUserQuestion`:

> "Here's my recommendation for today: #$A (P1), #$B (P1), #$C (P2). Which issues do you want to work on today, and in what order?"

Store the user's response as the ordered work queue:

```
PLANNED_ISSUES=[<ordered issue numbers>]
ACTIVE_ISSUE=<first issue number>
ISSUE_NUMBER=$ACTIVE_ISSUE
```

The first item becomes the **active issue**. Track `PLANNED_ISSUES` throughout the session -- the exit skill writes it to the state file.

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

### 3. Update Board Status (project mode only)

If `WORK_MODE == "project"`, update the project board item to "In Progress":

```bash
# Find the item ID for this issue (cache for reuse in later phases)
ITEM_ID=$(gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json | jq -r '.items[] | select(.content.number? == '$ISSUE_NUMBER') | .id')

# Update status to "In Progress"
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_IN_PROGRESS_ID
```

Cache `$ITEM_ID` -- it is reused in Phase 3 (step 9) and Phase 5 (step 5) for board updates.

### 4. Discovered Work Items

During brainstorming, new bugs, sub-tasks, or related work items may be identified. When this happens:

1. Note the discovered item and ask the user: "I've identified a potential new issue: **[description]**. Should I create a GitHub Issue for it?"
2. If yes, invoke the `/co-dwerker:new-issue` flow (Steps 1-3 from new-issue.md).
3. In project mode, the new-issue flow will also add it to the board with priority/status prompts.
4. Ask: "Add this to today's work queue, or leave it for a future session?"
5. If added to queue, append the new issue number to `PLANNED_ISSUES`.

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
- Run the full test suite (per project's CLAUDE.md -- typically `uv run pytest`)
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

### 9. Update Board (project mode only)

If `WORK_MODE == "project"`, update the project board item status to "In Review":

```bash
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_IN_REVIEW_ID
```

### 10. Discovered Work Items

During execution, bugs or additional tasks may surface. Handle them the same way as Phase 2 step 4:

1. Note the discovered item and ask the user if a new issue should be created.
2. If yes, invoke `/co-dwerker:new-issue`.
3. Ask whether to add to today's queue or leave for later.

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

- **New feature** --> create a new doc file in `$DOCS_PATH`
- **Changed behavior** --> update existing docs that reference the changed component
- **Bug fix** --> update known issues section if applicable
- **No user-facing impact** --> skip with a note

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

### 5. Update Board (project mode only)

If `WORK_MODE == "project"`, update the project board item status to "Done":

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

### 1. Show Progress

**Project mode:**
```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --limit 100
```

**Repo mode:**
```bash
gh issue list --repo "$REPO_OWNER_NAME" --state open --json number,title,labels --limit 20
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
> 1. Create a new issue (`/co-dwerker:new-issue`)
> 2. Pick an existing issue to work on
> 3. Run `/co-dwerker:exit` to wrap up the session"

### 4. User Options

At any point in the Next phase, the user can:
- Pick a new issue not in the original queue
- Create a new issue via `/co-dwerker:new-issue`
- Re-prioritize remaining items
- Invoke `/co-dwerker:exit` to end the session

---

## GitHub Project Board Setup

On first run in project mode, if the project board is missing expected fields, offer to create them.

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

When a required field is missing, create it AND populate its option values:

```bash
# Create Status field
gh project field-create $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" \
  --name "Status" --data-type "SINGLE_SELECT"
```

After creating the field, fetch its ID from the field list, then add each option value. Use the GitHub GraphQL API since `gh project` CLI may not support adding options directly:

```bash
# Fetch the newly created field ID
STATUS_FIELD_ID=$(gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json \
  | jq -r '.fields[] | select(.name == "Status") | .id')

# Add option values via GraphQL
gh api graphql -f query='
  mutation {
    updateProjectV2Field(input: {
      projectId: "'$PROJECT_ID'"
      fieldId: "'$STATUS_FIELD_ID'"
      singleSelectOptions: [
        {name: "Backlog", color: GRAY}
        {name: "Ready", color: BLUE}
        {name: "In Progress", color: YELLOW}
        {name: "In Review", color: ORANGE}
        {name: "Done", color: GREEN}
      ]
    }) {
      projectV2Field { ... on ProjectV2SingleSelectField { id } }
    }
  }
'
```

Repeat for Priority:

```bash
# Create Priority field
gh project field-create $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" \
  --name "Priority" --data-type "SINGLE_SELECT"

# Fetch field ID
PRIORITY_FIELD_ID=$(gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json \
  | jq -r '.fields[] | select(.name == "Priority") | .id')

# Add option values via GraphQL
gh api graphql -f query='
  mutation {
    updateProjectV2Field(input: {
      projectId: "'$PROJECT_ID'"
      fieldId: "'$PRIORITY_FIELD_ID'"
      singleSelectOptions: [
        {name: "P0-Critical", color: RED}
        {name: "P1-High", color: ORANGE}
        {name: "P2-Medium", color: YELLOW}
        {name: "P3-Low", color: BLUE}
      ]
    }) {
      projectV2Field { ... on ProjectV2SingleSelectField { id } }
    }
  }
'
```

After creating fields and options, re-fetch the field list to populate all field IDs and option IDs for the session.

### Ensuring Priority Labels Exist (both modes)

In repo mode, priority is tracked via GitHub labels. On first run, check that the repo has the expected priority labels:

```bash
gh label list --repo "$REPO_OWNER_NAME" --json name --jq '.[].name' | grep -c "^P[0-3]"
```

If any are missing, create them:

```bash
gh label create "P0-Critical" --repo "$REPO_OWNER_NAME" --color "B60205" --description "Critical priority" 2>/dev/null
gh label create "P1-High" --repo "$REPO_OWNER_NAME" --color "D93F0B" --description "High priority" 2>/dev/null
gh label create "P2-Medium" --repo "$REPO_OWNER_NAME" --color "FBCA04" --description "Medium priority" 2>/dev/null
gh label create "P3-Low" --repo "$REPO_OWNER_NAME" --color "0E8A16" --description "Low priority" 2>/dev/null
```
