---
name: work
description: Use when the user wants to start or resume a development session on a GitHub repo — a daily standup, triaging or picking issues, or taking an issue from design through implementation, review, and merge. Also use for "let's get to work", "what should I work on today", "pick up where we left off", or "resume the session".
compatibility: Requires the superpowers, pr-review-toolkit, commit-commands, and episodic-memory plugins, the gh CLI, and python3 3.9+.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py *), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/localapp_capture.py *), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/localapp_diff.py *)
---

# Co-Dwerker: Work

Run a structured development session that takes GitHub issues from standup to merged PR by
composing the superpowers and pr-review-toolkit skills, and leaves enough state behind that the
next session picks up exactly where this one stopped.

Two work modes, remembered per repo:

- **Repo mode** — GitHub Issues with P0–P3 priority labels; no board needed.
- **Project mode** — a GitHub Projects board with Status and Priority fields.

**Workflow:** Repo Detection → Resume Check → 0a Mode → 0b Project (project mode only) →
1 Standup → 2 Brainstorm → 3 Execute → 4 Docs → 5 Close → 6 Next (loops to 2)

## Ground rules

`${CLAUDE_PLUGIN_ROOT}/references/conventions.md` holds the shared conventions and file schemas.
The parts you need on every step:

- **Checkpoints.** Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py …` written out in
  full (below, `checkpoint.py …` is shorthand for that). Mark each step `in_progress` before you
  start it and `completed` when it is done; store anything a later step needs with
  `checkpoint.py set`. Run `checkpoint.py gate <phase>` before every user-facing GATE and go back
  if it lists missing steps. A long autonomous phase pushes these instructions out of context; the
  state file is what stops a step from being quietly skipped, and it is what Resume Check reads
  after a crash or a compacted context. The script finds the main checkout's state file from any
  worktree on its own.
- **Values, not shell variables.** `$NAME` in this file means "the value you determined earlier".
  Bash calls do not share state, so substitute the literal value in every command.
- **Model.** If the session is not on the most capable model available, suggest `/model best`
  once, at the start. Never pass `model` when dispatching subagents; they inherit. At most two
  subagents in flight.
- **Asking.** Gates are `AskUserQuestion` calls with two to four real options, recommended first.
- **Waiting.** No bare `sleep`. Scripts that wait get an explicit Bash `timeout`; CI waits use
  `gh pr checks --watch` and `gh run watch`.
- **`gh` failures** stop the workflow with the error and a question, never a silent continue.
  `gh project … --owner` takes the login (`$REPO_OWNER`), not `owner/repo`.

## Repo Detection

The working directory may not be the target repo. Follow
`${CLAUDE_PLUGIN_ROOT}/references/repo-detection.md`, then derive the environment values
(conventions §1: `MAIN_CHECKOUT`, `REPO_OWNER_NAME`, `REPO_OWNER`, and the rest). Everything below
assumes those are known and the CWD is the repo.

## Resume Check

1. **State file.** `checkpoint.py show` prints the live `progress` block, the steps still missing
   for its phase, and the previous `last_session` summary. When both exist, `progress` is the
   truth.
2. **Episodic memory.** Invoke `episodic-memory:search-conversations` for recent sessions on
   this repo: what was accomplished, blockers, decisions, context on the current issue.
3. **Git.** `git branch --list | head -20`, `git status --short`, `git worktree list`. Look for
   uncommitted work on a feature branch, worktrees from earlier sessions, branches named after
   issues in the state file.
4. **Offer.** If `progress.issue` is set and `progress.status` is `in_progress`, ask: "Last session
   (`last_session.date`, `$WORK_MODE` mode on `$REPO_OWNER_NAME`) was on issue #N at step S on
   branch `B`." Options: **Resume at step S (Recommended)** — `cd` into `progress.context.worktree`
   if recorded and it exists, re-read `design_doc` / `plan_doc` from context, and continue from
   that step; **Fresh start** — go to Phase 0a and offer to clean up the orphaned branch or
   worktree. If the recorded branch and worktree no longer exist, say so and recommend a fresh
   start. If `progress.status` is `in_progress` but `progress.issue` is null, the last session
   stopped during standup; start fresh without asking.

No prior state → Phase 0a.

## Phase 0a: Mode Selection — `0a.mode`

If the state file already has `work_mode`, use it and say so in the standup header. Only ask when
it is absent (first run, or a pre-v0.2 state file): **Repo mode** — GitHub Issues only, priority
via P0–P3 labels; **Project mode** — a GitHub Projects board with Status and Priority fields.

`checkpoint.py set --set work_mode=<repo|project> --set main_checkout=$MAIN_CHECKOUT`. Repo mode
skips Phase 0b.

## Phase 0b: Project Select (project mode) — `0b.project`, `0b.fields`

1. `gh project list --owner "$REPO_OWNER" --format json --limit 20`. If the state file has
   `github_project_number`, offer it first. Confirm with the user; keep `PROJECT_NUMBER` and
   `PROJECT_TITLE`.
2. `gh project item-edit` needs GraphQL node ids, so fetch them now:
   ```bash
   gh project view $PROJECT_NUMBER --owner "$REPO_OWNER" --format json --jq '.id'
   gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json
   ```
   Expect **Status** (Backlog, Ready, In Progress, In Review, Done) and **Priority** (P0-Critical,
   P1-High, P2-Medium, P3-Low). If either is missing, offer to create it using
   `${CLAUDE_PLUGIN_ROOT}/references/setup-project-board.md`. Record `project_number`,
   `project_title`, `project_id`, `status_field_id`, `status_options` (name → option id),
   `priority_field_id`, `priority_options` with `checkpoint.py set` so later phases, the pr-review
   and new-issue skills, and the exit skill have them.

## Phase 1: Standup

### `1.fetch`

Project mode: `gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json --limit 100`.

Repo mode: unless `progress.context.labels_verified` is already true, check
`gh label list --repo "$REPO_OWNER_NAME" --json name` for the P0–P3 labels and create any that are
missing (`${CLAUDE_PLUGIN_ROOT}/references/setup-project-board.md`), then
`checkpoint.py set --set labels_verified=true`. Then:

```bash
gh issue list --repo "$REPO_OWNER_NAME" --state closed --search "closed:>=$LAST_DATE" \
  --json number,title,closedAt,labels,closedByPullRequestsReferences --limit 20
