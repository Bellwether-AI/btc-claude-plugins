---
description: Fast-path execution — define, implement, and verify in one shot
---
# Flywheel: Fast Path

Execute a work item from `new` → `review` in a single session. This is the streamlined alternative to the multi-step define → plan → execute pipeline, used for straightforward tasks.

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
3. If no prompt file, use `Grep(pattern="^- status: new", path="$FLYWHEEL_PATH/work/")` to find work items with status `new`
4. If multiple files match, pick the most recently modified file. If still ambiguous, ask the user.
5. Use `Read` to read the matching work item file

**Subfolder Focus:** If the work item has a `- subfolder:` field, scope all work to that directory.

### 2. Understand the Task

Read the work item description carefully. Identify:

- **What needs to change** — the concrete deliverable
- **Where it lives** — which part of the codebase is affected
- **How to verify** — what "done" looks like

Do NOT write formal success criteria or a plan section to the work item. Keep it in your head and go.

### 3. Explore and Implement

In one continuous pass:

1. **Explore** the relevant code to understand current patterns and conventions
2. **Implement** the changes, following existing patterns
3. **Keep changes minimal** — do what the description asks, nothing more

Use dedicated tools (Glob, Grep, Read, Edit, Write) — not shell equivalents.

### 4. Verify

Run the project's verification commands:

```bash
npm run typecheck   # in affected directories (api/, dashboard/, agent/)
npm test            # where applicable
```

If verification fails:
- Analyze the failure
- Fix the issue
- Re-verify
- Max 3 attempts per failure before reporting as blocked

### 5. Browser Verification (if frontend changes)

If the work item involves UI changes:

1. Check for a running dev server
2. Use Chrome plugin tools to navigate and verify the UI changes visually
3. Log results

### 6. Update Work Item and Transition to Review

Using the `Edit` tool, update the work item:

1. Change status from `new` to `review`
2. Add execution log entries summarizing what was done

```
Edit(file_path="$WORK_ITEM_PATH", old_string="- status: new", new_string="- status: review")
```

Append to the execution log:
```markdown
- [timestamp] Fast path: [brief summary of changes made]
- [timestamp] Verification passed, ready for review
```

### 7. Report

```markdown
## Fast Path Complete

### Changes Made
- [List of files modified/created]
- [Brief description of what was done]

### Verification
- Typecheck: PASS/FAIL
- Tests: PASS/FAIL

### Work Item Status
- Status: review

### Next Steps
**STOP HERE** — Human review required before shipping.
When ready, run `/flywheel:done` to commit, push, and create PR.
```

## Human Review Gate

**CRITICAL**: This skill NEVER automatically invokes `/flywheel:done`, even in unattended mode.

The `review` status is a deliberate checkpoint requiring human verification. Do NOT:
- Invoke `/flywheel:done` or the `flywheel:done` skill
- Suggest that the next step will happen automatically
- Chain to any shipping/commit/push operations

## Rules

1. **No formal artifacts** — skip writing success criteria, plan sections, or notes to the work item
2. **Stay focused** — implement exactly what the description asks
3. **Fix failures immediately** — don't skip and continue
4. **Log concisely** — execution log should capture what was done, not the full journey
5. **Stop at review** — always end at `review` status

## If Blocked

```markdown
## Blocked

**Issue:** [What's preventing progress]
**Attempts:** [What was tried]
**Need:** [What input/decision is required]
```

Update status to `blocked` and stop.

## Status Transition

```
new → review
```

This command skips `defined` and `planned` statuses entirely.
