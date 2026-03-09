# Flywheel: Planning & Organizing

Break down a large task into smaller work items, creating sub-items via `/flywheel:new` and linking them to the parent.

## Command Execution Guidelines

**CRITICAL**: Follow these rules to minimize permission prompts:

1. **Use dedicated tools instead of shell equivalents:**
   - `Glob` instead of `find` or `ls` for file discovery
   - `Grep` instead of `grep` or `grep -q` for pattern matching
   - `Read` instead of `cat` for reading files
   - `Edit` instead of `sed -i` for file modifications
2. **One command per Bash call** — never chain with `&&`, `;`, or `||`
3. **Use absolute paths or `git -C`** — never `cd dir && git ...`

## Environment

```bash
FLYWHEEL_PATH="$HOME/.flywheel"
```

## Process

### 1. Load the Work Item

Check for a prompt file first (launched from dashboard):

1. Use `Glob(pattern=".flywheel-prompt-*.txt")` to find prompt files in the current directory
2. If found, use `Read` to read the prompt file contents

Or find the active work item:

1. Use `Grep(pattern="^- status: planned", path="$FLYWHEEL_PATH/work/")` to find work items
2. Use `Read` to read the matching work item file

Extract:
- The high-level task or project to break down
- Any constraints or dependencies
- Priority guidance
- Target project for sub-items

### 2. Analyze the Task

Break down the parent task into logical sub-items:

- **Identify natural boundaries** — separate phases, independent tasks, different skill types
- **Consider dependencies** — which items must complete before others can start?
- **Assign appropriate types** — some sub-items may be code, others research, writing, browser tasks
- **Keep items atomic** — each sub-item should be completable in a single session
- **Set priorities** — critical path items get higher priority

### 3. Present Breakdown to User

Before creating sub-items, present the proposed breakdown:

```markdown
## Proposed Breakdown

**Parent:** [Parent work item title]
**Sub-items:**

1. **[Sub-item title]** — [brief description]
   - Type: [code | research | writing | browser | admin]
   - Priority: [critical | high | medium | low]
   - Dependencies: [none | depends on #X]

2. **[Sub-item title]** — [brief description]
   - Type: [code | research | writing | browser | admin]
   - Priority: [critical | high | medium | low]
   - Dependencies: [none | depends on #1]

3. ...

**Questions:**
- [Any clarification needed before creating items?]

Proceed with creating these work items? (yes/no/modify)
```

Wait for user confirmation before creating items.

### 4. Create Sub-Items

For each approved sub-item, create a work item file:

```bash
# Use the Write tool to create each work item
```

Each sub-item should include:
- Clear title
- Project matching the parent (or different if appropriate)
- Priority as discussed
- Description referencing the parent work item
- Notes section linking back to parent: `Parent: [parent-id]`

**File format:** `$FLYWHEEL_PATH/work/YYYY-MM-DD-[short-description].md`

### 5. Update Parent Work Item

After creating sub-items, update the parent work item:

1. Write the breakdown to `## Artifacts` section:
```markdown
### Sub-Items Created

| # | ID | Title | Priority | Status |
|---|-----|-------|----------|--------|
| 1 | [id] | [title] | [priority] | new |
| 2 | [id] | [title] | [priority] | new |
```

2. Mark relevant success criteria as complete
3. Update execution log

### 6. Report

```markdown
## Breakdown Complete

### Sub-Items Created
1. **[title]** — `work/[filename]` (priority: [X])
2. **[title]** — `work/[filename]` (priority: [X])
3. ...

### Parent Work Item
- Updated with sub-item references in Artifacts section
- Status: [review | done depending on criteria]

### Next Steps
- Sub-items are ready in `work/`
- Run `/flywheel:define` on each to add success criteria
- Or launch them from the dashboard
```

## Tips

- **Don't over-decompose** — 3-7 sub-items is usually right
- **Mix types** — some items may be code, others research or writing
- **Consider parallelism** — independent items can run concurrently
- **Link back** — always reference the parent in sub-item Notes
- **Set realistic priorities** — not everything is critical
