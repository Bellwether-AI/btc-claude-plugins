---
description: Commit, push, create PR, and archive a completed work item
---
# Flywheel: Done

Commit, push, create PR (if applicable), archive work item, and clean up. Transitions `review` → `done`.

This command merges the functionality of the old `/flywheel-ship` and `/flywheel-cleanup` commands.

## Environment

```bash
FLYWHEEL_PATH="$HOME/.flywheel"
```

## Process

### 1. Load the Work Item

If you were given a prompt file to read (e.g., `.flywheel-prompt-*.txt`), you already have the work item path from that file — use `Read` to load it directly. Do not search for other work items.

Otherwise, find the work item:

1. Use `Glob(pattern=".flywheel-prompt-*.txt")` to find prompt files in the current directory
2. If found, use `Read` to read the prompt file contents
3. If no prompt file, use `Grep(pattern="^- status: review", path="$FLYWHEEL_PATH/work/")` to find work items with status `review`
4. If multiple files match, pick the most recently modified file (latest date prefix in filename). If still ambiguous, ask the user which work item to use.
5. Use `Read` to read the matching work item file

Extract `WORK_ITEM_PATH` and `WORK_ITEM_FILENAME` from the file path.

Read the work item to understand:
- The workflow type (main vs worktree)
- Success criteria (verify they're all checked)

### 1a. Detect Non-Code Work Item

Check if this is a non-code work item by examining the `type` metadata field.

**Detection method:**
1. Check the `- type:` field in the work item metadata
2. If type is `research`, `writing`, `browser`, `organize`, `manual`, or `ops` → this is a non-code item
3. If type is `code` or not set → check `git -C "$PROJECT_PATH" status --short` in the target project
4. If the output is empty (no changes), treat as non-code

**If non-code item detected:**
- Skip steps 2 (Final Verification), 4 (Stage and Commit), and 5 (Push and Create PR)
- Proceed directly to step 6 (Archive Work Item) and then cleanup

For non-code items, the "done" flow is: verify success criteria → archive work item → commit flywheel changes → clean up.

### 2. Final Verification

**Skip this step for non-code items** (detected in step 1a).

Run the project's verification commands (from CLAUDE.md):
```bash
npm run typecheck  # or equivalent
npm run lint       # or equivalent
npm run test       # or equivalent
```

If any fail, fix the issues first before proceeding.

### 3. Check All Success Criteria

Verify all success criteria are marked complete `[x]` in the work item.
If any are not complete, stop and report what's missing.

### 4. Stage and Commit

**Skip this step for non-code items** (detected in step 1a).

Run each as a separate Bash call:

1. `git status --short`
2. `git add -A`

Create a meaningful commit message following conventional commits:
- feat: New feature
- fix: Bug fix
- docs: Documentation
- refactor: Code restructure
- test: Adding tests
- chore: Maintenance

Include work item reference in commit body (separate Bash call):

```bash
git commit -m "[type]: [description]

[Optional body with more details]

Flywheel: [work-item-id]"
```

### 5. Push and Create PR (Workflow Dependent)

**Skip this step for non-code items** (detected in step 1a).

Read the `workflow` field from work item metadata using `Grep`:
```
Grep(pattern="^- workflow:", path="$WORK_ITEM_PATH")
```

#### If workflow is `main`:
```bash
git push origin main
```
No PR created - work goes directly to main.

#### If workflow is `worktree` or unset:

Check we're not on main (single Bash call):
```bash
git branch --show-current
```
If the result is `main` or `master`, stop and report the error. Do NOT use shell `if/then` — check the output in agent logic.

Push (single Bash call):
```bash
git push -u origin HEAD
```

Create PR (single Bash call):
```bash
gh pr create \
  --title "[Work item title]" \
  --body "## Summary
[From work item description]

## Changes
- [Key changes made]

## Success Criteria Verified
- [x] [Criterion 1]
- [x] [Criterion 2]

## Testing
[Verification commands that passed]

## Flywheel
Work Item: [id]"
```

Capture the PR URL from the output.

### 6. Archive Work Item

Update the work item using the `Edit` tool (separate calls for each change):

1. Set status: `Edit(old_string="- status: review", new_string="- status: done")`
2. Clear session: `Edit(old_string="- assigned-session: ...", new_string="- assigned-session:")`
3. Append to execution log using `Edit` (find the last log entry and add after it):
   - `[timestamp] Committed and pushed`
   - `[timestamp] PR created: [URL]` (if worktree workflow)
   - `[timestamp] Work item completed`

### 7. Sync Work Item

Work items are synced to the API automatically via the file watcher — no git operations needed on the work folder.

### 8. Clean Up

#### Clean up prompt files:

Use `Glob` to find prompt files, then `rm -f` each one individually by exact path:
```
Glob(pattern=".flywheel-prompt-*.txt", path="/absolute/path/to/project")
```
Then for each file found, run a separate Bash call:
```bash
rm -f /absolute/path/to/project/.flywheel-prompt-exact-filename.txt
```

Prompt files may also exist in other project directories (sophia/, bellwether/, personal/). If the work item's project is not flywheel, also clean up that project's directory using the same Glob-then-rm approach:
```
Glob(pattern=".flywheel-prompt-*.txt", path="/absolute/path/to/other/project")
```
Then `rm -f` each file found individually.

#### If workflow is `worktree`:

**CRITICAL: Capture info BEFORE cleanup.**

Run each as a separate Bash call and save the results in agent logic:

1. Get current path:
```bash
pwd
```

2. Get main project path (parse first line, first column from output):
```bash
git worktree list
```

3. Get current branch:
```bash
git branch --show-current
```

**Migrate Worktree Permissions (before cleanup):**

Check if the worktree has `.claude/settings.json` with permissions that should be migrated to the main project:

Use `Read` to attempt reading `$WORKTREE_PATH/.claude/settings.json`. If the file exists, proceed with migration. If it doesn't exist (Read returns an error), skip migration silently.

**If worktree settings exist:**

1. Read the permissions from `$WORKTREE_PATH/.claude/settings.json` using `Read`
2. For each permission, check if it contains the worktree path
3. Replace worktree path with main project path
4. Compare with main project's existing permissions (avoid duplicates)

**Present migration prompt:**

```markdown
## Permissions Migration

Found permissions in worktree that can be migrated to main project:

**Worktree permissions to migrate:**
- [List permissions with paths corrected]

**Already in main project (will skip):**
- [List any duplicates]

**Options:**
1. **Migrate** - Copy permissions to main project's .claude/settings.json
2. **Skip** - Don't migrate (permissions will be lost when worktree is deleted)

Choose (1/2): _
```

**If user approves migration:**

1. Ensure `$MAIN_PROJECT/.claude/` directory exists
2. If `$MAIN_PROJECT/.claude/settings.json` doesn't exist, create it with empty structure:
   ```json
   {"permissions": {"allow": []}}
   ```
3. Merge the migrated permissions (with corrected paths) into the main project settings
4. Avoid duplicates - only add permissions not already present
5. Write the updated settings.json

**If no worktree settings exist:**
Silently continue to cleanup - don't prompt if nothing to migrate.

**IMPORTANT:** All git commands below use `git -C "$MAIN_PROJECT"` to target the main repo. The worktree directory will be deleted during cleanup, which kills Claude Code's Bash tool (it checks cwd exists before every command). Therefore, **branch deletion and prune MUST happen BEFORE worktree removal**.

**Step 1: Detach HEAD in the worktree** (so the branch is no longer checked out):
```bash
git -C "$WORKTREE_PATH" checkout --detach
```

**Step 2: Delete the branch** — try soft delete first, then force if needed (separate Bash calls). This MUST happen while cwd still exists:

1. Try soft delete:
```bash
git -C "$MAIN_PROJECT" branch -d "$BRANCH"
```

2. If soft delete fails (e.g., unmerged changes), try force delete:
```bash
git -C "$MAIN_PROJECT" branch -D "$BRANCH"
```

**Step 3: Prune orphaned worktree references** (separate Bash call):
```bash
git -C "$MAIN_PROJECT" worktree prune
```

**Step 4: Remove worktree** — this destroys the cwd, so it MUST be the last git operation. Run each as a separate Bash call. Handle failures in agent logic, not shell:

1. Remove git worktree registration:
```bash
git -C "$MAIN_PROJECT" worktree remove "$WORKTREE_PATH" --force
```
If this fails, continue to the next step.

2. Remove the directory (worktree remove may leave behind untracked files). Note: this may also fail if cwd was inside the worktree — that's OK, the worktree is already deregistered:
```bash
rm -rf "$WORKTREE_PATH"
```

**Worktree Cleanup Error Handling:**
- `git worktree remove` deregisters the worktree; `rm -rf` ensures the directory is fully removed
- After worktree removal, the Bash tool may stop working if cwd was inside the worktree — this is expected and OK since all critical operations (branch delete, prune) already completed
- If the directory doesn't exist, that's fine - cleanup is already done
- If all cleanup fails, report the issue and let the user clean up manually

### 9. Capture Learnings (Auto-Detect)

After completing the work, analyze the session for learnings worth capturing.

#### Detection Heuristics

Scan the **execution log** and **conversation history** for signals:

1. **Retry patterns**: Multiple attempts at the same operation
2. **Error resolutions**: Error messages that were eventually fixed
3. **Workarounds**: Non-obvious solutions, fallbacks used
4. **Repeated issues**: Problems that have occurred before

**Keywords to look for:**
- "retry", "failed", "error", "workaround", "fallback"
- "finally worked", "the fix was", "turns out"
- "this keeps happening", "again", "same issue"

#### If Learning Detected

Draft a solution document using this format:

```markdown
---
date: [TODAY]
category: [tool-environment | flywheel-patterns | project-specific]
tags: [relevant, keywords]
---

# [Brief title describing the problem/solution]

## Problem
[What went wrong - include exact error messages]

## Solution
[What fixed it - step by step]

## Prevention
[How to avoid this next time]
```

**Present to user with options:**

```markdown
## Learning Detected

I noticed [brief description of what was learned].

**Draft solution:**
[Show the draft document]

**Options:**
1. **Save as-is** - Save to `solutions/[category]/`
2. **Edit first** - Let me modify before saving
3. **Skip** - Don't capture this learning

Choose (1/2/3): _
```

#### If User Approves (Option 1 or 2)

1. Generate filename from title (kebab-case, max 50 chars)
2. Save to `$FLYWHEEL_PATH/solutions/[category]/[filename].md`
3. Report: "Learning saved to `solutions/[category]/[filename].md`"

#### If No Learning Detected

Silently continue to Report section. Don't prompt if nothing worth capturing.

### 10. Report

#### For main workflow:
```markdown
## Done

### Git
- **Commit**: [hash]
- **Branch**: main
- **Pushed**: Yes

### Flywheel
- **Work Item**: [id]
- **Status**: done
- **Location**: work/[filename]

### Cleanup
- Prompt files removed

### Ready for Next
Run `/flywheel:new` to create another work item.
```

#### For worktree workflow:
```markdown
## Done

### Git
- **Commit**: [hash]
- **Branch**: [branch]
- **PR**: [PR_URL]

### Flywheel
- **Work Item**: [id]
- **Status**: done
- **Location**: work/[filename]

### Cleanup
- Worktree removed: [path]
- Branch deleted: [branch]
- Prompt files removed
- Now in: [main project]

### Ready for Next
Run `/flywheel:new` to create another work item.
```

## Status Transition

```
review → done
```

## If Work Item Not in Review

If status is `new`:
- Suggest running `/flywheel:define` first

If status is `defined`:
- Suggest running `/flywheel:plan` first

If status is `planned` or `executing`:
- Suggest running `/flywheel:execute` to complete implementation

If status is already `done`:
- Report that work item is already complete
- No action needed

## Error Handling

### PR Creation Fails
- Check `gh auth status`
- Verify branch is pushed
- Report error and suggest manual PR creation

### Flywheel Update Fails
- Report error but don't block shipping
- Update status manually in the work item file
- PR/commit is the priority - work item tracking is secondary

### Commit Fails (pre-commit hooks)
- Run the failing checks
- Fix issues
- Retry commit
- Max 3 attempts before reporting blocked

## Key Rules

1. **Always verify before shipping** - run all project checks first
2. **Delete branch BEFORE removing worktree** - worktree removal kills the Bash tool's cwd
3. **Archive work item after successful push** - keeps done/ as permanent record
4. **Main workflow is simpler** - no branches, no PRs, no worktree cleanup
5. **Do NOT retry failing cleanup commands** - if a command fails, use the fallback approach or report the issue; never retry the same failing command more than once
6. **Only push flywheel repo for flywheel projects** - other projects may not have remote access
