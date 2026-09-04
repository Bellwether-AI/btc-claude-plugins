# co-dwerker Conventions

Shared conventions for every co-dwerker skill. The skills point here instead of repeating
themselves. Read the section you need when you need it.

**Contents**

1. Environment
2. Model policy
3. Progress checkpoints (`checkpoint.py`)
4. Asking the user
5. Subagents
6. `gh` errors and the GitHub hosting guard
7. Waiting on long-running work
8. Worktrees
9. File schemas

---

## 1. Environment

Derive these once per skill invocation (from the repo root):

```bash
TODAY=$(date +%Y-%m-%d)
STATE_FILE=".co-dwerker.state.json"          # per-clone session state (gitignored)
CONFIG_FILE=".co-dwerker.json"               # per-repo config (committed)
GLOBAL_STATE_FILE="$HOME/.claude/co-dwerker-last-repo.json"
GLOBAL_STATE_FILE_LEGACY="$HOME/.co-dwerker-last-repo.json"   # pre-v0.3.1 location, read-only fallback
REPO_REMOTE=$(git remote get-url origin 2>/dev/null)
REPO_OWNER_NAME=$(echo "$REPO_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
```

Plugin files live under the plugin root, which Claude Code substitutes into
`${CLAUDE_PLUGIN_ROOT}` in skill text:

- Scripts: `${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py`, `localapp_capture.py`, `localapp_diff.py`
- References: `${CLAUDE_PLUGIN_ROOT}/references/<name>.md`

If you ever see the literal placeholder unsubstituted, the plugin root is two directories above the
skill's own directory (the "Base directory for this skill" line printed when the skill loaded).

---

## 2. Model policy

co-dwerker runs long autonomous phases: design, implementation, verification, review. The quality
of every one of those scales with the model, and the plugin owner has said explicitly that they
prefer the most capable model everywhere and accept the token cost. Treat model quality as
non-negotiable and manage cost through concurrency instead.

- **Session model.** Your system prompt names the model you are running on. If it is not the most
  capable model available, suggest once at session start: "co-dwerker works best on the most capable
  model. Run `/model best` to switch." `best` resolves to the latest Fable model where the account
  has it and to Opus otherwise, so it never needs updating when models change. Say it once; do not
  repeat it later in the session, and never recommend a specific older model by name.
- **Subagents.** Do not pass a `model` parameter when dispatching. Omitted means the subagent
  inherits the session model (unless the user configured a default subagent model, which is their
  choice to make). `subagent_type: "fork"` always inherits, and carries the conversation with it.
  Never pass `haiku`.
- **Concurrency.** Keep at most two subagents in flight and let each land its work before launching
  more. This protects against losing work when a session's budget runs out; it is not a reason to
  lower model quality.

---

## 3. Progress checkpoints

Task and todo tools are disabled by default on current Claude models, and long autonomous phases
push earlier instructions out of context. A step that is not recorded as done is a step that can be
skipped without anyone noticing, and a crash or context compaction in the middle of Phase 3 loses
everything held only in conversation. `checkpoint.py` writes progress into `$STATE_FILE` at every
step boundary so the workflow, not your memory, is the source of truth.

```bash
CK="${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py"

$CK start-issue 42 --phase 2 --set work_mode=repo --set planned_issues='[42, 43]'
$CK mark 3.1 in_progress                 # before starting a step
$CK mark 3.1 completed --set baseline_tests_file=.co-dwerker.baseline-tests.json
$CK set --set pr_number=57 --set pr_url=https://github.com/o/r/pull/57
$CK set --append local_app_pids=12345    # lists grow idempotently
$CK gate 3                               # before ANY user-facing GATE: exit 0 or a list of missing steps
$CK gate 5 --skip docs-merge             # only for a step that genuinely does not apply; tell the user
$CK show                                 # on resume, or whenever you need to re-orient
$CK finish-issue                         # Phase 5 cleanup done; clears per-issue context
```

