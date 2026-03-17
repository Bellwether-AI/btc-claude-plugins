---
description: Process permission requests and write to settings
---
# Flywheel: Process Permission Requests

Read collected permission request logs, derive well-scoped permission entries, and write them to `settings.local.json` with user approval.

## Process

### 1. Fetch the Permission Log

Fetch recent permission request events from the Flywheel cloud API:

```
WebFetch(url="https://www.flywheelgsd.com/api/permissions/log")
```

If the request fails or returns a non-200 status, report "Could not reach the Flywheel API at https://www.flywheelgsd.com/api/permissions/log — check your connection." and stop.

The response is a JSON array of event objects, each with:
- `timestamp`: when the request occurred
- `toolName`: the tool name (Bash, Read, Edit, Write, WebFetch, etc.)
- `toolInput`: the tool input object
- `cwd`: working directory where the request happened
- `project`: project directory name
- `sessionName`: Claude session name

If the response is an empty array, report "No permission requests found." and stop.

### 2. Derive Permission Strings

For each log entry, derive a Claude Code permission string using these rules:

**Bash tool:**
- Extract the command from `toolInput.command`
- Use the first word (or first two words for compound commands like `git status`) as the prefix
- Format: `Bash(prefix:*)`
- Examples: `npm run build` → `Bash(npm run build:*)`, `git status` → `Bash(git status:*)`

**Read tool:**
- Extract the file path from `toolInput.file_path`
- Replace the specific file with `**` at the directory level
- Use `~/` prefix where possible (replace `/Users/<username>/` with `~/`)
- Format: `Read(~/path/to/dir/**)`

**Edit tool:**
- Same as Read but with Edit prefix
- Format: `Edit(~/path/to/dir/**)`

**Write tool:**
- Same as Read but with Write prefix
- Format: `Write(~/path/to/dir/**)`

**WebFetch tool:**
- Extract the URL from `toolInput.url`
- Derive the domain
- Format: `WebFetch(domain:example.com)`

**WebSearch tool:**
- Format: `WebSearch`

**Skill tool:**
- Extract skill name from `toolInput.skill`
- Format: `Skill(skill-name)`

**Other tools:**
- Use the tool name with a reasonable pattern from the input
- Format: `ToolName(pattern)`

### 3. Worktree Path Normalization

For any path containing `-worktrees/`:
1. Extract the base repo name: `/path/to/repo-worktrees/branch/` → `repo`
2. Generate TWO permission entries:
   - Base repo: e.g., `Read(~/personal/flywheel/**)`
   - Worktrees glob: e.g., `Read(~/personal/flywheel-worktrees/**)`

For paths NOT in a worktree, derive a single permission entry using the directory path.

When normalizing paths:
- Replace `/Users/<username>/` with `~/`
- Go up to a reasonable directory level (project root, not individual files)
- Use `**` glob suffix for directory-level permissions

### 4. Deduplicate and Count

- Group identical permission strings together
- Count occurrences of each
- Sort by frequency (most common first)

### 5. Filter Existing Permissions

Ask the user which scope to check and write to:

```
Which settings scope should I work with?
1. Project .claude/settings.local.json (current project only)
2. Global ~/.claude/settings.local.json (writes to all 4 locations: global + personal/bellwether/sophia areas)
3. Show proposals only (don't write)
```

**Note on Global scope**: When "Global" is selected, rules are written to `~/.claude/settings.local.json` AND all three area settings files (`~/.claude-personal/`, `~/.claude-bellwether/`, `~/.claude-sophia/`). This is necessary because `CLAUDE_CONFIG_DIR` replaces `~/.claude/` in area sessions via direnv.

Use the AskUserQuestion tool with these options.

Then read the target `settings.local.json` file and filter out any permission strings that already exist in the `permissions.allow` array.

### 6. Present Proposals

Display the proposed new permissions grouped by tool type:

```markdown
## Proposed Permission Entries

### Bash (X new)
| # | Permission | Occurrences |
|---|-----------|-------------|
| 1 | `Bash(npm run dev:*)` | 5 |
| 2 | `Bash(docker compose:*)` | 3 |

### Read (X new)
| # | Permission | Occurrences |
|---|-----------|-------------|
| 1 | `Read(~/personal/project/**)` | 12 |

### Already Exists (filtered out)
- `Bash(git status:*)` (already in settings)
- `Read(./**)` (already in settings)

**Total: X new entries to add**
```

If there are no new entries to add, report that and stop.

### 7. Confirm and Write

Ask the user to confirm using AskUserQuestion:

```
Add these X permission entries to [scope] settings.local.json?
1. Yes, add all
2. Let me select which ones
3. Cancel
```

If "Let me select which ones": list each entry and let the user choose (use AskUserQuestion with multiSelect).

If confirmed:
1. Read the target `settings.local.json`
2. Parse the JSON
3. Add the new entries to `permissions.allow`
4. Write the file back with proper formatting (2-space indent)
5. **If Global scope**: also write the same entries to all 3 area settings files (`~/.claude-personal/settings.local.json`, `~/.claude-bellwether/settings.local.json`, `~/.claude-sophia/settings.local.json`), preserving existing area-specific rules

## Important Notes

- NEVER write permissions without explicit user confirmation
- Always show what will be written before writing
- Preserve existing entries in settings.local.json — only append
- Use proper JSON formatting when writing settings files
- The `permissions.deny` array should never be modified by this skill
- If `settings.local.json` doesn't exist at the target path, create it with the structure: `{"permissions": {"allow": []}}`
