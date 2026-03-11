---
description: Define work item goals and success criteria
---
# Flywheel: Define Work Item

Ask clarifying questions, define success criteria, and transition a work item from `new` → `defined`.

## DEFINITION MODE ONLY - NO CODE

**CRITICAL**: This command defines goals and success criteria. It does NOT implement anything.

**DO NOT:**
- Write or modify any code files (`.ts`, `.tsx`, `.js`, `.json`, `.css`, etc.)
- Create components, functions, or tests
- Execute any implementation steps
- Create PLAN.md or implementation plans

**ONLY modify:**
- The work item `.md` file in `work/`

The implementation will happen later via `/flywheel:plan` and `/flywheel:execute`.

---

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
4. If multiple files match, pick the most recently modified file (latest date prefix in filename). If still ambiguous, ask the user which work item to use.
5. Use `Read` to read the matching work item file

Read the work item to understand the initial description.

**Subfolder Focus:** If the work item has a `subfolder` field in its metadata, your focus is that directory within the project. The prompt file (if present) will include this context. When working directly with the work item, check for `- subfolder:` in the metadata and focus your work on that directory.

### 2. Confirm or Set Work Item Type

Check if the work item already has a `- type:` field in its metadata.

**If type is already set** (from `/flywheel:new`):
- Note it, but confirm it still makes sense given the clarifying questions below
- If it doesn't fit, update it

**If type is NOT set:**
- Infer the type from the description and conversation context
- Set it during the update in step 4

**Valid types:**
- `code` — standard dev work (default if project is a code repo)
- `research` — gather info, synthesize findings
- `writing` — draft emails, docs, proposals
- `browser` — admin tasks, forms, tickets
- `organize` — break down into sub-items
- `manual` — user handles it, flywheel just tracks
- `ops` — infrastructure provisioning and operational CLI tasks (az, gh, docker, kubectl)

### 3. Ask Clarifying Questions

The goal is to deeply understand what success looks like. Ask about:

- **Scope**: What's included? What's explicitly out of scope?
- **Constraints**: Any technical limitations, deadlines, or requirements?
- **Dependencies**: Does this depend on or affect other work?
- **Acceptance**: How will we know this is done?
- **Edge cases**: What unusual situations should we handle?

Example questions:
- "What's the most important outcome of this work?"
- "Are there specific constraints I should know about?"
- "What does 'done' look like for this feature?"
- "Should we handle [edge case]?"

### 4. Define Success Criteria

Based on the conversation, create specific, verifiable success criteria.

**Good criteria:**
- Specific and measurable
- Verifiable with a clear method
- Independent (can be checked individually)
- Complete (cover all aspects of "done")

**Good examples:**
- "GET /items returns 200 with pagination metadata"
- "Login fails with 401 for invalid credentials"
- "All existing tests pass"

**Bad examples (avoid these):**
- "API works correctly" — too vague, not verifiable
- "Good user experience" — not measurable

### 5. Assess Complexity

Based on the success criteria and scope, set the `- effort:` field in work item metadata.

**Complexity heuristic:**
- **low**: Single file change, straightforward, < 3 success criteria
- **medium**: Multiple files, moderate logic, 3-5 success criteria (default)
- **high**: Architectural changes, complex logic, > 5 criteria, cross-system impact

**Signals for higher effort:**
- Number of success criteria (more = higher)
- Cross-file or cross-system changes
- Architectural decisions required
- Edge cases and error handling complexity
- New patterns or abstractions needed

Set `- effort: low|medium|high` in the metadata. This field is read by downstream skills (`/flywheel:plan`, `/flywheel:execute`) and invocation paths (dashboard, scheduler) to calibrate reasoning depth.

### 6. Update the Work Item

Update the work item file with:

1. **Success Criteria section** - filled with defined criteria
2. **Description section** - expanded with clarifications
3. **Notes section** - any important context from discussion
4. **Status** - change from `new` to `defined`
5. **Type** - set `- type:` if not already present (from step 2)
6. **Effort** - set `- effort:` based on complexity assessment (from step 5)
7. **Workflow** - if specified by user, add `workflow: main` or `workflow: worktree`

```markdown
## Success Criteria

- [ ] [Specific, verifiable outcome 1]
- [ ] [Specific, verifiable outcome 2]
- [ ] [Specific, verifiable outcome 3]
- [ ] All tests pass
- [ ] No type errors
```

Add execution log entry:
```markdown
## Execution Log
- [timestamp] Work item created
- [timestamp] Goals defined, success criteria added
```

### 7. Confirm Definition

Report:
```markdown
## Work Item Defined

**File**: [filename]
**ID**: [id]
**Status**: defined

### Success Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]

### Next Steps
Run `/flywheel:plan` to create an implementation plan.
```

### 8. Check for Unattended Mode

After confirming the definition, check if the work item should proceed automatically.

**Check condition:**
1. Work item has `- unattended: true` in metadata

Use the `Grep` tool to check:
```
Grep(pattern="^- unattended: true", path="$WORK_ITEM_PATH")
```
If matches are found, the work item is in unattended mode.

**If unattended mode is set (matches found):**
- Do NOT show "Run `/flywheel:plan`" in Next Steps
- Instead, immediately invoke `/flywheel:plan` using the Skill tool:

```
Use the Skill tool to invoke "flywheel:plan"
```

**If not in unattended mode:**
- Show the standard "Run `/flywheel:plan`" message and stop

## Status Transition

```
new → defined
```

This command ONLY performs this single status transition.

## What This Command Does NOT Do

**NEVER:**
- Write or modify code files (`.ts`, `.tsx`, `.js`, `.json`, `.css`, etc.)
- Create implementation plans (that's `/flywheel:plan`)
- Execute any code changes (that's `/flywheel:execute`)
- Use the Edit or Write tools on non-markdown files
- Create new files in `src/`, `app/`, `lib/`, or any code directory

**ONLY:**
- Read files to understand context
- Ask clarifying questions
- Update the work item markdown file with success criteria
- Change the work item status from `new` to `defined`

## Tips for Good Success Criteria

1. **Start with the end**: What would make you say "yes, this is done"?
2. **Be specific**: Include exact values, endpoints, behaviors
3. **Include verification**: How will you test each criterion?
4. **Don't forget basics**: Tests pass, no type errors, no lint errors
5. **Consider edge cases**: Error handling, empty states, boundary conditions

## If Work Item Already Defined

If status is already `defined` (or later):
- Show current success criteria
- Ask if they want to revise them
- If yes, update criteria and keep status as `defined`
- If no, suggest running `/flywheel:plan`
