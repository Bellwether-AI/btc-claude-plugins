# Flywheel: Execute Plan

Execute the implementation plan autonomously, transitioning `planned` → `review` (items stay in `planned` during execution).

## Environment

```bash
FLYWHEEL_PATH="$HOME/.flywheel"
```

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

## Process

### 1. Load the Work Item

Check for a prompt file first (launched from dashboard):

1. Use `Glob(pattern=".flywheel-prompt-*.txt")` to find prompt files in the current directory
2. If found, use `Read` to read the prompt file contents

Or find a `planned` work item:

1. Use `Grep(pattern="^- status: planned", path="$FLYWHEEL_PATH/work/")` to find work items with status `planned`
2. Use `Read` to read the matching work item file

Read the work item to understand:
- The implementation plan
- Success criteria
- Current progress (if resuming)

**Check effort level:** Look for `- effort:` in the work item metadata. If effort is `high`, use thorough reasoning for all implementation decisions: "This is a high-complexity work item. Use thorough reasoning for all implementation decisions."

### 2. Prepare for Execution

Items remain in `planned` status during execution (with gradient animation in the dashboard).

### 2a. Search Prior Learnings

Before starting work, search for relevant solutions from past issues.

**Extract keywords from work item:**
- Title words
- Tags from description
- Key technical terms

**Search solutions directory:**

Use the `Grep` tool:
```
Grep(pattern="keyword", path="$FLYWHEEL_PATH/solutions/", output_mode="files_with_matches")
```

**If matches found, display them:**

```markdown
## Prior Learnings Found

Found [N] potentially relevant solution(s):

### 1. [Title from solution file]
**Problem:** [First line of Problem section]
**File:** `solutions/[category]/[filename].md`

### 2. [Title from solution file]
...

Review these before proceeding to avoid repeating past mistakes.
```

**If no matches found:**
Silently continue - don't mention if nothing relevant.

### 2b. Check Chrome Plugin (if Browser Verification Required)

If the work item contains a `## Browser Verification` section, the Chrome plugin is required.

**Check availability:**
1. Call `mcp__claude-in-chrome__tabs_context_mcp`
2. If the call succeeds → Chrome plugin is available, continue
3. If the call fails/errors → Chrome plugin is unavailable, **FAIL EXECUTION**

**If Chrome plugin unavailable:**
```markdown
## Blocked

**Issue:** Chrome plugin required but unavailable
**Reason:** This work item includes frontend changes that require browser verification.
**Required:**
- Chrome browser must be running
- Claude in Chrome extension must be installed and active
- The MCP connection must be established

Please ensure the Chrome plugin is available and run `/flywheel:execute` again.
```

Update status to blocked and stop execution. Do not proceed without browser verification capability for frontend work items.

### 2c. Detect Worktree Port (if Browser Verification Required)

If the work item contains a `## Browser Verification` section and the current directory is a git worktree (not the main working tree), find an available port for the dev server.

**Detect worktree** — run each as a separate Bash call and compare in agent logic:

1. Get registered worktrees:
```bash
git worktree list
```
Parse the first line's first column to get the main worktree path.

2. Get current directory:
```bash
pwd
```

If the current directory differs from the main worktree path, this is a worktree.

**Find available port (worktree only):**

If in a worktree, check which ports are in use (single Bash call):
```bash
lsof -i :3001-3010
```

In agent logic, pick the first port in the 3001-3010 range that is NOT in the output. If all ports are in use, report an error.

If on the main worktree, use the default port 3000.

**Start dev server with detected port:**
- In worktree: `npm run dev -- --port $DEV_PORT`
- On main: `npm run dev` (default port 3000)

**Use `http://localhost:$DEV_PORT` for all browser verification navigate calls** instead of hardcoded `http://localhost:3000`.

### 3. Execute Loop

For each step in the implementation plan:

```
┌─────────────────────────────────────────────┐
│  DO THE WORK                                │
│  - Implement the checklist item             │
│  - Update work item: add execution log      │
├─────────────────────────────────────────────┤
│  VERIFY                                     │
│  - Run automated checks (typecheck, test)   │
│  - Run specific verification for this step  │
├─────────────────────────────────────────────┤
│  PASS?                                      │
│  ├─ YES → Continue to next item             │
│  └─ NO  → Analyze failure, fix, re-verify   │
│           Loop until pass (max 3 attempts)  │
└─────────────────────────────────────────────┘
```

### 3a. Non-Code Execution

Check the `- type:` metadata field. If type is `research`, `writing`, `browser`, `organize`, `manual`, or `ops`, use appropriate tools instead of code editing. If type is not set, fall back to checking if the project ends with `/general` or if the plan contains an `## Artifacts Plan` section.

