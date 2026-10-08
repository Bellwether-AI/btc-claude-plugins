---
name: pr-review
description: Use when the user asks to review a GitHub pull request or check PR quality — "review this PR", "review PR 123", "is this ready to merge". Also invoked by /co-dwerker:work after it opens a PR.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py *)
---

# Co-Dwerker: PR Review

Review a pull request, fix what the review finds, update the board, and hand the PR to the user
for approval. `/co-dwerker:work` calls this at Step 3.8; it also works standalone on any PR.

Conventions §1 (environment, `REPO_OWNER` vs `REPO_OWNER_NAME`, running the scripts), §2 (model
policy and the legwork tier, which step 2 uses) and §6 (`gh` errors):
`${CLAUDE_PLUGIN_ROOT}/references/conventions.md`.

## 0. Identify the PR

**From the work skill.** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py show` prints
`progress.context` with `pr_number`, `pr_url`, the active `progress.issue`, `work_mode`, and the
board ids, and `resolves_issues`. Confirm in one line — "Reviewing PR #N for issues #A, #B" —
and go to step 1.

**Standalone.** Ask for a PR number or URL, then:

```bash
gh pr view $PR_NUMBER --repo "$REPO_OWNER_NAME" --json number,title,body,headRefName,state,url,labels
```

Keep `url` as `$PR_URL`. Collect every same-repo `Closes|Fixes|Resolves #N` in the body as the
resolution set (conventions §10); the first is `$ISSUE_NUMBER` for the board lookup. If the body
has none, fall back to `progress.issue` in the state file if it exists, else null. Confirm in one
line — "Reviewing PR #N for issues #A, #B" — and if the title or body mentions an issue only as a
bare `#N`, say so: GitHub closes nothing on a bare reference, so the author should add
`Closes #N` before merge or the issue waits for Phase 5 or a later reconciliation to find it.
Read `work_mode` and the project number from the state
file (`progress.context.work_mode` / `project_number`, falling back to the top-level `work_mode`
/ `github_project_number`).

## 1. Review

Invoke `pr-review-toolkit:review-pr` on the PR. If you dispatch additional reviewers yourself,
prefer `subagent_type: "fork"` so they inherit the design discussion, and do not pass `model`.

## 2. Address findings

Decide each finding and write its fix spec (files, change, covering test). That is thinking-tier
work and stays on the session model. Implementing the specified fixes is legwork (conventions §2):
when the tier applies (session on the top model in the §2 lineup), batch every specified fix into
one `general-purpose` dispatch on the legwork model with the specs in the prompt; otherwise apply
them yourself. Re-run tests and lint, commit, push to the PR branch. Repeat until the review is
clean. A clean first pass goes straight on.

## 3. Board (project mode only)

Move the item to the board's `in_review` role (conventions §10). Inside the work skill the ids are
in `progress.context` (`project_id`, `item_id`, `status_field_id`, `status_role_map`). Standalone,
fetch them and build the role map from the conventions §10 role-name table:

```bash
gh project view $PROJECT_NUMBER --owner "$REPO_OWNER" --format json --jq '.id'                 # PROJECT_ID
gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json \
  --jq '.fields[] | select(.name=="Status") | {id, options}'                                   # STATUS_FIELD_ID + options → role map
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json \
  | jq -r '.items[] | select(.content.number? == '$ISSUE_NUMBER') | .id'                        # ITEM_ID
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID \
  --single-select-option-id $STATUS_ROLE_IN_REVIEW_ID
```

`in_review` is `null` (the board has no review status) → say "This board has no in-review
status; leaving the item where it is" and move on. No linked issue → say "No linked issue found
for this PR; skipping the board update" and move on.

## 4. Discovered work

If the review surfaced bugs or follow-up tasks, ask whether to create issues for them (invoke
`co-dwerker:new-issue`) and whether they join today's queue.

## GATE: user approval

Before asking, confirm steps 1–4 actually happened (the review ran, findings are fixed and pushed,
the board is updated or the skip was stated, discovered work was offered). Then ask with
`AskUserQuestion`, giving the PR number and URL, a one- or two-sentence summary of the change, and
the verification status (tests, lint, review findings). Options: **Approve — continue to docs,
then merge (Recommended)**; **I want changes** (take the notes, apply them, return to step 2);
**Stop here**. Return control to the caller, or end if standalone.
