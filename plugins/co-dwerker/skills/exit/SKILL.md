---
name: exit
description: Use when the user is done for the day, wrapping up, stopping work, or ending a co-dwerker session — persists state, updates the project board, saves memories, and writes a summary so the next session can resume. Also use for "let's stop here", "save where we are", or "wind down".
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py *)
---

# Co-Dwerker: Exit

Wind down a work session so the next one, whenever and however it starts, can reconstruct the
full picture. Several systems each hold part of that picture, so this skill writes to all of
them:

1. The local state file (`.co-dwerker.state.json`) — machine-readable resume point
2. The GitHub Projects board (project mode) — shared, human-visible status
3. Auto-memory (`~/.claude/projects/<project>/memory/`) — durable facts and learnings
4. Project status files (`.co-dwerker.json`, `CLAUDE.md`, `project_state.md`)
5. Episodic memory — the searchable conversation record

Shared conventions, environment variables, and file schemas:
`${CLAUDE_PLUGIN_ROOT}/references/conventions.md`. `CK="${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py"`.

## 1. Gather the session facts

Start from `$CK show`, which prints the live `progress` block (active issue, phase, step, and the
context keys: branch, worktree, PRs, planned issues, local-app skip reasons), then fill in from
the conversation:

- Issues completed, created (via `/co-dwerker:new-issue`), and still in progress
- PRs created and merged, with URLs
- Branches with uncommitted or unpushed work; open worktrees
- Decisions that affect future work; blockers and follow-ups

## 2. Save the local state file

Update `$STATE_FILE` (schema in conventions §9). Leave the `progress` block exactly as
`checkpoint.py` left it; that is what Resume Check reads. Write `last_session` from the facts
above, plus the top-level `work_mode`, `repo_owner_name`, `repo_local_path`
(`git rev-parse --show-toplevel`), `github_project_number`, `github_project_title`, and
`planned_issues`. Merge into the existing JSON rather than rewriting it from scratch.

If `.gitignore` does not already exclude `.co-dwerker.state.json`, add it.

Also write the global last-repo file so `/co-dwerker:work` can find this repo from anywhere:

```bash
mkdir -p "$HOME/.claude"
printf '{\n  "repo_owner_name": "%s",\n  "repo_local_path": "%s"\n}\n' "$REPO_OWNER_NAME" "$PROJECT_ROOT" > "$GLOBAL_STATE_FILE"
rm -f "$GLOBAL_STATE_FILE_LEGACY"     # pre-v0.3.1 location
```

## 3. Update the project board (project mode only)

```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER_NAME" --format json --limit 100
```

For each issue touched this session make sure the board agrees with reality: completed → Done,
mid-work → In Progress, PR awaiting review → In Review. Only fix discrepancies.

## 4. Save memories

The auto-memory directory is the one whose `MEMORY.md` your system prompt loads for this project.
If you cannot see it there, `ls ~/.claude/projects/*/memory/MEMORY.md` and pick the entry whose
path matches this repo (`autoMemoryDirectory` in settings can relocate it, so do not derive the
path by hand).

**Project status memory.** Create or update `<project-name>.md`:

```markdown
---
name: <Project Name> Status
description: Current development state for <project> — active issues, branches, next steps
type: project
---

## Current State (as of $TODAY)
- **Active issue:** #<n> — <title> (Phase <p>, step <s>)
- **Branch / worktree:** <branch> / <path or none>
- **PRs open:** #<n> (<status>)
- **Next up:** #<a>, #<b>

## Session History
- $TODAY: <one or two sentences on what was accomplished>

**Why:** Enables session continuity across Claude Code conversations.
**How to apply:** Read this at session start to resume context.
```

**Learnings.** Save only what a future session cannot derive from code, git history, or docs:
workflow adjustments the user asked for (type `feedback`, with the reason), external resources
discovered (type `reference`), non-obvious dependencies between issues or deadlines (type
`project`). Add a one-line pointer in `MEMORY.md` for every new file.

## 5. Update project status files

**`.co-dwerker.json`** — create on first session, otherwise merge. Other steps own
`local_app_command`, `local_app_skip`, and `dismissed_warnings`; read the file first and preserve
them. If no docs repo is known yet, ask once: "Does this project have a companion documentation
repo? If so, what is the org/repo and the path within it for this project's docs?" Write `null`
for both fields if not.

**`CLAUDE.md`** — if project conventions changed (new test or lint commands, run commands), update
the relevant section.

**`project_state.md`** — if the project keeps one, refresh status, open PRs, active branches.

## 6. Leave a searchable session record

The episodic-memory plugin indexes the conversation itself. Put a structured summary in plain
text in the conversation (not in a file) so future searches find it: project and board, date,
issues worked with outcomes, PRs with URLs and status, key decisions, blockers, what to start
with next session, and anything surprising that was learned.

## 7. Git hygiene

```bash
git status --short
git branch --list
git worktree list
git stash list
```

- Uncommitted meaningful work → offer a WIP commit (ask; do not just do it). Scratch changes →
  note them.
- Branches with no open PR → list them; do not delete anything.
- Worktrees → list them, marking which came from this session.

## 8. Exit summary

Concise, but complete enough that tomorrow's reader knows exactly where things stand:

> **Session Summary — $TODAY** ($WORK_MODE mode on $REPO_OWNER_NAME)
>
> **Completed:** Issue #n: title (PR #p merged)
> **Created:** Issue #n: title (priority / status)
> **In progress:** Issue #n: title — Phase p, step s (branch `b`); next step: …
> **Tomorrow's starting point:** resume #n at Phase p step s, then #a, #b
> **Open items:** blockers, pending reviews, follow-ups
