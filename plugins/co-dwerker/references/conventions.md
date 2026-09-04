# co-dwerker Conventions

Shared conventions for every co-dwerker skill. The skills point here instead of repeating
themselves. Read the section you need when you need it.

**Contents**

1. Environment and how to run the scripts
2. Model policy
3. Progress checkpoints (`checkpoint.py`)
4. Asking the user
5. Subagents
6. `gh` errors and the GitHub hosting guard
7. Waiting on long-running work
8. Worktrees
9. File schemas

---

## 1. Environment and how to run the scripts

Derive these once per skill invocation, from inside the repo:

```bash
TODAY=$(date +%Y-%m-%d)
MAIN_CHECKOUT=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")  # main checkout, even from a linked worktree
STATE_FILE="$MAIN_CHECKOUT/.co-dwerker.state.json"   # per-clone session state (gitignored)
CONFIG_FILE=".co-dwerker.json"                       # per-repo config (committed)
GLOBAL_STATE_FILE="$HOME/.claude/co-dwerker-last-repo.json"
GLOBAL_STATE_FILE_LEGACY="$HOME/.co-dwerker-last-repo.json"   # pre-v0.3.1 location, read-only fallback
REPO_REMOTE=$(git remote get-url origin 2>/dev/null)
REPO_OWNER_NAME=$(echo "$REPO_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')   # owner/repo
REPO_OWNER="${REPO_OWNER_NAME%%/*}"                  # login only — every `gh project … --owner` wants this
```

Two things about these names:

- **They are values you carry, not shell state.** Each Bash call starts a fresh shell, so a
  variable set in one call does not exist in the next. Substitute the literal value (or re-derive
  it inline) every time a command needs it. The `$NAME` form in the skills is shorthand for "the
  value you determined earlier".
- **`REPO_OWNER` vs `REPO_OWNER_NAME`.** `gh issue`, `gh pr`, and `gh label` take `--repo
  owner/repo`; `gh project` takes `--owner <login>`. Passing `owner/repo` to `--owner` fails.

