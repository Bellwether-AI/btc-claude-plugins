---
name: new-issue
description: Use when the user wants to create a GitHub issue — "open an issue for this", "file a bug", "add a task for later" — or when new work surfaces mid-session. Also invoked inline by /co-dwerker:work and /co-dwerker:pr-review when they discover follow-up work.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py *)
---

# Co-Dwerker: New Issue

Create a GitHub issue in the current repo. In project mode, also add it to the board with a
priority and status. Works standalone at any time; the work and pr-review skills call it inline
when discovered work needs a home.

Conventions §1 (environment, `REPO_OWNER` vs `REPO_OWNER_NAME`, running the scripts) and §6 (`gh`
errors): `${CLAUDE_PLUGIN_ROOT}/references/conventions.md`.

## 1. Draft the issue

Ask for a title and description (a title alone is fine; help flesh it out). Build:

- **Title** — concise, imperative ("Add pagination to the user list endpoint").
- **Body**:
  ```markdown
  ## Description
  <what needs to happen and why>

  ## Acceptance Criteria
  - [ ] <criterion>
  ```
- **Labels** — suggest from the description (bug, enhancement, documentation, …).
- **Assignee** — `@me` unless told otherwise.

Show the draft and ask: **Create it (Recommended)**, **Edit first** (take the changes and redraft).

## 2. Priority (both modes)

Ask with options **P2-Medium (Recommended)**, **P1-High**, **P0-Critical**, **P3-Low**. Priority
labels are created on first use if the repo lacks them
(`${CLAUDE_PLUGIN_ROOT}/references/setup-project-board.md`).

## 3. Create

```bash
gh issue create --repo "$REPO_OWNER_NAME" \
  --title "<title>" --body "<body>" \
  --label "<label>" --label "<priority-label>" \
  --assignee "@me"
```

One `--label` flag per label. Capture `NEW_ISSUE_NUMBER` and the URL from the output.

## 4. Project board (project mode only)

Read the state file (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py show`):
`progress.context.work_mode` / `project_number`, falling back to the top-level `work_mode` /
`github_project_number`. If the mode is not `project`, skip to step 5.

Ask for a board status: **Backlog (Recommended)**, **Ready**, **In Progress**. Then:

```bash
gh project view $PROJECT_NUMBER --owner "$REPO_OWNER" --format json --jq '.id'          # PROJECT_ID
gh project item-add $PROJECT_NUMBER --owner "$REPO_OWNER" \
  --url "https://github.com/$REPO_OWNER_NAME/issues/$NEW_ISSUE_NUMBER"
gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json               # field + option ids
```

The new item can take a moment to appear in the list, so poll briefly rather than failing on the
first empty result:

```bash
for attempt in 1 2 3 4; do
  ITEM_ID=$(gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json \
    | jq -r '.items[] | select(.content.number? == '$NEW_ISSUE_NUMBER') | .id')
  [ -n "$ITEM_ID" ] && break
  sleep 2
done
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID \
  --field-id $PRIORITY_FIELD_ID --single-select-option-id $SELECTED_PRIORITY_OPTION_ID
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID \
  --field-id $STATUS_FIELD_ID --single-select-option-id $SELECTED_STATUS_OPTION_ID
```

## 5. Session integration

If a work session is active (`progress.status` is `in_progress` in the state file), record the
issue and ask whether it joins today's queue:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py set --append issues_created=$NEW_ISSUE_NUMBER
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py set --set planned_issues='[<existing..., NEW_ISSUE_NUMBER>]'   # only if the user says yes
```

## 6. Confirm

Tell the user the new issue number, title, and URL; in project mode, the project number, priority,
and status it was added with; and whether it joined today's queue.
