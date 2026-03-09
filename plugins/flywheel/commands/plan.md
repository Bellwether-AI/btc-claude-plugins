# Flywheel: Create Implementation Plan

Explore the codebase, design an implementation approach, and transition a work item from `defined` → `planned`.

## PLANNING MODE ONLY - NO IMPLEMENTATION

**CRITICAL**: This command creates an implementation PLAN, not actual code.

**DO NOT:**
- Write or modify any code files (`.ts`, `.tsx`, `.js`, `.json`, `.css`, etc.)
- Create components, functions, or tests
- Execute any implementation steps
- Use the Edit or Write tools on non-markdown files
- Create new files in `src/`, `app/`, `lib/`, or any code directory

**ONLY modify:**
- The work item `.md` file in `work/`

The plan will be executed later by `/flywheel:execute`.

---

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

Or find a `defined` work item:

1. Use `Grep(pattern="^- status: defined", path="$FLYWHEEL_PATH/work/")` to find work items with status `defined`
2. Use `Read` to read the matching work item file

Read the work item to understand the success criteria.

**Check effort level:** Look for `- effort:` in the work item metadata. If effort is `high`, note this — the plan should reflect thorough reasoning: "This is a high-complexity work item requiring thorough reasoning and careful architectural consideration."

### 2. Explore the Codebase

Before planning, understand the current architecture:

- **Find relevant files**: Search for related code, components, modules
- **Understand patterns**: How are similar features implemented?
- **Identify dependencies**: What existing code will this interact with?
- **Note conventions**: Naming, file structure, testing patterns

Use dedicated tools for exploration (no Bash needed):
- `Glob(pattern="src/**/*.ts")` to find files
- `Grep(pattern="relatedFunction", glob="*.ts")` to search for code patterns
- `Read(file_path="src/relevant-file.ts")` to read file contents

### 3. Design Implementation Approach

Based on exploration, design how to achieve each success criterion:

- What files need to be created or modified?
- What's the order of operations?
- Are there any technical decisions to make?
- What verification will prove each step works?

### 3a. Detect Frontend Changes

Determine if this work item involves frontend/UI changes. Look for indicators in the work item description and success criteria:

**Frontend indicators:**
- Mentions of: UI, dashboard, components, pages, styling, CSS, layout, visual, user-facing, buttons, forms, modals, cards, tables, navigation, responsive
- File patterns: `*.tsx`, `*.jsx`, `*.css`, `*.scss`, `app/`, `components/`, `pages/`
- Frameworks: React, Next.js, Tailwind, styled-components

**If frontend changes are detected:**
- The implementation plan MUST include a `## Browser Verification` section
- This section will be executed by `/flywheel:execute` using the Chrome plugin
- Without this section, frontend changes cannot be visually verified

### 3b. Detect Non-Code Tasks

Check the `- type:` metadata field to determine the task type.

**Type-based detection:**
- `code` or not set → standard code planning (default behavior)
- `research` → plan focuses on sources to consult and findings to produce
- `writing` → plan focuses on content to draft and where to deliver it
- `browser` → plan focuses on URLs to visit and actions to take
- `organize` → plan focuses on how to break down into sub-items
- `manual` → plan focuses on what the user needs to do (checklist only)
- `ops` → plan focuses on CLI commands to run, distinguishing read-only from mutating operations

**If type is not set**, infer from description indicators:
- research, email, writing, drafting, browser task, admin, meeting, organize, planning, proposal, document, presentation, review, analysis, summary
- Project identifier ends with `/general` (catchall projects)

**If non-code task detected:**
- The implementation plan should focus on **what to do** rather than **what code to write**
- Specify which tools to use: WebSearch, WebFetch, Gmail MCP, Outlook MCP, Teams MCP, SharePoint MCP, Fireflies MCP, Chrome browser automation
- Include an `## Artifacts Plan` section specifying:
  - What text artifacts to write to the work item's `## Artifacts` section
  - What file artifacts (Word, PowerPoint) to save to OneDrive
- Verification is based on artifacts produced and actions completed, not code tests

**Non-code plan format:**
```markdown
## Implementation Plan

### Phase 1: [Research/Gather/Draft/etc.]

1. **[Action title]**
   - Tool: [WebSearch | Gmail | Outlook | Teams | SharePoint | Fireflies | Browser]
   - Action: [What to search/fetch/draft/submit]
   - Output: [What artifact this produces]

### Artifacts Plan

**Work item artifacts (## Artifacts section):**
- [Research summary / draft text / meeting notes / etc.]

**OneDrive artifacts:**
- [Word doc / PowerPoint / etc. if applicable]
```

**Ops plan format:**

For `ops` type items, the plan should list CLI commands grouped by phase, each marked as READ-ONLY or MUTATING:

