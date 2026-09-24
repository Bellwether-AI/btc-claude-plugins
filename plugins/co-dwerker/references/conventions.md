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
10. Closing issues and reconciliation

---

## 1. Environment and how to run the scripts

Derive these once per skill invocation, from inside the repo:

```bash
TODAY=$(date +%Y-%m-%d)
MAIN_CHECKOUT=$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd)")   # main checkout, even from a linked worktree; works on any git
STATE_FILE="$MAIN_CHECKOUT/.co-dwerker.state.json"   # per-clone session state (git-excluded by the scripts)
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
full form. Three things the scripts already handle, so the skills do not: the state file lives
in the main checkout and is found from any worktree; it is added to the clone's
`.git/info/exclude` (never to the committed `.gitignore`); every per-issue artifact the capture
writes is excluded the same way. References live at `${CLAUDE_PLUGIN_ROOT}/references/<name>.md`. If you ever see the
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
non-negotiable and manage cost through concurrency instead. The one exception is the legwork tier
below, which exists to stretch the best model's usage limits, not to save tokens.

- **Session model.** Your system prompt names the model you are running on. If it is not the most
  capable model available, suggest once at session start: "co-dwerker works best on the most capable
  model. Run `/model best` to switch." `best` always resolves to the most capable model the account
  has, so this advice never needs updating when models change. Say it once; do not repeat it later
  in the session, and never recommend a specific older model by name.
- **Subagents.** Do not pass a `model` parameter when dispatching, except for legwork-tier work
  (below). Omitted means the subagent inherits the session model (unless the user configured a
  default subagent model, which is their choice to make). `subagent_type: "fork"` always inherits,
  and carries the conversation with it. Never pass `haiku` or `sonnet`.
- **Concurrency.** Keep at most two subagents in flight and let each land its work before launching
  more. This protects against losing work when a session's budget runs out; it is not a reason to
  lower model quality. The limit counts legwork-tier agents too.

### Legwork tier

The session model does the thinking. Some work needs none: it is many actions whose outcome is
already decided. That work may run one model down, because the plugin owner's plan gives the best
model a tighter weekly limit than the next one, and the owner would rather spend that limit on
design, review, and decisions than on typing out code the plan already contains.

**Lineup (the plugin owner maintains this line; do not try to verify limits or ordering from your
context):** best to least, `fable` > `opus` > `sonnet` > `haiku`. The legwork model is `opus`, and
the tier applies only when the session itself is on `fable`. Check the model your system prompt
names: if it is not `fable`, there is no legwork tier this session. The Agent tool's `model`
options are not listed in capability order, so never derive the lineup from them.

Legwork additionally requires that the task is fully specified: no interpretation, judgment, or
decision left (the bar is in the Legwork list below). Never step down twice, and never to `sonnet`
or `haiku`: the tier bridges one limit gap, it does not trade quality for speed.

**Legwork (next model down):**

- Implementing a plan task that already gives the exact files, the code or a near-complete
  sample, the test commands, and the acceptance criteria.
- The implementer's own first pass over what it just wrote: run the tests and linters, fix the
  breakage it introduced.
- Implementing a fix the session model has already specified to the same standard after a review.
- Bulk mechanical actions: a rename across many files, diffing or scanning large files or logs for
  a stated pattern, moving or regenerating files, repetitive `git`/`gh` operations over many items,
  running deployments the user has already approved, or scripts, and reporting their output.

**Thinking (session model only):**

- Brainstorming, design, writing the plan, and every gate the user answers.
- Every review, reading its findings, deciding whether a finding is right, and specifying the fix.
- Debugging anything the legwork agent could not fix on its first pass.
- Any task whose plan entry falls short of the bar above: fill in the plan first, or do the task
  yourself.
- The fix loop in `superpowers:subagent-driven-development`. Rounds 1 to 3 resume the legwork
  implementer, but the resume message is yours to write: turn each open finding into a specified
  fix (file, change, covering test) before sending it, never the raw findings. A finding you
  cannot specify without investigating is debugging: investigate on the session model, then hand
  down the spec. Rounds 4 and 5 dispatch a fresh implementer; omit `model` there so it lands on the
  session model, which is the escalation that skill asks for.

**How to dispatch legwork.** `subagent_type: "fork"` ignores `model`, so a legwork agent is
`general-purpose` (or `Explore` for read-only scans) with the legwork model from the lineup above.
It inherits nothing from the conversation. Inside `superpowers:subagent-driven-development`, brief
it exactly as that skill's implementer template says (task brief file, report file, no-subagents
contract) and add the worktree path and the user's instructions verbatim, which the brief cannot
carry. Outside that skill (bulk mechanical work), the prompt holds everything: paths, the exact
pattern or command, the expected output, and an instruction to stop and report rather than decide
when something the prompt did not anticipate comes up. If you find yourself explaining a decision
to it in the prompt, the task is not legwork.

The whole **Model Selection** section of `superpowers:subagent-driven-development` is overridden
by this section: ignore "use the least powerful model that can handle each role", ignore "always
specify the model explicitly when dispatching a subagent", and ignore the cheap and mid-tier
floors it sets for reviewers and scoped re-reviews. In co-dwerker, `model` is passed for exactly
one purpose, legwork-tier implementers; every reviewer, re-reviewer, whole-branch reviewer,
rounds 4 and 5 implementer, and any BLOCKED re-dispatch that skill says needs a more capable
model omits it.

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
`1.fetch`, `2.brainstorm`, `3.5a`, `5.cleanup`). Every heading is a step, marked even when its
text does not repeat the command. Values after `--set` are parsed as JSON when they look like JSON
(`57`, `true`, `[1,2]`) and kept as strings otherwise; store paths other steps re-read (design
doc, plan, worktree) as absolute paths. Exit codes: 0 ok, 1 gate blocked, 2 usage or state-file
error.

`progress.status` is the issue's status (`in_progress` from `start-issue` until `finish-issue`);
`progress.step_status` is the last mark. Resume Check keys on `progress.issue` being set.

**Context keys other steps rely on** (all under `progress.context`):

| Key | Written by | Read by |
|-----|-----------|---------|
| `work_mode`, `planned_issues`, `main_checkout` | Phase 0a / Standup gate | every phase, exit |
| `labels_verified` | Phase 1 (repo mode) | Phase 1 next session |
| `project_number`, `project_title`, `project_id`, `status_field_id`, `status_options`, `priority_field_id`, `priority_options` | Phase 0b | board updates, pr-review, new-issue, exit |
| `item_id` | Phase 2 | pr-review, Phase 5, exit |
| `design_doc`, `plan_doc` | Phase 2, Phase 3 Step 3.2 | Steps 3.4–3.5, Resume Check |
| `branch`, `worktree`, `worktree_native` | Phase 3 Step 3.3 | Step 3.5a, Phase 5 cleanup, Resume Check, exit |
| `baseline_tests_file`, `baseline_localapp_file` | Phase 3 Steps 3.1, 3.1b | Steps 3.5, 3.5a |
| `local_app_pids` | Steps 3.1b, 3.5a | Step 3.5a pre-flight, exit |
| `local_app_result`, `local_app_skip_reason`, `dismissed_for_pr` | Step 3.5a | Step 3.7 (PR body), `localapp_diff.py`, exit |
| `pr_number`, `pr_url` | Step 3.7 | Step 3.8, Phase 4, Phase 5 |
| `docs_pr_number`, `docs_pr_url`, `docs_repo_path`, `docs_repo_cloned` | Phase 4 (docs skill) | Phase 5 |
| `status_role_map` | Phase 0b | 2.board, pr-review §3, 5.board, new-issue §4, exit |
| `resolves_issues`, `refs_issues`, `verify_later` | Step 3.2, revised at 3.7 | Step 3.7 (PR body), Step 5.close-issue, `finish-issue` |
| `pending_verification` | Step 5.close-issue, exit §3 | Step 1.reconcile, exit §3, `show` |
| `reconcile_dismissed` | Step 1.reconcile, exit §3 | Step 1.reconcile |
| `issues_created` | new-issue skill | exit |

Session-level keys (`work_mode`, `main_checkout`, `planned_issues`, `issues_created`,
`labels_verified`, the project/board ids and `status_role_map`, `local_app_pids`,
`pending_verification`, `reconcile_dismissed`) survive `start-issue` and `finish-issue`;
everything else is per issue and is cleared. `finish-issue` records the active issue and every
entry of `resolves_issues` in `completed_this_session` and drops them from `planned_issues`.

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
- Legwork-tier dispatches (§2) are never forks: a fork ignores `model`.
- Respect the two-at-a-time limit from §2.

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
  The state file and the capture artifacts never need this; they are excluded, not ignored.

---

## 9. File schemas

### `.co-dwerker.state.json` (main checkout, excluded via `.git/info/exclude`)

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
  "pending_verification": [
    { "issue": 16, "pr": 22, "condition": "the 2026-09-09 05:00 UTC RefreshBbssamToken run succeeds", "check_after": "2026-09-09", "recorded": "2026-09-08" }
  ],
  "progress": {
    "issue": 42,
    "phase": "3",
    "step": "3.5a",
    "status": "in_progress | completed   (issue status; completed only after finish-issue)",
    "step_status": "in_progress | completed   (the last mark)",
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
- `pending_verification` is the top-level copy `end-session` makes of the session key of the
  same name, so the next standup (and `checkpoint.py show`) can read it even if `progress` was
  reset. `progress.context.pending_verification` is authoritative when both exist.
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

---

## 10. Closing issues and reconciliation

GitHub closes an issue on merge only when the PR body contains one of the keywords `close`,
`closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`, `resolved` immediately followed
by `#N` (or `Owner/Repo#N` for another repo), one issue per keyword. A bare `#N`, a number in the
title, or "(#17 #18 #16)" closes nothing. co-dwerker therefore tracks what a PR resolves
explicitly instead of hoping the body says so.

