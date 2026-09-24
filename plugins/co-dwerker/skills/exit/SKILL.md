---
name: exit
description: Use when the user is done for the day, wrapping up, stopping work, or ending a co-dwerker session, so the next session can resume where this one stopped. Also use for "let's stop here", "save where we are", "wind down", or "we're done".
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py *)
---

# Co-Dwerker: Exit

Wind down a work session so the next one, whenever and however it starts, can reconstruct the
full picture. Several systems each hold part of that picture, so this skill writes to all of
them:

1. The local state file (`.co-dwerker.state.json`) — machine-readable resume point
2. GitHub issues and, in project mode, the Projects board — what is actually closed and where it sits
3. Auto-memory (`~/.claude/projects/<project>/memory/`) — durable facts and learnings
4. Project status files (`.co-dwerker.json`, `CLAUDE.md`, `project_state.md`)
5. Episodic memory — the searchable conversation record

Conventions §1 (environment, running the scripts), §6 (`gh` errors), and §9 (file schemas):
`${CLAUDE_PLUGIN_ROOT}/references/conventions.md`. `checkpoint.py …` below means
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py …`.

## 1. Gather the session facts

Start from `checkpoint.py show`, which prints the live `progress` block (active issue, phase, step,
and the context keys: branch, worktree, PRs, planned issues, issues created, local-app skip
reasons) and the previous `last_session`. Fill in from the conversation:

- Issues completed, created, and still in progress
- PRs created and merged, with URLs
- Branches with uncommitted or unpushed work; open worktrees
- Decisions that affect future work; blockers and follow-ups

## 2. Save the local state file

```bash
checkpoint.py end-session --repo-owner-name $REPO_OWNER_NAME \
  --completed <issue numbers finished today, comma-separated> \
  --prs-created <numbers> --prs-merged <numbers>
```

Omit any list flag that has nothing to report.

`completed_this_session` already holds every issue `finish-issue` recorded, including the extra
entries of each PR's `resolves_issues`; pass `--completed` only for issues finished outside the
work skill.

This writes `last_session` and the top-level keys from `progress` (leaving `progress` itself
intact for Resume Check), writes the global last-repo file `~/.claude/co-dwerker-last-repo.json`
so `/co-dwerker:work` can find this repo from anywhere, and removes the pre-v0.3.1 global file.
The state file is already kept out of `git status` by `.git/info/exclude`; no `.gitignore` change
is needed.

## 3. Reconcile issues, then the board

Issues first, because a project board with its built-in "Item closed" workflow follows issue
state on its own, and the failure that actually happens is a fixed issue that never closed
(conventions §10).

**Issues.** For every PR merged this session (`--prs-merged`, plus `progress.context.pr_number`
if `gh pr view $N --json state --jq .state` says `MERGED`):

```bash
gh pr view $P --repo "$REPO_OWNER_NAME" --json number,title,body,mergedAt > /tmp/co-dwerker-pr.json
gh issue list --repo "$REPO_OWNER_NAME" --state open --json number,title --limit 200 > /tmp/co-dwerker-open.json
jq -c -n --slurpfile pr /tmp/co-dwerker-pr.json --slurpfile open /tmp/co-dwerker-open.json '
  ($open[0] | map({key: (.number|tostring), value: .title}) | from_entries) as $open
  | $pr[0] as $pr
  | [ ($pr.body // "") | scan("(?:^|[^A-Za-z0-9_/-])#([0-9]+)") | .[0] ] | unique[]
  | select($open[.] != null)
  | {pr: $pr.number, pr_title: $pr.title, merged: $pr.mergedAt[0:10], issue: (.|tonumber), issue_title: $open[.]}'
```

Skip pairs already in `reconcile_dismissed`. List what is left and ask once: **Close all listed
as completed (Recommended)** / **Close some (say which)** / **Leave all open**. Close with
`gh issue close $N --repo "$REPO_OWNER_NAME" --reason completed --comment "Latent close
(co-dwerker exit $TODAY): resolved by PR #$P, merged $MERGED_DATE, which carried no closing
keyword for this issue."`; record kept-open pairs with `checkpoint.py set --append
reconcile_dismissed='{"issue": N, "pr": P}'`. Then read `pending_verification` and repeat it in
the exit summary so tomorrow's reader sees what is waiting.

**Board (project mode).** Only items whose Status disagrees with the issue's state:

```bash
gh api graphql -f org="$REPO_OWNER" -F num=$PROJECT_NUMBER -f query='
query($org:String!,$num:Int!,$after:String){
  organization(login:$org){projectV2(number:$num){items(first:100,after:$after){
    pageInfo{hasNextPage endCursor}
    nodes{id fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name optionId}}
      content{__typename ... on Issue{number state repository{nameWithOwner}}}}}}}}' \
  --jq '.data.organization.projectV2.items | {more: .pageInfo, rows: [.nodes[] | select(.content.__typename=="Issue") | {id, option: .fieldValueByName.optionId, status: .fieldValueByName.name, repo: .content.repository.nameWithOwner, issue: .content.number, state: .content.state}]}'
```

Repeat with `-f after=<endCursor>` while `more.hasNextPage`. For a user-owned project replace
`organization(login:$org)` with `user(login:$org)`. A row is a discrepancy when `state == CLOSED`
and `option != status_role_map.done`, or `state == OPEN` and `option == status_role_map.done`.
Move the first kind to `done` with `gh project item-edit --project-id $PROJECT_ID --id <id>
--field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_ROLE_DONE_ID` (when `done` is not
`null`); ask about the second kind, since an open issue in Done usually means someone closed the
wrong thing. Report "board agrees with issue state" when there are none.

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
- **Active issue:** #<n> — <title> (step <s>)
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

Close with a short summary that tomorrow's reader can act on without the conversation: the date
and mode, what was completed (with PR numbers), what was created, what is in progress and at which
step and branch, the recommended starting point for the next session, any open items, and the
pending-verification list with its check-after dates.
