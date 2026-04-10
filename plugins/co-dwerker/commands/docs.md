---
description: Create or update companion documentation for a PR or Issue. Use when writing docs for a docs repo, updating documentation, creating doc PRs, or documenting recent changes. Asks what PR or Issue to document when run standalone.
---
# Co-Dwerker: Docs

Create or update companion documentation in an external docs repo for a given PR or Issue. Can be invoked standalone at any time, or is called by the `/co-dwerker:work` workflow after code PR approval.

**Note:** This command handles **companion docs repo** updates only. CHANGELOG.md and RELEASE_NOTES.md updates in the code repo are handled separately by the `/co-dwerker:work` execute phase.

## Environment

```bash
TODAY=$(date +%Y-%m-%d)
STATE_FILE=".co-dwerker.state.json"
CONFIG_FILE=".co-dwerker.json"
REPO_REMOTE=$(git remote get-url origin 2>/dev/null)
REPO_OWNER_NAME=$(echo "$REPO_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
```

If `REPO_OWNER_NAME` is empty (not in a git repo or no remote):
1. Check `$STATE_FILE` for `repo_owner_name`.
2. If found, use it and tell the user: "Using **$SAVED_REPO** from your last session."
3. If not found, ask: "Which repo are these docs for? Provide the `owner/repo` name."

**GitHub hosting guard:** If `REPO_REMOTE` does not contain `github.com`, stop and tell the user: "co-dwerker requires a GitHub-hosted repository."

**Error handling:** If any `gh` CLI command fails during the docs workflow, report the error to the user and ask how to proceed rather than silently continuing.

## Model Preference

When dispatching subagents via the `Agent` tool during documentation work, always set `model: "opus"`. Never use `model: "haiku"`. Use `"sonnet"` as minimum fallback.

---

## Step 1: Identify the Subject

Determine what to document. This step adapts based on how the command was invoked.

### If invoked with context (from `/co-dwerker:work` Phase 4):

The calling workflow has `$ISSUE_NUMBER`, `$PR_NUMBER`, and `$REPO_OWNER_NAME` already set in the conversation context. Check whether these values are available from earlier in the conversation (they will be if Phase 3 just completed). If all three are present, confirm with the user:

> "Documenting changes from PR #$PR_NUMBER (Issue #$ISSUE_NUMBER). Proceeding to check docs config."

Skip to Step 2.

### If invoked standalone:

Use `AskUserQuestion`:

> "What would you like to document? Provide one of:
> - A **PR number** (e.g., #42)
> - An **Issue number** (e.g., #15)
> - A **description** of what to document"

Based on the response:

- **PR number provided:**
  ```bash
  gh pr view $PR_NUMBER --repo "$REPO_OWNER_NAME" --json title,body,files,commits,headRefName
  ```
  Also check if the PR closes an issue to get `$ISSUE_NUMBER`.

- **Issue number provided:**
  ```bash
  gh issue view $ISSUE_NUMBER --repo "$REPO_OWNER_NAME" --json title,body,comments,labels
  ```
  Check for linked/merged PRs:
  ```bash
  gh pr list --repo "$REPO_OWNER_NAME" --state merged --search "closes #$ISSUE_NUMBER" --json number,title
  ```
  Use the most recent merged PR as `$PR_NUMBER` if one exists.

- **Description provided:** Use the description directly. Set `$ISSUE_NUMBER` and `$PR_NUMBER` to null.

---

## Step 2: Check Docs Config

Read `$CONFIG_FILE` (`.co-dwerker.json`) for `docs_repo` and `docs_path`.

```bash
# Read the config file from the project root
```

**If no config file exists or `docs_repo` is null/missing:**

Use `AskUserQuestion`:

> "No companion docs repo is configured for this project. Would you like to:
> 1. **Configure one now** -- provide the `org/repo` and path within it
> 2. **Skip documentation** for now"

If the user provides a docs repo, update `.co-dwerker.json`:

```json
{
  "docs_repo": "Org/RepoName",
  "docs_path": "path/to/docs"
}
```

If skipped, end the command with a message: "Skipping documentation. You can configure a docs repo later by editing `.co-dwerker.json`."

**Store the values:**
```
DOCS_REPO=<org/repo>
DOCS_PATH=<path within docs repo>
```

---

## Step 3: Locate or Clone Docs Repo

Check if the docs repo is already cloned locally:

```bash
# Check common sibling locations relative to the code repo
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
git checkout main && git pull origin main
```

If `$ISSUE_NUMBER` is available:
```bash
git checkout -b "docs/$ISSUE_NUMBER-<short-description>"
```

If no issue number (description-only invocation):
```bash
git checkout -b "docs/$TODAY-<slug-from-description>"
```

---

## Step 4: Analyze Doc Impact

Determine what documentation to create or update.

**If a PR was provided**, read the PR diff:
```bash
gh pr diff $PR_NUMBER --repo "$REPO_OWNER_NAME"
```

**If only an issue was provided**, read the issue and any linked PRs:
```bash
gh issue view $ISSUE_NUMBER --repo "$REPO_OWNER_NAME" --json title,body,comments
```

**Categorize the impact:**
- **New feature** --> create a new doc file in `$DOCS_PATH`
- **Changed behavior** --> update existing docs that reference the changed component
- **Bug fix** --> update known issues section if applicable
- **No user-facing impact** --> tell the user: "The changes don't appear to have user-facing doc impact. Want to proceed anyway or skip?" If skipped, clean up the branch and end.

---

## Step 5: Create or Update Docs

Write documentation in the configured `$DOCS_PATH` within the docs repo.

- Follow the existing documentation style in that directory (read a few existing files first to match format, tone, and structure)
- For new features, create a new doc file
- For changed behavior, update the relevant existing files
- For bug fixes, update known issues or troubleshooting sections

---

## Step 6: Create Docs PR

```bash
cd "../$(basename $DOCS_REPO)"
# Stage only the specific files that were created or modified
git add <specific doc files changed>
git commit -m "docs: update documentation for $REPO_OWNER_NAME#$ISSUE_NUMBER"
git push -u origin "<branch-name>"
gh pr create --title "docs: <description>" --body "$(cat <<'EOF'
## Summary
Documentation update for $REPO_OWNER_NAME#$ISSUE_NUMBER

<bullet points describing doc changes>

## Related
- Code PR: $REPO_OWNER_NAME#$PR_NUMBER (if applicable)
- Issue: $REPO_OWNER_NAME#$ISSUE_NUMBER (if applicable)
EOF
)"
```

Capture the docs PR number and URL:
```
DOCS_PR_NUMBER=<number>
DOCS_PR_URL=<url>
```

---

## Step 7: Cross-Reference (workflow context only)

**If invoked from `/co-dwerker:work` Phase 4:** Back in the code repo, update CHANGELOG.md to reference the docs PR:
- Add a line noting the companion docs PR number

**If invoked standalone:** Skip this step. The user can manually cross-reference if desired.

---

## Step 8: Confirmation

Present the result:

> "Docs PR created: $DOCS_PR_URL
>
> Changes: <summary of doc updates>
>
> Related: Code PR $REPO_OWNER_NAME#$PR_NUMBER / Issue #$ISSUE_NUMBER"

If invoked from the work workflow, the calling Phase 4 will handle the gate for user approval before proceeding.

If invoked standalone, the command is complete.
