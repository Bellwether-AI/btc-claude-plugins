# GitHub Project Board & Label Setup

Reference file for first-run setup tasks. Read this file when setting up a new project's board fields or priority labels.

## Project Board Field Setup (project mode only)

On first run in project mode, if the project board is missing expected fields, offer to create them.

### Required Fields

| Field | Type | Options |
|-------|------|---------|
| Status | Single select | Backlog, Ready, In Progress, In Review, Done |
| Priority | Single select | P0-Critical, P1-High, P2-Medium, P3-Low |

### Optional Fields

These are used if present but not required:
- **Sprint** -- iteration field for grouping work by time period
- **Agent** -- single select for categorizing by agent/component
- **Docs PR** -- text field for linking companion documentation PRs

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

---

## Priority Label Setup (both modes)

Priority is tracked via GitHub labels in repo mode. In project mode, labels are also applied to keep things in sync. On first run, check that the repo has the expected priority labels:

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
