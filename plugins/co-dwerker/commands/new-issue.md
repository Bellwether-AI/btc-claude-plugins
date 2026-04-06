---
description: Create a new GitHub Issue and optionally add it to the active project board with priority and status
---
# Co-Dwerker: New Issue

Create a GitHub Issue from the current repo. If a co-dwerker work session is active in project mode, the issue is also added to the project board with user-selected priority and status.

This command can be invoked standalone at any time, or it is called inline during work sessions when new work items surface.

## Environment

```bash
TODAY=$(date +%Y-%m-%d)
STATE_FILE=".co-dwerker.state.json"
REPO_REMOTE=$(git remote get-url origin 2>/dev/null)
REPO_OWNER_NAME=$(echo "$REPO_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
```

---

## Step 1: Gather Issue Details

Use `AskUserQuestion` to collect the issue information:

> "What's the issue? Give me a title and description (or just a title and I'll help flesh it out)."

From the user's response, construct:
- **Title** — concise, imperative form (e.g., "Add pagination to user list endpoint")
- **Body** — expand the user's description into a structured issue body:
  ```markdown
  ## Description
  <what needs to happen and why>

  ## Acceptance Criteria
  - [ ] <criterion 1>
  - [ ] <criterion 2>
  ```
- **Labels** — suggest relevant labels based on the description (bug, enhancement, documentation, etc.). Ask the user to confirm or adjust.
- **Assignee** — default to `@me` unless the user specifies otherwise.

Present the draft issue to the user for confirmation before creating it:

> "Here's the issue I'll create:
>
> **Title:** <title>
> **Labels:** <labels>
> **Assignee:** <assignee>
>
> **Body:**
> <body preview>
>
> Look good?"

---

## Step 2: Create the Issue

```bash
gh issue create --repo "$REPO_OWNER_NAME" \
  --title "<title>" \
  --body "<body>" \
  --label "<label1>,<label2>" \
  --assignee "@me"
```

Capture the new issue number from the command output:

```bash
NEW_ISSUE_NUMBER=<number from gh output>
```

---

## Step 3: Project Board Integration (project mode only)

Read the state file to check the current work mode:

```bash
# Read .co-dwerker.state.json
```

**If `work_mode` is not `"project"`, skip to Step 4.**

If `work_mode == "project"`, the issue should be added to the active project board.

### 3a. Load Project Context

Read from the state file:
- `github_project_number` → `PROJECT_NUMBER`
- Fetch `PROJECT_ID` if not cached:

```bash
PROJECT_ID=$(gh project view $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --jq '.id')
```

### 3b. Ask for Priority and Status

Use `AskUserQuestion`:

> "Adding to Project #$PROJECT_NUMBER. What priority and status?"
>
> **Priority:** P0-Critical / P1-High / P2-Medium (default) / P3-Low
> **Status:** Backlog (default) / Ready / In Progress

### 3c. Add Issue to Project Board

```bash
# Add the issue to the project
gh project item-add $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" \
  --url "https://github.com/$REPO_OWNER_NAME/issues/$NEW_ISSUE_NUMBER"
```

### 3d. Set Priority and Status Fields

Fetch the project field IDs and option IDs (load from state cache if available, otherwise query):

```bash
# Get field list
gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json
```

Find the item ID for the newly added issue:

```bash
ITEM_ID=$(gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json \
  | jq -r '.items[] | select(.content.number? == '$NEW_ISSUE_NUMBER' and .content.repository? | test("'$REPO_OWNER_NAME'")) | .id')
```

If `ITEM_ID` is empty, the issue may not have been added yet. Wait briefly and retry:

```bash
# Retry once if ITEM_ID is empty
sleep 2
ITEM_ID=$(gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json \
  | jq -r '.items[] | select(.content.number? == '$NEW_ISSUE_NUMBER') | .id')
```

Set the field values:

```bash
# Set priority
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID \
  --field-id $PRIORITY_FIELD_ID --single-select-option-id $SELECTED_PRIORITY_OPTION_ID

# Set status
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID \
  --field-id $STATUS_FIELD_ID --single-select-option-id $SELECTED_STATUS_OPTION_ID
```

### 3e. Also Apply Priority Label to Issue

To keep repo-mode and project-mode in sync, add the priority as a label on the issue itself:

```bash
gh issue edit $NEW_ISSUE_NUMBER --repo "$REPO_OWNER_NAME" --add-label "<priority-label>"
```

Where `<priority-label>` matches the selected priority (e.g., `P1-High`).

---

## Step 4: Session Integration

If called during an active work session (state file has `last_session.date == $TODAY`):

Use `AskUserQuestion`:

> "Add Issue #$NEW_ISSUE_NUMBER to today's work queue?"

If yes, append `NEW_ISSUE_NUMBER` to the in-memory `PLANNED_ISSUES` list. The exit skill will persist this to the state file.

If no, the issue stays in backlog / the status selected in Step 3.

---

## Step 5: Confirmation

Present the result:

> "Created Issue #$NEW_ISSUE_NUMBER: <title>
> $ISSUE_URL"

If added to a project board:

> "Added to Project #$PROJECT_NUMBER as **$PRIORITY** / **$STATUS**"

If added to today's work queue:

> "Added to today's work queue."
