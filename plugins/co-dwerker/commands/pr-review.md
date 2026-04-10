---
description: Review a PR created during a co-dwerker work session -- run pr-review-toolkit, address findings, update board status, and present for user approval. Called by /co-dwerker:work Phase 3, or invoke standalone for any PR.
---
# Co-Dwerker: PR Review

Review a pull request, address findings, update the project board, and present the PR for user approval. This command is called by `/co-dwerker:work` Phase 3 after PR creation, but can also be invoked standalone for any PR.

## Environment

```bash
STATE_FILE=".co-dwerker.state.json"
REPO_REMOTE=$(git remote get-url origin 2>/dev/null)
REPO_OWNER_NAME=$(echo "$REPO_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
```

## Model Preference

When dispatching subagents via the `Agent` tool during PR review, always set `model: "opus"`. Never use `model: "haiku"`. Use `"sonnet"` as minimum fallback.

---

## Step 0: Identify the PR

### If invoked with context (from `/co-dwerker:work` Phase 3):

The calling workflow has `$PR_NUMBER`, `$ISSUE_NUMBER`, `$REPO_OWNER_NAME`, and `$WORK_MODE` in the conversation context. Confirm:

> "Reviewing PR #$PR_NUMBER for Issue #$ISSUE_NUMBER."

Skip to Step 1.

### If invoked standalone:

Use `AskUserQuestion`:

> "Which PR do you want to review? Provide a PR number or URL."

Fetch context:

```bash
gh pr view $PR_NUMBER --repo "$REPO_OWNER_NAME" --json number,title,body,headRefName,state
```

Also check if the state file has `work_mode` and project board context:

```bash
# Read .co-dwerker.state.json if it exists
```

---

## Step 1: Review

Use the `Skill` tool to invoke `pr-review-toolkit:review-pr` on the PR.

---

## Step 2: Address Review Findings

If the review identifies issues:

1. Fix each finding
2. Re-run verification (tests + lint)
3. Commit fixes
4. Push to the PR branch

Repeat until the review is clean. If the review found no issues, proceed immediately.

---

## Step 3: Update Board (project mode only)

**Skip this step if `WORK_MODE` is not `"project"` or if no project board context is available.**

If `WORK_MODE == "project"`, update the project board item status to "In Review":

```bash
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_IN_REVIEW_ID
```

If `$PROJECT_ID`, `$ITEM_ID`, or field IDs are not in conversation context (standalone invocation), read them from the state file or fetch them:

```bash
PROJECT_NUMBER=$(jq -r '.github_project_number' "$STATE_FILE")
PROJECT_ID=$(gh project view $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --jq '.id')
ITEM_ID=$(gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json | jq -r '.items[] | select(.content.number? == '$ISSUE_NUMBER') | .id')
```

---

## Step 4: Discovered Work Items

During the review, bugs or additional tasks may have surfaced. If any were identified:

1. Note the discovered item and ask the user if a new issue should be created.
2. If yes, invoke `/co-dwerker:new-issue`.
3. Ask whether to add to today's queue or leave for later.

If nothing was discovered, skip this step.

---

## GATE: User Approval

Use `AskUserQuestion`:

> "PR #$PR_NUMBER is ready for your review: $PR_URL
>
> Changes: <1-2 sentence summary>
>
> All tests pass, linting clean, review findings addressed. Ready for you to confirm."

Wait for user approval before returning control to the calling workflow (or ending if standalone).
