---
description: Merge open PRs, sync local main, and clean up artifacts
---
# Flywheel: Merge

Merge all open PRs for the current repo, sync local main, and clean up any stray flywheel artifacts.

This is a finalization command run after the user has reviewed all open PRs.

## Environment

```bash
FLYWHEEL_PATH="$HOME/.flywheel"
```

## Process

### 1. List Open PRs

Get all open PRs for the current repository:

```bash
gh pr list --json number,title,headRefName
```

If no PRs found, report and skip to cleanup.

### 2. Disable Deploy Workflow

When merging multiple PRs, each squash merge triggers a push to main. To avoid wasted CI runs (each cancelling the previous), disable the deploy workflow before merging:

```bash
gh workflow disable deploy.yml
```

If this fails (e.g., workflow not found), log a warning but continue — the merges will still work, just with the old cancel-and-restart behavior.

### 3. Merge Each PR

For each open PR, merge with squash and delete the remote branch.

First, get the list of PR numbers (single Bash call):
```bash
gh pr list --json number -q '.[].number'
```

Then, for each PR number from the output, run a separate Bash call:
```bash
gh pr merge $PR_NUMBER --squash --delete-branch
```

Track success/failure in agent logic (not shell variables). Continue with remaining PRs even if one fails. Collect all results for the final report.

### 4. Re-enable Deploy Workflow and Trigger Single Deploy

After all merges are complete, re-enable the workflow and trigger a single deploy:

```bash
gh workflow enable deploy.yml
```

Then trigger a single deploy run (only if at least one PR was successfully merged):
```bash
gh workflow run deploy.yml
```

If either command fails, log a warning and report it. The user can manually trigger the deploy.

### 5. Sync Local Main Branch

After merging, sync the local main branch with remote. Run each as a separate Bash call:

```bash
git fetch origin
```

```bash
git checkout main
```

```bash
git pull origin main
```

### 6. Rebuild and Restart Agent (Flywheel repo only)

This step only applies when merging PRs in the `personal/flywheel` project. Check the project's `CLAUDE.md` for `## Project Identifier` — if it contains `personal/flywheel`, proceed. Otherwise, skip this step entirely.

If any sub-step fails, log the error and continue to step 7 (cleanup). Do not block the merge.

1. **Build the agent**:

```bash
npm run build --prefix ~/personal/flywheel/agent
```

If the build fails, log the error and skip the restart — proceed to step 7.

2. **Restart via launchctl**:

```bash
launchctl unload ~/Library/LaunchAgents/com.flywheel.agent.plist
```

Wait 2 seconds, then:

```bash
launchctl load ~/Library/LaunchAgents/com.flywheel.agent.plist
```

3. **Verify the restart** by reading the last 15 lines of `~/.flywheel/logs/agent.log`. Confirm you see:
   - `Hook server listening on http://127.0.0.1:9753`
   - `Connected to Flywheel hub`

If the log shows `EADDRINUSE` on port 9753, the previous process hasn't fully stopped. Wait a few more seconds and try the `launchctl load` again.

4. **Track the result** for the final report — rebuilt (yes/no), restarted (yes/no), status (running/failed).

### 7. Clean Up Local Branches

Delete any local branches that have been merged.

First, get the list of merged branches (single Bash call):
```bash
git branch --merged main
```

Parse the output in agent logic — exclude lines containing `*`, `main`, or `master`. Then for each branch name, run a separate Bash call:
```bash
git branch -d $BRANCH
```

If a delete fails, continue with the remaining branches.

### 8. Clean Up Flywheel Artifacts

Remove any stray flywheel files. Run each as a separate Bash call (no echo suffixes):

1. Remove prompt files in current directory — use `Glob` first, then `rm -f` each:
```
Glob(pattern=".flywheel-prompt-*.txt")
```
Then for each file found, run a separate Bash call:
```bash
rm -f /exact/path/to/.flywheel-prompt-exact-filename.txt
```

2. Remove transitioning markers in Flywheel — use `Glob` first, then `rm -f` each:
```
Glob(pattern=".flywheel-transitioning-*", path="$FLYWHEEL_PATH")
```
Then for each file found, run a separate Bash call:
```bash
rm -f /exact/path/to/.flywheel-transitioning-exact-filename
```

3. Find orphaned worktree directories. First get registered worktrees:
```bash
git worktree list
```

Then use `Glob` to find directories in the worktrees parent:
```
Glob(pattern="$WORKTREE_PARENT/*/")
```

Compare the two lists in agent logic. For each directory that is NOT in the git worktree list, remove it (separate Bash call per orphan):
```bash
rm -rf "$ORPHAN_DIR"
```

### 9. Report Results

```markdown
## Merge Complete

### PRs Merged
- [List of successfully merged PRs]

### PRs Failed (if any)
- [List of PRs that failed to merge with reason]

### Deploy
- Workflow disabled during merges, re-enabled after
- Single deploy triggered via workflow_dispatch

### Local Sync
- Branch: main
- Status: Up to date with origin/main

### Agent (if personal/flywheel repo)
- Rebuilt: yes/no
- Restarted: yes/no
- Status: [running | failed — reason | skipped — not flywheel repo]

### Cleanup
- Prompt files removed: [count]
- Transitioning markers removed: [count]
- Local branches deleted: [list]
```

## Error Handling

### PR Merge Fails

If a PR fails to merge:
1. Log the error
2. Add to failed list
3. Continue with remaining PRs
4. Report all failures at the end

Common failure reasons:
- Merge conflicts (user must resolve manually)
- Required checks not passed (shouldn't happen if user reviewed)
- Branch protection rules

### No PRs Found

If no open PRs exist:
```markdown
## No PRs to Merge

No open pull requests found for this repository.

### Cleanup Performed
- [cleanup actions taken]
```

## Usage

Run from any git repository:

```bash
/flywheel:merge
```

## Key Rules

1. **User has already reviewed PRs** - no additional approval checks
2. **Continue on failure** - merge other PRs even if one fails
3. **Clean up everything** - branches, prompt files, transitioning markers
4. **Report all results** - clear summary of what happened
