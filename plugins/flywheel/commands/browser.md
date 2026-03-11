---
description: Perform browser-based admin tasks, forms, and tickets using Chrome automation
---
# Flywheel: Browser Tasks

Perform administrative tasks, fill out forms, file tickets, and complete browser-based work using Chrome automation.

## Environment

```bash
FLYWHEEL_PATH="$HOME/.flywheel"
```

## Prerequisites

The Chrome browser automation tools (`mcp__claude-in-chrome__*`) must be available:
- Chrome browser must be running
- Claude in Chrome extension must be installed and active
- MCP connection must be established

**Check availability before starting:**
1. Call `mcp__claude-in-chrome__tabs_context_mcp`
2. If it succeeds, proceed
3. If it fails, report that Chrome plugin is unavailable and stop

## Process

### 1. Load the Work Item

Check for a prompt file first (launched from dashboard):

1. Use `Glob(pattern=".flywheel-prompt-*.txt")` to find prompt files in the current directory
2. If found, use `Read` to read the prompt file contents

Or find the active work item:

1. Use `Grep(pattern="^- status: planned", path="$FLYWHEEL_PATH/work/")` to find work items
2. Use `Read` to read the matching work item file

Extract:
- What browser task to perform
- Which URL(s) to visit
- What data to enter or actions to take
- What evidence of completion to capture

### 2. Check Chrome Plugin

```
mcp__claude-in-chrome__tabs_context_mcp(createIfEmpty=true)
```

If this fails, report blocked and stop.

### 3. Create a New Tab

```
mcp__claude-in-chrome__tabs_create_mcp()
```

### 4. Execute Browser Task

For each step in the task:

1. **Navigate** to the target URL:
   ```
   mcp__claude-in-chrome__navigate(url="https://...", tabId=X)
   ```

2. **Read the page** to understand the layout:
   ```
   mcp__claude-in-chrome__read_page(tabId=X)
   ```

3. **Find elements** to interact with:
   ```
   mcp__claude-in-chrome__find(query="submit button", tabId=X)
   ```

4. **Fill forms** using form_input:
   ```
   mcp__claude-in-chrome__form_input(ref="ref_1", value="text", tabId=X)
   ```

5. **Click buttons** using computer:
   ```
   mcp__claude-in-chrome__computer(action="left_click", ref="ref_1", tabId=X)
   ```

6. **Take screenshots** as evidence:
   ```
   mcp__claude-in-chrome__computer(action="screenshot", tabId=X)
   ```

7. **Log each action** in the execution log

### 5. Safety Rules

**CRITICAL — Always follow these safety rules:**

- **Never enter passwords** — direct the user to enter passwords themselves
- **Never enter financial information** — credit cards, bank accounts, etc.
- **Confirm before submitting** — always pause and ask before clicking submit/send/purchase buttons
- **Never create accounts** — direct the user to create accounts themselves
- **Never modify permissions** — sharing settings, access controls, etc.
- **Screenshot evidence** — take screenshots before and after important actions
- **Respect bot detection** — never attempt to bypass CAPTCHAs

### 6. Write Evidence to Artifacts

After completing the browser task, write a summary to `## Artifacts`:

```markdown
### Browser Task: [Description]

**URL:** [Target URL]
**Date:** [Timestamp]

**Actions Taken:**
1. [Action 1] — [Result]
2. [Action 2] — [Result]
3. [Action 3] — [Result]

**Evidence:**
- Screenshot taken at [step]
- Confirmation number: [if applicable]

**Status:** Completed
```

### 7. Update Work Item

- Mark relevant success criteria as complete `[x]`
- Update execution log with task completion
- If all criteria met, transition to `review` status

### 8. Report

```markdown
## Browser Task Complete

### Actions Taken
- [Summary of what was done]

### Evidence
- [Screenshots, confirmation numbers, etc.]

### Next Steps
Review the evidence and run `/flywheel:done` when satisfied.
```

## Common Browser Tasks

| Task | Approach |
|------|----------|
| Fill out a form | Navigate → read_page → form_input for each field → screenshot → confirm → submit |
| File a ticket | Navigate to ticket system → fill fields → attach files → submit |
| Admin task | Navigate to admin panel → find controls → make changes → screenshot |
| Data entry | Navigate to form → enter data → verify → submit |
| Check status | Navigate → read_page → extract information → write to artifacts |

## Error Handling

- If a page doesn't load: wait 5 seconds, try again (max 2 retries)
- If an element can't be found: take screenshot, try alternative selectors
- If an action fails: log the error, take screenshot, report to user
- If blocked by login: report to user, ask them to log in manually
- After 3 failed attempts on same step: stop and report blocked
