---
description: Create a new Flywheel work item
---
# Flywheel: New Work Item

Create a new work item in Flywheel with status `new`.

## Environment

```bash
FLYWHEEL_PATH="$HOME/.flywheel"
TODAY=$(date +%Y-%m-%d)
```

## Process

### 1. Gather Basic Info

Ask: "What would you like to work on?"

Collect:
- **Title**: Clear, concise description of the work
- **Project**: Which project is this for?
- **Priority**: low | medium | high | critical
- **Type** (optional): code | research | writing | browser | organize | manual
  - If not specified, infer from context or leave unset for `/flywheel:define` to determine
  - `code` — standard dev work (default if project is a code repo)
  - `research` — gather info, synthesize findings
  - `writing` — draft emails, docs, proposals
  - `browser` — admin tasks, forms, tickets
  - `organize` — break down into sub-items
  - `manual` — user handles it, flywheel just tracks
  - `ops` — infrastructure provisioning and operational CLI tasks (az, gh, docker, kubectl)

Don't ask for success criteria yet - that's the `/flywheel:define` step.

### 2. Determine Target Project

Infer from conversation or ask:
- `bellwether/BellwetherPlatform`
- `sophia/Sophia.Core`
- `sophia/Sophia.Api`
- `personal/[project-name]`
- Other (specify path)

### 3. Generate Work Item ID

Format: `[short-name]-[random-3-digits]`
Example: `auth-refactor-042`, `api-pagination-718`

### 4. Create Work Item

Create file at: `$FLYWHEEL_PATH/work/[TODAY]-[short-description].md`

```markdown
# [Clear Title]

## Metadata
- id: [generated-id]
- project: [target-project-path]
- priority: [low|medium|high|critical]
- created: [TODAY]
- status: new
- source: cli
- type: [code|research|writing|browser|organize|manual|ops] (omit if not specified)
- effort: [low|medium|high] (omit - set by /flywheel:define)
- unattended: true
- assigned-session:

## Description

[Brief description of what needs to be done]

## Success Criteria

[To be defined - run /flywheel:define]

## Notes

[Any initial context from the conversation]

## Execution Log

- [timestamp] Work item created
```

### 5. Confirm Creation

```bash
ls -la "$FLYWHEEL_PATH/work/"
```

Report:
```markdown
## Work Item Created

**File**: [filename]
**ID**: [id]
**Project**: [project]
**Priority**: [priority]
**Status**: new

### Next Steps
Run `/flywheel:define` to define success criteria and goals.
```

## Priority Guidelines

| Priority | When to Use |
|----------|-------------|
| critical | Production issues, blocking other work |
| high | Important features, significant bugs |
| medium | Standard development work |
| low | Nice to have, refactoring, tech debt |

## Work Item Naming

File naming: `YYYY-MM-DD-short-description.md`
- Use lowercase
- Use hyphens for spaces
- Keep it short but descriptive
- Include date for sorting

Examples:
- `2025-01-20-add-user-auth.md`
- `2025-01-20-fix-pagination-bug.md`
- `2025-01-20-refactor-api-routes.md`

## Execution Order

When creating multiple work items that must execute in a specific sequence, prefix each title with a sequential integer followed by a period. This ensures the items are processed in the correct order.

**Format:** `N. [Title]`

**Examples:**
- `1. Set up database schema`
- `2. Build API endpoints`
- `3. Add frontend forms`

This produces files like:
- `2025-01-20-1-set-up-database-schema.md`
- `2025-01-20-2-build-api-endpoints.md`
- `2025-01-20-3-add-frontend-forms.md`

## Unattended Mode

New work items default to `- unattended: true`. This means after creation, the work item automatically proceeds through the full workflow (`/flywheel:define` → `/flywheel:plan` → `/flywheel:execute`) without pausing for user input between steps.

**IMPORTANT:** Unattended mode is NOT fully autonomous. Execution stops at `review` status for human verification before shipping. The user always reviews changes before they are committed and pushed. This is a safety guardrail — `unattended: true` is safe to use for all work items.

Set `- unattended: false` only if you want manual control, requiring the user to explicitly invoke each step. This is rarely needed.