Step ids are `<phase>.<step>` and match the headings in `skills/work/SKILL.md` (for example
`1.fetch`, `2.brainstorm`, `3.5a`, `5.cleanup`). Values after `--set` are parsed as JSON when they
look like JSON (`57`, `true`, `[1,2]`) and kept as strings otherwise.

If `checkpoint.py` warns that the state file is not gitignored, append `.co-dwerker.state.json`
to `.gitignore` before the next commit.

**Context keys other steps rely on** (all under `progress.context`):

| Key | Written by | Read by |
|-----|-----------|---------|
| `work_mode`, `planned_issues` | Standup gate | every phase, exit |
| `project_number`, `project_id`, `status_field_id`, `status_options`, `item_id` | Phase 0b / Phase 2 | board updates, pr-review, exit |
| `branch`, `worktree`, `worktree_native` | Phase 3 Step 3 | Step 5a, Phase 5 cleanup, exit |
| `baseline_tests_file`, `baseline_localapp_file` | Phase 3 Steps 1, 1b | Steps 5, 5a |
| `local_app_pids` | Steps 1b, 5a | Step 5a pre-flight, exit |
| `local_app_skip_reason`, `dismissed_for_pr` | Step 5a | Step 7 (PR body), exit |
| `pr_number`, `pr_url` | Step 7 | Step 8, Phase 4, Phase 5 |
| `docs_pr_number`, `docs_repo_path`, `docs_repo_cloned` | Phase 4 | Phase 5 |

---

## 4. Asking the user

Use `AskUserQuestion` with real options: a short label, a one-line description of what happens if
chosen, and the recommended choice first with "(Recommended)" in its label when there is one. The
skills describe each gate as an option list; render them as options rather than as a numbered
paragraph, so the choice is unambiguous for both of you. Put the situation and evidence in the
question text, keep the options to the decision itself, and do not ask for anything you can
derive from files or `gh`.

---

## 5. Subagents

- Use `subagent_type: "fork"` for work that needs what this session already knows: the design doc,
  the decisions made during brainstorming, the user's stated preferences. A fork inherits the whole
  conversation and the session model.
- Use the `Explore` agent for read-only scans of a large codebase when only the conclusion matters.
- Pass the user's instructions to a subagent verbatim, adding detail if useful but never
  paraphrasing them away.
- Respect the two-at-a-time limit from section 2.

---

## 6. `gh` errors and the GitHub hosting guard

co-dwerker requires a GitHub-hosted repository. If `REPO_REMOTE` does not contain `github.com`,
stop and tell the user: "co-dwerker requires a GitHub-hosted repository. The origin remote does not
appear to be on github.com."

If any `gh` command fails, report the error and ask how to proceed instead of continuing as if it
had worked. The usual causes are missing auth (`gh auth login`), insufficient project-board
permissions, and rate limiting.

---

## 7. Waiting on long-running work

The Bash tool stops any command that begins with `sleep` at its timeout instead of letting it run,
and it cannot "watch" output over time. So:

- Never issue a bare `sleep`. A loop with an inner sleep is fine:
  `for i in 1 2 3; do ITEM_ID=$(...); [ -n "$ITEM_ID" ] && break; sleep 2; done`.
- Scripts that wait internally (the capture script, `gh run watch`) run in the foreground with an
  explicit Bash `timeout`. Size it to the work: for the capture script use
  `(boot_timeout + idle_seconds + 60) * 1000` ms, at most 600000.
- CI after a merge: find the run, then `gh run watch <run-id> --exit-status` with a 10-minute
  timeout. Before a merge: `gh pr checks <n> --watch --fail-fast`. If a pipeline routinely takes
  longer than 10 minutes, use the `Monitor` tool with a poll loop that emits each terminal status.

---

## 8. Worktrees

`superpowers:using-git-worktrees` decides between the native `EnterWorktree` tool and a
`git worktree add` fallback. Record which one happened so cleanup uses the matching tool:

```bash
$CK set --set worktree=<path> --set worktree_native=true --set branch=<name>
```

