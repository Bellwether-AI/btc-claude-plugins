# Flywheel: New Work Item

Create a new work item in Flywheel with status `new`.

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
- `my-org/MyProject`
- `team-a/ServiceApi`
- `team-b/SharedLib`
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

## Key Differences from Previous `/flywheel:plan`

- **Minimal info gathering** - just title, project, priority
- **No success criteria** - that comes in `/flywheel:define`
- **No implementation details** - that comes in `/flywheel:plan`
- **Status is `new`** - not `ready` or `defined`

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

New work items default to `- unattended: true`. This means after creation, the work item automatically proceeds through the full workflow (`/flywheel:define` → `/flywheel:plan` → `/flywheel:execute`) without pausing for user input between steps. Execution still stops at `review` status for human verification before shipping.

Set `- unattended: false` if you want manual control, requiring the user to explicitly invoke each step.