gh issue list --repo "$REPO_OWNER_NAME" --state open --assignee @me --json number,title,labels,milestone --limit 50
gh issue list --repo "$REPO_OWNER_NAME" --state open --json number,title,labels,milestone,assignees,createdAt --limit 50
```

`$LAST_DATE` is `last_session.date`, or yesterday if unknown.

### `1.report`

Present:

- **Shipped since last session** — Done or closed since `$LAST_DATE`, with PR links
  (`closedByPullRequestsReferences`).
- **In progress** — In Progress / In Review items, or open issues assigned to the user; cross-check
  against `progress.issue` and active branches.
- **Next by priority** — Ready items (project) or open issues (repo) sorted P0 > P1 > P2 > P3,
  then milestone due date, then oldest first; unlabelled issues last.
- **Blockers** — "blocked" / "waiting" labels, unresolved dependency references in issue bodies.

### `1.recommend`

Propose 2–4 issues for today with a one-line reason each (priority, dependency chain, quick win).
Offer more than fits in a day so "what's next" is always clear.

### GATE: work queue

`checkpoint.py gate 1`. Ask which issues, in what order. Options: the recommended set in
recommended order (first), then up to three single candidates; the tool's built-in "Other" covers
a custom order. The first issue becomes the active issue:

```bash
checkpoint.py start-issue $ISSUE_NUMBER --phase 2 --set work_mode=$WORK_MODE \
  --set main_checkout=$MAIN_CHECKOUT --set planned_issues='[<ordered numbers>]'
```

## Phase 2: Brainstorm

### `2.load`

`gh issue view $ISSUE_NUMBER --repo "$REPO_OWNER_NAME" --json title,body,comments,labels,assignees,milestone`,
plus the source files the issue references, linked issues and PRs, and the relevant tests if it
is a bug.

### `2.brainstorm`

Invoke `superpowers:brainstorming` and follow it completely. It explores the problem, asks
clarifying questions, proposes approaches, gets the design approved, and saves
`docs/superpowers/specs/$TODAY-<topic>-design.md`. Design defects are the expensive kind, so do
not shortcut this even for issues that look small. When it finishes:
`checkpoint.py mark 2.brainstorm completed --set design_doc=<path>`.

### `2.board` (project mode; otherwise `gate 2 --skip board`)

```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json \
  | jq -r '.items[] | select(.content.number? == '$ISSUE_NUMBER') | .id'        # ITEM_ID
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID \
  --single-select-option-id $STATUS_IN_PROGRESS_ID