**Available tools for non-code work:**
- **Web research**: `WebSearch` for searching, `WebFetch` for reading pages
- **Email**: `mcp__claude_ai_Gmail__gmail_search_messages`, `mcp__claude_ai_Gmail__gmail_create_draft`, `mcp__claude_ai_ms365__outlook_email_search`
- **Calendar**: `mcp__claude_ai_ms365__outlook_calendar_search`, `mcp__claude_ai_ms365__find_meeting_availability`
- **Teams**: `mcp__claude_ai_ms365__chat_message_search`
- **SharePoint**: `mcp__claude_ai_ms365__sharepoint_search`, `mcp__claude_ai_ms365__read_resource`
- **Meeting transcripts**: `mcp__claude_ai_Fireflies__fireflies_search`, `mcp__claude_ai_Fireflies__fireflies_fetch`
- **Browser automation**: `mcp__claude-in-chrome__*` tools for navigating, filling forms, clicking buttons
- **File creation**: For Word/PowerPoint artifacts, note the output location for manual OneDrive save

**Writing artifacts to the work item:**

When producing text artifacts (research summaries, drafts, notes), write them to the `## Artifacts` section of the work item using the `Edit` tool:

```
Edit(file_path="$WORK_ITEM_PATH",
     old_string="## Artifacts\n",
     new_string="## Artifacts\n\n### [Artifact Title]\n[Content here]\n")
```

If the work item doesn't have an `## Artifacts` section yet, add one before the `## Execution Log` section:

```
Edit(file_path="$WORK_ITEM_PATH",
     old_string="## Execution Log",
     new_string="## Artifacts\n\n### [Artifact Title]\n[Content here]\n\n## Execution Log")
```

**Verification for non-code items:**
- Skip `npm run typecheck`, `npm run lint`, `npm run test` — these don't apply
- Instead verify: artifacts are present, actions were completed, success criteria are met

### 3b. Ops Hybrid Execution

For `ops` type items, use a hybrid execution model where read-only commands run automatically but mutating commands require user confirmation.

**Read-only commands** (run automatically via `Bash` tool):
- Verbs: `list`, `show`, `get`, `describe`, `view`, `status`, `ps`, `logs`, `inspect`, `info`, `check`, `whoami`, `version`
- Examples: `az resource list`, `az group show`, `gh repo view`, `docker ps`, `kubectl get pods`, `az account show`

**Mutating commands** (require user confirmation):
- Verbs: `create`, `delete`, `update`, `apply`, `deploy`, `run`, `edit`, `set`, `remove`, `destroy`, `start`, `stop`, `restart`, `scale`, `push`, `tag`
- Examples: `az group create`, `az webapp create`, `gh repo edit`, `docker run`, `kubectl apply -f`, `az webapp restart`

**Execution flow for each command in the plan:**

1. Parse the command to identify if it's read-only or mutating
2. **If read-only**: Execute immediately via `Bash` tool, log the result
3. **If mutating**: Present the command to the user via `AskUserQuestion`:
   ```
   AskUserQuestion: "Run this command? `az group create --name mygroup --location eastus`"
   Options: ["Yes, run it", "Skip this command"]
   ```
4. If user approves: Execute via `Bash` tool, log the result
5. If user skips: Log that the command was skipped, continue to next step

**Heuristic for classifying commands:**
- Check the first argument after the CLI tool name (e.g., `az resource list` → `list` = read-only)
- For compound commands like `az webapp deployment`, check the final verb
- When in doubt, treat as mutating and prompt the user

### 4. Update Work Item Progress

After completing each major step, update the execution log using the `Edit` tool.

Find the last entry in the `## Execution Log` section and append the new entry after it:
```
Edit(file_path="$WORK_ITEM_PATH",
     old_string="- [last existing log entry]",
     new_string="- [last existing log entry]\n- [timestamp] Completed: [step description]")
```

### 5. Verify Success Criteria

After all implementation steps, verify each success criterion:

```
For each criterion in Success Criteria:
  - Run its verification method
  - If PASS: mark as [x], continue
  - If FAIL:
    - Log the failure in Execution Log
    - Analyze what's wrong
    - Fix the issue
    - Re-run verification
    - Max 3 fix attempts per criterion
```

Update the success criteria checkboxes in the work item:
- `[ ]` → `[x]` for completed criteria

### 5a. Execute Browser Verification (if present)

If the work item contains a `## Browser Verification` section, execute those steps using the Chrome plugin.