```markdown
## Implementation Plan

### Phase 1: [Discover/Audit/etc.]

1. **[Action title]** (READ-ONLY)
   - Command: `az resource list --resource-group mygroup`
   - Purpose: [What info this gathers]

2. **[Action title]** (MUTATING)
   - Command: `az group create --name mygroup --location eastus`
   - Purpose: [What this changes]
   - Confirm: Yes — user must approve before execution

### Phase 2: [Provision/Configure/etc.]

3. **[Action title]** (MUTATING)
   - Command: `gh repo edit --enable-issues`
   - Purpose: [What this changes]
   - Confirm: Yes
```

Key rules for ops plans:
- Mark every command as READ-ONLY or MUTATING
- READ-ONLY commands (list, show, get, describe, view, status, ps, logs) run automatically
- MUTATING commands (create, delete, update, apply, deploy, run, edit, set, remove, destroy) require user confirmation via `AskUserQuestion`
- Group related commands into logical phases

### 4. Create the Implementation Plan

Update the work item with a detailed plan:

```markdown
## Implementation Plan

### Phase 1: [Description]

1. **[Step title]**
   - [Specific action]
   - [Files affected]
   - [Verification]

2. **[Step title]**
   - [Specific action]
   - [Files affected]
   - [Verification]

### Phase 2: [Description]

3. **[Step title]**
   ...

### Verification

- [How to verify the implementation is complete]
- [Commands to run: tests, typecheck, lint]
```

**If frontend changes detected, also include:**

```markdown
## Browser Verification

**Prerequisites:**
- Dev server running at: [URL, e.g., http://localhost:3000]
- Chrome plugin (Claude in Chrome) must be available

**Steps:**
1. Navigate to [URL/path]
2. Verify [element/component] is visible
3. [Click/interact with element]
4. Verify [expected outcome]

**Example steps:**
- Navigate to http://localhost:3000/dashboard
- Verify "Work Items" heading is visible
- Verify work item cards are displayed
- Click "New" button
- Verify modal appears with form fields
```

The browser verification section is REQUIRED for any work item involving frontend changes. During `/flywheel:execute`, these steps will be executed using the Chrome plugin (`mcp__claude-in-chrome__*` tools).

### 5. Update Work Item Status

Change status from `defined` to `planned`:

Use the `Edit` tool:
```
Edit(file_path="$WORK_ITEM_PATH", old_string="- status: defined", new_string="- status: planned")
```

Add execution log entry:
```markdown
## Execution Log
- [timestamp] Work item created
- [timestamp] Goals defined, success criteria added
- [timestamp] Implementation plan created
```

### 6. Report

```markdown
## Plan Created

**Work Item**: [filename]
**Status**: planned

### Implementation Plan Summary
- Phase 1: [description]
- Phase 2: [description]
- ...

### Files to Modify
- [list of files]

### Next Steps
Run `/flywheel:execute` to implement the plan.
```

### 7. Check for Unattended Mode

After reporting the plan, check if the work item should proceed automatically.

**Check condition:**
1. Work item has `- unattended: true` in metadata

Use the `Grep` tool to check:
```
Grep(pattern="^- unattended: true", path="$WORK_ITEM_PATH")
```
If matches are found, the work item is in unattended mode.

**If unattended mode is set (matches found):**
- Do NOT show "Run `/flywheel:execute`" in Next Steps
- Instead, immediately invoke `/flywheel:execute` using the Skill tool:

```
Use the Skill tool to invoke "flywheel-execute"
```

**If not in unattended mode:**
- Show the standard "Run `/flywheel:execute`" message and stop

## Status Transition

```
defined → planned
```

This command ONLY performs this single status transition.

## What This Command Does NOT Do

**NEVER:**
- Write or modify code files (`.ts`, `.tsx`, `.js`, `.json`, `.css`, etc.)
- Define success criteria (that's `/flywheel:define`)
- Execute the plan (that's `/flywheel:execute`)
- Use the Edit or Write tools on non-markdown files
- Create new files in `src/`, `app/`, `lib/`, or any code directory

**ONLY:**
- Read files to understand codebase structure and patterns
- Update the work item markdown file with the implementation plan
- Change the work item status from `defined` to `planned`

## Plan Requirements

A good plan includes:

1. **Specific steps**: Exactly what to do, not vague directions
2. **File references**: Which files to create/modify
3. **Order of operations**: Dependencies between steps
4. **Verification**: How to confirm each step is complete
5. **Phases**: Group related steps together

## If Work Item Not Defined

If status is `new`:
- Suggest running `/flywheel:define` first
- Don't try to create a plan without clear success criteria

If status is already `planned` (or later):
- Show existing plan
- Ask if they want to revise it
- If yes, update plan and keep status as `planned`
- If no, suggest running `/flywheel:execute`
