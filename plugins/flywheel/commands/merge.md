# Flywheel: Merge

Merge all open PRs for the current repo, sync local main, and clean up any stray flywheel artifacts.

This is a finalization command run after the user has reviewed all open PRs.

## Command Execution Guidelines

**CRITICAL**: Follow these rules to minimize permission prompts:

1. **Use dedicated tools instead of shell equivalents:**
   - `Glob` instead of `find` or `ls` for file discovery
   - `Grep` instead of `grep` or `grep -q` for pattern matching
   - `Read` instead of `cat` for reading files
   - `Edit` instead of `sed -i` for file modifications
2. **One command per Bash call** — never chain with `&&`, `;`, or `||`
   - Bad: `rm -f file.txt 2>/dev/null; echo "done"`
   - Good: `rm -f file.txt`
3. **No echo suffixes** — `rm -f` with `2>/dev/null` is already silent on failure
4. **Use absolute paths or `git -C`** — never `cd dir && git ...`
   - Bad: `cd /path/to/repo && git add . && git commit -m "msg"`
   - Good: Three separate calls: `git -C /path/to/repo add .`, then `git -C /path/to/repo commit -m "msg"`
5. **Handle fallbacks in agent logic** — don't use `cmd1 || cmd2` in shell
   - Bad: `git branch -d "$B" 2>/dev/null || git branch -D "$B"`
   - Good: Try `git branch -d "$B"` first; if it fails, try `git branch -D "$B"` as a separate call
6. **No glob patterns in rm/write operations** — use `Glob` tool first, then `rm -f` each file individually
   - Bad: `rm -f .flywheel-prompt-*.txt`
   - Good: Use `Glob(pattern=".flywheel-prompt-*.txt")` to find files, then `rm -f /exact/path/to/file.txt` for each

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

### 2. Merge Each PR

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

### 3. Sync Local Main Branch

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

### 4. Clean Up Local Branches

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

### 5. Clean Up Flywheel Artifacts

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

### 6. Report Results

```markdown
## Merge Complete

### PRs Merged
- [List of successfully merged PRs]

### PRs Failed (if any)
- [List of PRs that failed to merge with reason]

### Local Sync
- Branch: main
- Status: Up to date with origin/main

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