**Process:**
1. Ensure dev server is running (check prerequisites in Browser Verification section)
2. Get tab context: `mcp__claude-in-chrome__tabs_context_mcp`
3. Create a new tab: `mcp__claude-in-chrome__tabs_create_mcp`
4. For each verification step:
   - **Navigate**: Use `mcp__claude-in-chrome__navigate` to go to URLs
   - **Find elements**: Use `mcp__claude-in-chrome__find` to locate elements by description
   - **Read page**: Use `mcp__claude-in-chrome__read_page` to get page structure
   - **Interact**: Use `mcp__claude-in-chrome__computer` for clicks, typing, etc.
   - **Screenshot**: Use `mcp__claude-in-chrome__computer` with action "screenshot" to capture state
5. Log results in execution log

**Example execution:**
```
1. Navigate to http://localhost:$DEV_PORT/dashboard (use port from step 2c; default 3000)
   → mcp__claude-in-chrome__navigate(url="http://localhost:$DEV_PORT/dashboard", tabId=X)

2. Verify "Work Items" heading is visible
   → mcp__claude-in-chrome__find(query="Work Items heading", tabId=X)
   → If found: PASS, if not found: FAIL

3. Click "New" button
   → mcp__claude-in-chrome__find(query="New button", tabId=X)
   → mcp__claude-in-chrome__computer(action="left_click", ref="ref_X", tabId=X)

4. Verify modal appears
   → mcp__claude-in-chrome__read_page(tabId=X)
   → Check for modal elements in response
```

**On verification failure:**
- Log the failure with screenshot if possible
- Attempt to fix the issue (max 3 attempts)
- If still failing after 3 attempts, mark as blocked

### 6. Transition to Review

When ALL success criteria are verified:

Update status using the `Edit` tool:
```
Edit(file_path="$WORK_ITEM_PATH", old_string="- status: planned", new_string="- status: review")
```

Add completion entry to execution log:
```markdown
- [timestamp] All success criteria verified
- [timestamp] Ready for /flywheel:done
```

### 7. Report

```markdown
## Execution Complete

### Success Criteria Results
| # | Criterion | Result |
|---|-----------|--------|
| 1 | [criterion] | ✅ |
| 2 | [criterion] | ✅ |

### Summary
- Implementation steps completed: X/Y
- Issues encountered and fixed: [list]

### Work Item Status
- File: [filename]
- Status: review

### Next Steps
**STOP HERE** - Human review required before shipping.

When ready, manually run `/flywheel:done` to commit, push, create PR, and archive.
```

## Human Review Gate

**CRITICAL**: This skill NEVER automatically invokes `/flywheel:done`, even in unattended mode.

The `review` status is a deliberate checkpoint requiring human verification before code is shipped. This ensures:
- A human reviews the changes before they go to production
- Unattended automation doesn't accidentally ship broken or unwanted code
- The user has a chance to test, review diffs, or make adjustments

**Do NOT:**
- Invoke `/flywheel:done` or the `flywheel:done` skill
- Suggest that the next step will happen automatically
- Chain to any shipping/commit/push operations

**Always:**
- Stop execution after transitioning to `review` status
- Wait for explicit human command to proceed with `/flywheel:done`

## Rules

1. **Don't ask permission between steps** - keep working until blocked or complete
2. **Always update the work item** - execution log should tell the full story
3. **Fix failures immediately** - don't skip and continue
4. **Log everything** - timestamps and descriptions for each step
5. **Stop after 3 failed attempts** on same issue - report what's blocking

## If Blocked

Stop and report clearly:

```markdown
## Blocked

**Issue:** [What's preventing progress]
**Attempts:** [What was tried]
**Need:** [What input/decision is required]
```

Update the work item using the `Edit` tool:
```
Edit(file_path="$WORK_ITEM_PATH", old_string="- status: planned", new_string="- status: blocked")
```

Then append to the Execution Log section using `Edit`:
```
Edit(file_path="$WORK_ITEM_PATH", old_string="## Execution Log", new_string="## Execution Log\n- [timestamp] BLOCKED: [reason]")
```
Note: Append the new log entry after the last existing entry in the Execution Log section.

## Status Transitions

```
planned → review
```

Or if blocked:
```
planned → blocked
```

## Arguments

- `/flywheel:execute` - Run the full plan
- `/flywheel:execute step N` - Run only step N
- `/flywheel:execute verify` - Only run verification, no implementation
- `/flywheel:execute resume` - Continue from last logged progress

## If Work Item Not Planned

If status is `new`:
- Suggest running `/flywheel:define` first

If status is `defined`:
- Suggest running `/flywheel:plan` first

If status is already `review` or `done`:
- Show that execution is complete
- Suggest running `/flywheel:done`