checkpoint.py set --set item_id=$ITEM_ID
```

### `2.discovered`

Brainstorming often surfaces new bugs or sub-tasks. For each one, ask whether to create an issue
(invoke `co-dwerker:new-issue`) and whether it joins today's queue
(`checkpoint.py set --set planned_issues='[...]'`). Mark this step completed even when nothing
surfaced; "nothing to record" is a valid outcome, not a skipped step.

### GATE: design approval

Brainstorming holds its own approval gate. Once the design is approved, `checkpoint.py gate 2`
(with `--skip board` in repo mode) and go to Phase 3.

## Phase 3: Execute

Autonomous from here until a PR is ready for review. Two captures run before any code changes so
the later checks can tell "this PR broke it" from "it was already broken".

### `3.1` Baseline tests

Follow `${CLAUDE_PLUGIN_ROOT}/references/baseline-tests.md`. Capture-and-continue; no gate.

### `3.1b` Baseline local app

Follow `${CLAUDE_PLUGIN_ROOT}/references/local-app.md` §1–3. Give the capture command a Bash
`timeout` of 240000 ms. The only gate here is a boot failure on the *unmodified* branch, because
without a baseline boot the verification diff in Step 3.5a has nothing to compare against.

### `3.2` Plan

Invoke `superpowers:writing-plans`; it turns the design doc into an implementation plan.
`checkpoint.py mark 3.2 completed --set plan_doc=<path>`.

### `3.3` Isolate

Invoke `superpowers:using-git-worktrees`. Record what it did (conventions §8):

```bash
checkpoint.py set --set branch=<name> --set worktree=<path> --set worktree_native=<true|false>
```

Then carry the baseline artifacts into the worktree so Steps 3.5 and 3.5a can read them. The
copies stay out of commits because the scripts already added the names to the clone's shared
`.git/info/exclude`. `$MAIN_CHECKOUT` is `progress.context.main_checkout`.

```bash
for f in .co-dwerker.baseline-tests.json .co-dwerker.baseline-localapp.json; do
  [ -f "$MAIN_CHECKOUT/$f" ] && cp "$MAIN_CHECKOUT/$f" "$WORKTREE_PATH/$f"
done
```

### `3.4` Implement

Invoke `superpowers:executing-plans`, or `superpowers:subagent-driven-development` when the plan
has independent tasks (two subagents at a time). Follow it through its TDD cycles and commits.

### `3.5` Verify

Invoke `superpowers:verification-before-completion`: full test suite, linters, and the success
criteria from the design doc.

**Baseline diff.** If `.co-dwerker.baseline-tests.json` exists, compare failing test ids per
suite by exact match:

- failing then and now → pre-existing; report it, do not block on it.
- failing now only → regression; fix before continuing.
- failing then, passing now → mention it as a bonus.

Lint suites and any suite the baseline marked `tooling_missing` or `timeout` get no carve-out
(a lint baseline has no failing-test list to diff): exit 0 or fix. If a suite has
`failing_tests_truncated: true`, a "new" failure may be a pre-existing one that fell off the
50-entry list; confirm by running that one test in `$MAIN_CHECKOUT`, which is still on the
unmodified base, and if you cannot confirm, fix it. With no baseline file, every failure is a
regression.

### `3.5a` Local app verification

Follow `${CLAUDE_PLUGIN_ROOT}/references/local-app.md` §4–5. This is a phase gate: Step 3.6 does
not start until Step 3.5a is complete under one of the three definitions in §5 (clean diff, a skip
the user chose with a recorded reason, or no runnable app), and the step is marked completed with
`local_app_result` set. After fixing anything, `checkpoint.py mark 3.5a in_progress` and re-run
from detection. Capture commands get 240000 ms.

### `3.6` Changelog

Update `CHANGELOG.md` (line-by-line technical changes with the reason for each) and
`RELEASE_NOTES.md` (human-readable features, behavior changes, fixes, known issues) following the
repo's `CLAUDE.md`. Commit them with `commit-commands:commit`, separately from the implementation
commits.

### `3.7` Create PR

Compose the test plan from `progress.context` (local-app.md §6 lists the local-app lines). Fill in
every `<placeholder>` and every `$VAR` below with literal text before running; the quoted heredoc
does not expand variables.

```bash
gh pr create --title "<concise title>" --body "$(cat <<'EOF'
## Summary
<what changed and why, as bullets>

