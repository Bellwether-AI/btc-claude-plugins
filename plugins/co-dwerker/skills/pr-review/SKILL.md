---
name: pr-review
description: Use when the user asks to review a GitHub pull request, check PR quality, or says "review this PR" / "review PR #N" — runs the automated review, addresses findings, updates the project board, and presents the PR for approval. Also invoked by /co-dwerker:work after it opens a PR.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py *)
---

# Co-Dwerker: PR Review

Review a pull request, fix what the review finds, update the board, and hand the PR to the user
for approval. `/co-dwerker:work` calls this at Phase 3 Step 8; it also works standalone on any
PR.

Conventions (environment, model policy, asking, `gh` errors):
`${CLAUDE_PLUGIN_ROOT}/references/conventions.md`.

## 0. Identify the PR

**From the work skill.** `.co-dwerker.state.json` → `progress.context` has `pr_number`,
`pr_url`, the active `progress.issue`, and `work_mode` (`checkpoint.py show` prints it). Confirm
in one line — "Reviewing PR #N for issue #M" — and go to step 1.

**Standalone.** Ask for a PR number or URL, then:

```bash
gh pr view $PR_NUMBER --repo "$REPO_OWNER_NAME" --json number,title,body,headRefName,state,url,labels
```

Keep `url` as `$PR_URL`. Derive `$ISSUE_NUMBER` from a `Closes #N` in the body, else from
`progress.issue` in the state file if it exists, else null. Read `work_mode` and
`github_project_number` from the state file for the board step.

## 1. Review

Invoke `pr-review-toolkit:review-pr` on the PR. If you dispatch additional reviewers yourself,
prefer `subagent_type: "fork"` so they inherit the design discussion, and do not pass `model`.

## 2. Address findings

For each finding: fix, re-run tests and lint, commit, push to the PR branch. Repeat until the
review is clean. A clean first pass goes straight on.

## 3. Board (project mode only)

Move the item to In Review. Ids come from `progress.context` (`project_id`, `item_id`,
`status_field_id`, `status_options`) when running inside the work skill; standalone, fetch them:

```bash
PROJECT_NUMBER=$(jq -r '.github_project_number' "$STATE_FILE")
PROJECT_ID=$(gh project view $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --jq '.id')
ITEM_ID=$(gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json \
  | jq -r '.items[] | select(.content.number? == '$ISSUE_NUMBER') | .id')
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID \
  --single-select-option-id $STATUS_IN_REVIEW_ID
```

No linked issue → say "No linked issue found for this PR; skipping the board update" and move on.

## 4. Discovered work

If the review surfaced bugs or follow-up tasks, ask whether to create issues for them (invoke
`co-dwerker:new-issue`) and whether they join today's queue.

## GATE: user approval

Before asking, confirm steps 1–4 actually happened (the review ran, findings are fixed and pushed,
the board is updated or the skip was stated, discovered work was offered). Then ask with
`AskUserQuestion`:

> PR #$PR_NUMBER is ready for your review: $PR_URL
> Changes: <one or two sentences>
> Tests pass, lint is clean, review findings addressed.

Options: **Approved, continue (Recommended)**; **I want changes** (take the notes, apply, and
return to step 2); **Stop here**. Return control to the caller, or end if standalone.