**The resolution set** (per-issue context, integers in the current repo only):

| Key | Meaning | PR body line |
|-----|---------|--------------|
| `resolves_issues` | issues the PR fully resolves; starts as `[ISSUE_NUMBER]` | `Closes #N` |
| `refs_issues` | issues the PR touches but does not finish | `Refs #N — <what remains>` |
| `verify_later` | entries `{"issue": N, "condition": "<observable>", "check_after": "YYYY-MM-DD"}` for issues in `resolves_issues` whose closure should be confirmed by a later observation | still `Closes #N` |

Never put a partially addressed issue under `Closes`; never hold a fully fixed issue out of
`Closes` because it "needs verification first" — that is what `verify_later` records. Issues in
other repos are written into the body by hand (`Closes Org/Repo#N`) and are not tracked.

**Phase 5** closes every open issue in `resolves_issues` that is not in `verify_later`, with a
comment naming the PR. For each `verify_later` entry it appends to the session-level
`pending_verification` list (`{"issue", "pr", "condition", "check_after", "recorded"}`) and
comments on the issue with the condition and the date co-dwerker will ask about it.

**Reconciliation** (standup Step 1.reconcile, exit §3) looks for issues left behind:

1. `pending_verification` entries whose `check_after` is today or earlier.
2. Open issues referenced by PRs merged in the last 30 days. Same-repo references are extracted
   with the `jq` regex `(?:^|[^A-Za-z0-9_/-])#([0-9]+)` (no lookbehind, so it runs in both `jq`
   and `gh --jq`). These are candidates, not proof: bodies also cite follow-ups they filed and
   numbers from other repos.
3. `planned_issues` entries whose issue is already closed (dropped silently, with a note).

Present the candidates and ask once with `AskUserQuestion`: **Close all listed as completed
(Recommended)** / **Close some (say which)** / **Leave all open**. Closing is
`gh issue close N --repo "$REPO_OWNER_NAME" --reason completed --comment "<why, naming the PR
and, for orphans, that the PR carried no closing keyword>"`. Kept-open orphans go into the
session-level `reconcile_dismissed` list as `{"issue": N, "pr": P}` so the same pair is not
asked again; kept-open pending entries either leave the list or get a new `check_after`.

**Board status roles.** Boards name their statuses differently, so Phase 0b maps the Status
field's options to three roles and stores `status_role_map` = `{"in_progress": <option id or
null>, "in_review": <option id or null>, "done": <option id or null>}`. Steps that move an item
use the role's id and, when it is `null`, say the board has no such status and continue. A board
with its built-in "Item closed" workflow enabled moves closed issues to Done on its own, which is
why reconciliation fixes issues first and only then looks for board items that disagree with
issue state.