Closes #$ISSUE_NUMBER

## Test plan
- [x] Existing tests pass; new tests cover the change
- [x] Linting passes
<local app verification line(s) when applicable>

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
checkpoint.py set --set pr_number=<number> --set pr_url=<url>
```

### `3.8` Review and approval

Invoke `co-dwerker:pr-review`. It runs `pr-review-toolkit:review-pr`, fixes findings until the
review is clean, moves the board item to In Review in project mode, surfaces discovered work,
and holds its own user-approval gate. It reads `pr_number` and the rest from `progress.context`,
so it will not ask which PR. When it returns, `checkpoint.py gate 3` and go to Phase 4.

## Phase 4: Docs — `4.docs`

Invoke `co-dwerker:docs`. It reads the PR and issue from `progress.context`, checks
`.co-dwerker.json` for a companion docs repo, skips cleanly when there is none or the change has
no user-facing documentation impact, and records `docs_pr_number` / `docs_pr_url` itself when it
opens a PR. Its confirmation is the gate: `checkpoint.py mark 4.docs completed`, then
`checkpoint.py gate 4`.

## Phase 5: Close

### `5.merge`

```bash
gh pr checks $PR_NUMBER --watch --fail-fast        # Bash timeout 600000; skip if the repo has no workflows
gh pr merge $PR_NUMBER --squash                    # no --delete-branch: the branch is checked out in a worktree
```

### `5.ci`

The merge commit's run may take a few seconds to appear, and the previous run on the default
branch is already green, so find the run by commit rather than "latest":

```bash
gh repo view --json defaultBranchRef --jq .defaultBranchRef.name                 # DEFAULT_BRANCH
gh pr view $PR_NUMBER --json mergeCommit --jq .mergeCommit.oid                    # MERGE_SHA
for i in 1 2 3 4 5 6; do
  RUN_ID=$(gh run list --commit "$MERGE_SHA" --json databaseId --jq '.[0].databaseId')
  [ -n "$RUN_ID" ] && break; sleep 10
done
gh run watch "$RUN_ID" --exit-status                                               # Bash timeout 600000
```

If `gh workflow list` is empty the repo has no CI: `gate 5 --skip ci` and say so. If CI fails,
tell the user immediately with the run URL; that needs attention before anything else happens.

### `5.docs-merge` (when `docs_pr_number` is set; otherwise `--skip docs-merge`)

`gh pr merge $DOCS_PR_NUMBER --repo "$DOCS_REPO" --squash --delete-branch`

### `5.close-issue`

If the merge did not auto-close it:
`gh issue close $ISSUE_NUMBER --repo "$REPO_OWNER_NAME" --reason completed`

### `5.board` (project mode; otherwise `--skip board`)

`gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_DONE_ID`

### `5.cleanup`

- Worktree first: native → `ExitWorktree` with `action: "remove"`; fallback → from the main
  checkout, `git worktree remove "$WORKTREE_PATH"`. Then delete the branch, which the squash merge
  leaves "unmerged" in git's eyes: `git branch -D "$BRANCH_NAME"` and
  `git push origin --delete "$BRANCH_NAME"` (skip the push if the repo auto-deletes head branches).
- Delete the per-issue artifacts in the main checkout (and in the worktree if it still exists):
  `.co-dwerker.baseline-tests.json`, `.co-dwerker.baseline-localapp.json`,
  `.co-dwerker.verify-localapp.json`, `.co-dwerker.localapp-diff.json`,
  `.co-dwerker.localapp-*.log`.
- Remove a docs-repo clone only if this session created it (`docs_repo_cloned`).
- `checkpoint.py gate 5` (with the skips that apply), then `checkpoint.py finish-issue`.

## Phase 6: Next

### `6.progress`

Show what was completed today and the remaining queue (project mode: item list; repo mode: open
issues with labels).

### `6.queue`

Queue not empty: ask "Issue #N (title) is next in the queue. Start brainstorming?" Options:
**Start #N (Recommended)** → Phase 2 after `checkpoint.py start-issue N --phase 2`; **Pick a
different issue**; **Wrap up** → suggest `/co-dwerker:exit`.

Queue empty: say so and offer `/co-dwerker:new-issue`, picking an existing issue, or
`/co-dwerker:exit`.

## First-run setup

Project board fields (project mode) and P0–P3 labels (both modes):
`${CLAUDE_PLUGIN_ROOT}/references/setup-project-board.md`.