- **Native.** The session's working directory is now the worktree under `.claude/worktrees/`, and
  the baseline files from Steps 1 and 1b were written in the main checkout, so copy them across
  (Step 3 shows how). At Phase 5 cleanup, after the PR has merged, call `ExitWorktree` with
  `action: "remove"`. If it refuses because of uncommitted changes, show them to the user and only
  retry with `discard_changes: true` after they confirm.
- **Fallback.** From the main checkout, `git worktree remove <path>`.

---

## 9. File schemas

### `.co-dwerker.state.json` (per clone, gitignored)

Written incrementally by `checkpoint.py` during a session and summarized by `/co-dwerker:exit`.

```json
{
  "work_mode": "repo | project",
  "repo_owner_name": "owner/repo",
  "repo_local_path": "/absolute/path/to/repo",
  "github_project_number": null,
  "github_project_title": null,
  "planned_issues": [43],
  "progress": {
    "issue": 42,
    "phase": "3",
    "step": "3.5a",
    "status": "in_progress | completed",
    "started_at": "ISO-8601",
    "updated_at": "ISO-8601",
    "completed_steps": ["3.1", "3.1b", "3.2", "3.3", "3.4", "3.5"],
    "context": { "see the context-keys table above": true }
  },
  "completed_this_session": [41],
  "last_session": {
    "date": "YYYY-MM-DD",
    "completed_issues": [41],
    "current_issue": 42,
    "current_phase": "3",
    "current_step": "3.5a",
    "branch": "feature/42-short-name",
    "worktree": "/path or null",
    "prs_created": [57],
    "prs_merged": [56],
    "issues_created": [44],
    "local_app_pids": [12345],
    "local_app_skip_reason": null
  }
}
```

- `progress` is the live view. Resume Check trusts it over `last_session` when both exist.
- `last_session` is the end-of-day summary written by the exit skill.
- `work_mode` absent means a pre-v0.2 state file; present the first-time mode prompt rather than
  defaulting.

### `~/.claude/co-dwerker-last-repo.json` (global)

Only enough to navigate back to the repo when the session starts elsewhere:

```json
{ "repo_owner_name": "owner/repo", "repo_local_path": "/absolute/path/to/repo" }
```

### `.co-dwerker.json` (per repo, committed)

Merge into this file; never overwrite it, because several steps own different keys.

```json
{
  "docs_repo": "Org/DocsRepo or null",
  "docs_path": "path/within/docs/repo or null",
  "local_app_command": "custom run command, or absent",
  "local_app_skip": false,
  "dismissed_warnings": ["normalized warning text", "..."]
}
```

- `docs_repo` / `docs_path`: companion documentation repo (Phase 4, `/co-dwerker:docs`).
- `local_app_command`: user-supplied run command from the Step 5a no-app-detected gate; used by
  both Step 1b and Step 5a instead of framework detection.
- `local_app_skip`: `true` marks the repo as having no runnable application; Steps 1b and 5a
  skip cleanly.
- `dismissed_warnings`: warnings the user dismissed permanently; `localapp_diff.py` treats them
  as pre-existing. Append with `localapp_diff.py dismiss --normalized "<text>"`.

### Baseline and verification artifacts (per clone, excluded via `.git/info/exclude`)

| File | Written by | Purpose |
|------|-----------|---------|
| `.co-dwerker.baseline-tests.json` | Phase 3 Step 1 (agent) | pre-existing test/lint failures; see `baseline-tests.md` |
| `.co-dwerker.baseline-localapp.json` | `localapp_capture.py --mode baseline` | unmodified-branch boot + log capture |
| `.co-dwerker.verify-localapp.json` | `localapp_capture.py --mode verify` | implemented-branch boot + log capture |
| `.co-dwerker.localapp-diff.json` | `localapp_diff.py diff` | machine-readable diff report |
| `.co-dwerker.localapp-<app>-<mode>.log` | `localapp_capture.py` | full raw output for debugging |

The scripts add these to `.git/info/exclude` themselves (resolved per worktree). Phase 5 cleanup
deletes them; they are per-issue artifacts, not documentation.