**Plugin files** live under the plugin root, substituted into `${CLAUDE_PLUGIN_ROOT}` in skill
text. Run the scripts exactly like this, written out in full:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py <subcommand> ...
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/localapp_capture.py ...
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/localapp_diff.py ...
```

That exact form is what each skill's `allowed-tools` pre-approves, and it works even if the
executable bit was lost on install. Where a skill writes `checkpoint.py mark …` it means this
full form. References live at `${CLAUDE_PLUGIN_ROOT}/references/<name>.md`. If you ever see the
placeholder unsubstituted, the plugin root is two directories above the skill's own directory
(the "Base directory for this skill" line printed when the skill loaded).

`checkpoint.py` and `localapp_diff.py` locate the main checkout's state file themselves, from
the main checkout or any linked worktree, so they need no `--state-file`. Never `cd` out of the
repo to work on another one (the docs repo, for instance); use `git -C <path>` and `gh --repo`
instead, so every relative path in the session keeps meaning what it meant.

---

## 2. Model policy

co-dwerker runs long autonomous phases: design, implementation, verification, review. The quality
of every one of those scales with the model, and the plugin owner has said explicitly that they
prefer the most capable model everywhere and accept the token cost. Treat model quality as
non-negotiable and manage cost through concurrency instead.

- **Session model.** Your system prompt names the model you are running on. If it is not the most
  capable model available, suggest once at session start: "co-dwerker works best on the most capable
  model. Run `/model best` to switch." `best` always resolves to the most capable model the account
  has, so this advice never needs updating when models change. Say it once; do not repeat it later
  in the session, and never recommend a specific older model by name.
- **Subagents.** Do not pass a `model` parameter when dispatching. Omitted means the subagent
  inherits the session model (unless the user configured a default subagent model, which is their
  choice to make). `subagent_type: "fork"` always inherits, and carries the conversation with it.
  Never pass `haiku`.
- **Concurrency.** Keep at most two subagents in flight and let each land its work before launching
  more. This protects against losing work when a session's budget runs out; it is not a reason to
  lower model quality.

---

## 3. Progress checkpoints

Task and todo tools are not available by default on current Claude models, and long autonomous
phases push earlier instructions out of context. A step that is not recorded as done is a step
that can be skipped without anyone noticing, and a crash or context compaction in the middle of
Phase 3 loses everything held only in conversation. `checkpoint.py` writes progress into the
state file at every step boundary so the workflow, not your memory, is the source of truth.

```bash
# shorthand below: checkpoint.py == python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py
checkpoint.py start-issue 42 --phase 2 --set work_mode=repo --set planned_issues='[42, 43]'
checkpoint.py mark 3.1 in_progress                 # before starting a step
checkpoint.py mark 3.1 completed --set baseline_tests_file=.co-dwerker.baseline-tests.json
checkpoint.py set --set pr_number=57 --set pr_url=https://github.com/o/r/pull/57
checkpoint.py set --append local_app_pids=12345    # lists grow idempotently
checkpoint.py set --top repo_owner_name=o/r        # top-level state keys (rarely needed)
checkpoint.py gate 3                               # before ANY user-facing GATE: exit 0, or a list of missing steps
checkpoint.py gate 5 --skip docs-merge             # only for a step that genuinely does not apply; tell the user
checkpoint.py show                                 # progress + last_session; use on resume or to re-orient
checkpoint.py finish-issue                         # Phase 5 cleanup done; clears per-issue context
checkpoint.py end-session --repo-owner-name o/r --prs-created 57 --prs-merged 57   # exit skill
```

Step ids are `<phase>.<step>` and match the headings in `skills/work/SKILL.md` (for example
`1.fetch`, `2.brainstorm`, `3.5a`, `5.cleanup`). Values after `--set` are parsed as JSON when they
look like JSON (`57`, `true`, `[1,2]`) and kept as strings otherwise. Exit codes: 0 ok, 1 gate
blocked, 2 usage or state-file error.

If `checkpoint.py` warns that the state file is not gitignored, append `.co-dwerker.state.json`
to `.gitignore` on the current branch so the change ships with the PR (`end-session` also adds it
if still missing).

**Context keys other steps rely on** (all under `progress.context`):

| Key | Written by | Read by |
|-----|-----------|---------|
| `work_mode`, `planned_issues`, `main_checkout` | Phase 0a / Standup gate | every phase, exit |
| `labels_verified` | Phase 1 (repo mode) | Phase 1 next session |
| `project_number`, `project_title`, `project_id`, `status_field_id`, `status_options`, `priority_field_id`, `priority_options` | Phase 0b | board updates, pr-review, new-issue, exit |
| `item_id` | Phase 2 | pr-review, Phase 5 |
| `design_doc`, `plan_doc` | Phase 2, Phase 3 Step 3.2 | Steps 3.4–3.5, Resume Check |
| `branch`, `worktree`, `worktree_native` | Phase 3 Step 3.3 | Step 3.5a, Phase 5 cleanup, Resume Check, exit |
| `baseline_tests_file`, `baseline_localapp_file` | Phase 3 Steps 3.1, 3.1b | Steps 3.5, 3.5a |
| `local_app_pids` | Steps 3.1b, 3.5a | Step 3.5a pre-flight, exit |
| `local_app_result`, `local_app_skip_reason`, `dismissed_for_pr` | Step 3.5a | Step 3.7 (PR body), `localapp_diff.py`, exit |
| `pr_number`, `pr_url` | Step 3.7 | Step 3.8, Phase 4, Phase 5 |
| `docs_pr_number`, `docs_pr_url`, `docs_repo_path`, `docs_repo_cloned` | Phase 4 (docs skill) | Phase 5 |
| `issues_created` | new-issue skill | exit |

Session-level keys (`work_mode`, `main_checkout`, `planned_issues`, `issues_created`,
`labels_verified`, the project/board ids, `local_app_pids`) survive `start-issue` and
`finish-issue`; everything else is per issue and is cleared.

---

## 4. Asking the user

Use `AskUserQuestion` with real options: a short label, a one-line description of what happens if
chosen, and the recommended choice first with "(Recommended)" in its label when there is one. The
tool allows two to four options and always adds its own free-text "Other", so never list more than
four and never add your own "something else" option. The skills describe each gate as an option
list; render them as options rather than as a numbered paragraph. Put the situation and evidence in
the question text, keep the options to the decision itself, and do not ask for anything you can
derive from files or `gh`.

---

## 5. Subagents

- Use `subagent_type: "fork"` for work that needs what this session already knows: the design doc,
  the decisions made during brainstorming, the user's stated preferences. A fork inherits the whole
  conversation and the session model.
- Use the `Explore` agent for read-only scans of a large codebase when only the conclusion matters.
- Pass the user's instructions to a subagent verbatim (add detail if useful, but the user chose
  their words carefully and a paraphrase loses that).
- Respect the two-at-a-time limit from section 2.

---

## 6. `gh` errors and the GitHub hosting guard

co-dwerker requires a GitHub-hosted repository. If `REPO_REMOTE` does not contain `github.com`,
stop and tell the user: "co-dwerker requires a GitHub-hosted repository. The origin remote does not
appear to be on github.com."

If any `gh` command fails, report the error and ask how to proceed instead of continuing as if it
had worked. The usual causes are missing auth (`gh auth login`), insufficient project-board
permissions, rate limiting, and (for `gh project`) passing `owner/repo` where `--owner` wants the
login.

---

## 7. Waiting on long-running work

The Bash tool stops any command that begins with `sleep` at its timeout instead of letting it run,
and it cannot "watch" output over time. So:

- Never issue a bare `sleep`. A loop with an inner sleep is fine:
  `for i in 1 2 3; do ITEM_ID=$(...); [ -n "$ITEM_ID" ] && break; sleep 2; done`.
- Scripts that wait internally (the capture script, `gh run watch`, `gh pr checks --watch`) run
  in the foreground with an explicit Bash `timeout`. For the capture script use
  `(boot_timeout + idle_seconds + 90) * 1000` ms: **240000** with the defaults of 60 s boot and
  90 s idle (the script's own hard cap is boot + idle + 30 s, plus a 10 s kill grace).
- Before merging a PR: `gh pr checks <n> --watch --fail-fast` with a 10-minute timeout. After
  merging: find the run for the merge commit (Phase 5 shows how) and `gh run watch <id>
  --exit-status`. If a pipeline routinely takes longer than 10 minutes, use the `Monitor` tool with
  a poll loop that emits each terminal status.

---

## 8. Worktrees

`superpowers:using-git-worktrees` decides between the native `EnterWorktree` tool and a
`git worktree add` fallback. Step 3.3 records `branch`, `worktree`, and `worktree_native` so later
steps use the matching tool.

- **Native.** The session's working directory is now the worktree under `.claude/worktrees/`. The
  baseline files from Steps 3.1 and 3.1b were written in `main_checkout`, so Step 3.3 copies them
  across. At Phase 5 cleanup, after the PR has merged, call `ExitWorktree` with `action: "remove"`.
  If it refuses because of uncommitted changes, show them to the user and only retry with
  `discard_changes: true` after they confirm.
- **Fallback.** From the main checkout, `git worktree remove <path>`.
- **Resuming** into a recorded worktree: `cd "<worktree>"` regardless of `worktree_native`; the
  flag only decides the removal tool. If `ExitWorktree` later reports that this session did not
  enter the worktree, fall back to `git worktree remove`.
- **Exclude file.** `git rev-parse --git-path info/exclude` resolves to the clone's one shared
  `info/exclude` from the main checkout and from every linked worktree, which is why the scripts'
  exclusions apply everywhere.
- **Config edits in the worktree.** `.co-dwerker.json` is repo config. When Step 3.5a changes it
  (custom run command, no-runnable-app flag, permanent warning dismissal), commit that change on
  the feature branch right away so it ships with the PR and the worktree can be removed cleanly.

---

## 9. File schemas

### `.co-dwerker.state.json` (main checkout, gitignored)

Written incrementally by `checkpoint.py` during a session; `end-session` fills in `last_session`
and the top-level keys from `progress` at exit.

```json
{
  "work_mode": "repo | project",
  "repo_owner_name": "owner/repo",
  "repo_local_path": "/absolute/path/to/main/checkout",
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
    "context": { "see the context-keys table in section 3": true }
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
- `last_session` is the end-of-day summary written by `end-session`.
- `work_mode` absent means a pre-v0.2 state file; present the first-time mode prompt rather than
  defaulting.

### `~/.claude/co-dwerker-last-repo.json` (global)

Written by `end-session`. Only enough to navigate back to the repo when the session starts
elsewhere:

```json
{ "repo_owner_name": "owner/repo", "repo_local_path": "/absolute/path/to/main/checkout" }
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
- `local_app_command`: user-supplied run command from the Step 3.5a no-app-detected gate; used by
  both Step 3.1b and Step 3.5a instead of framework detection.
- `local_app_skip`: `true` marks the repo as having no runnable application; Steps 3.1b and 3.5a
  skip cleanly.
- `dismissed_warnings`: warnings the user dismissed permanently; `localapp_diff.py` treats them
  as pre-existing. Append with `localapp_diff.py dismiss --normalized "<text>"`.

### Baseline and verification artifacts (per clone, excluded via `.git/info/exclude`)

| File | Written by | Purpose |
|------|-----------|---------|
| `.co-dwerker.baseline-tests.json` | Phase 3 Step 3.1 (agent) | pre-existing test/lint failures; see `baseline-tests.md` |
| `.co-dwerker.baseline-localapp.json` | `localapp_capture.py --mode baseline` | unmodified-branch boot + log capture |
| `.co-dwerker.verify-localapp.json` | `localapp_capture.py --mode verify` | implemented-branch boot + log capture |
| `.co-dwerker.localapp-diff.json` | `localapp_diff.py diff` | machine-readable diff report |
| `.co-dwerker.localapp-<app>-<mode>.log` | `localapp_capture.py` | full raw output for debugging |

The scripts add these to the clone's shared `.git/info/exclude` themselves. Phase 5 cleanup
deletes them; they are per-issue artifacts, not documentation.
