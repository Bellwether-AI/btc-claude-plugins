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
1 Standup (incl. Left behind) → 2 Brainstorm → 3 Execute → 4 Docs → 5 Close → 6 Next (loops to 2)

## Ground rules

`${CLAUDE_PLUGIN_ROOT}/references/conventions.md` holds the shared conventions and file schemas.
The parts you need on every step:

- **Checkpoints.** Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py …` written out in
  full (below, `checkpoint.py …` is shorthand for that). Every `### x.y` heading below is a step:
  `checkpoint.py mark x.y in_progress` when you reach it and `checkpoint.py mark x.y completed`
  when it is done, whether or not the step's text repeats the command. Store anything a later step
  needs with `checkpoint.py set`. Run `checkpoint.py gate <phase>` before every user-facing GATE
  and go back if it lists missing steps. A long autonomous phase pushes these instructions out of
  context; the state file is what stops a step from being quietly skipped, and it is what Resume
  Check reads after a crash or a compacted context. The script finds the main checkout's state
  file from any worktree on its own and keeps it out of `git status` via `.git/info/exclude`.
- **Values, not shell variables.** `$NAME` in this file means "the value you determined earlier".
  Bash calls do not share state, so substitute the literal value in every command.
- **Model.** If the session is not on the most capable model available, suggest `/model best`
  once, at the start. Subagents inherit (no `model`), except legwork-tier dispatches under
  conventions §2, which run on the next model down. At most two subagents in flight.
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
4. **Offer.** If `progress.issue` is set (its `status` is `in_progress` until `finish-issue`;
   `step_status` is just the last mark), ask: "Last session (`last_session.date`, `$WORK_MODE`
   mode on `$REPO_OWNER_NAME`) was on issue #N at step S on branch `B`." Options: **Resume at
   step S (Recommended)** — `cd` into `progress.context.worktree` if recorded and it exists,
   re-read `design_doc` / `plan_doc` (absolute paths in context), and continue from step S, or
   from the next step if `step_status` is `completed`; **Fresh start** — go to Phase 0a and
   offer to clean up the orphaned branch or worktree. If the recorded branch and worktree no
   longer exist, say so and recommend a fresh start. If `progress.issue` is null there is
   nothing to resume; start at Phase 0a without asking.

No prior state → Phase 0a.

## Phase 0a: Mode Selection — `0a.mode`

If the state file already has `work_mode`, use it and say so in the standup header. Only ask when
it is absent (first run, or a pre-v0.2 state file): **Repo mode** — GitHub Issues only, priority
via P0–P3 labels; **Project mode** — a GitHub Projects board with Status and Priority fields.

`checkpoint.py mark 0a.mode completed --set work_mode=<repo|project> --set main_checkout=$MAIN_CHECKOUT`.
Repo mode skips Phase 0b.

## Phase 0b: Project Select (project mode) — `0b.project`, `0b.fields`

1. `gh project list --owner "$REPO_OWNER" --format json --limit 20`. If the state file has
   `github_project_number`, offer it first. Confirm with the user; keep `PROJECT_NUMBER` and
   `PROJECT_TITLE`.
2. `gh project item-edit` needs GraphQL node ids, so fetch them now:
   ```bash
   gh project view $PROJECT_NUMBER --owner "$REPO_OWNER" --format json --jq '.id'
   gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json
   ```
   Expect **Priority** (P0-Critical, P1-High, P2-Medium, P3-Low) and a single-select **Status**.
   If either field is missing, offer to create it using
   `${CLAUDE_PLUGIN_ROOT}/references/setup-project-board.md`. Boards differ in what they call
   their statuses, so map the Status options onto the three roles co-dwerker moves items through
   using the role-name table in conventions §10, and say which option each role got (or that a
   role was skipped). If the state file already has `status_role_map` and every id in it is
   still among the field's options, keep it without asking.
   Record `project_number`, `project_title`, `project_id`, `status_field_id`,
   `status_options` (name → option id), `status_role_map` (role → option id or null),
   `priority_field_id`, `priority_options` with `checkpoint.py set` so later phases, the
   pr-review and new-issue skills, and the exit skill have them. Mark `0b.project` and
   `0b.fields` completed.

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

`$LAST_DATE` is `last_session.date`, or yesterday if unknown. `checkpoint.py mark 1.fetch completed`.

### `1.report`

Present:

- **Shipped since last session** — Done or closed since `$LAST_DATE`, with PR links
  (`closedByPullRequestsReferences`).
- **In progress** — items in the board's `in_progress` or `in_review` role (project), or open
  issues assigned to the user; cross-check against `progress.issue` and active branches.
- **Next by priority** — items in neither of those roles nor `done` (project) or open issues
  (repo) sorted P0 > P1 > P2 > P3,
  then milestone due date, then oldest first; unlabelled issues last.
- **Blockers** — "blocked" / "waiting" labels, unresolved dependency references in issue bodies.

`checkpoint.py mark 1.report completed`.

### `1.reconcile`

Issues get left behind when a PR fixed them without a closing keyword, or when a fix was waiting
on a later observation nobody came back to. Conventions §10 holds the mechanics (scan pipeline,
the question, the close and bookkeeping commands); this step supplies the inputs and runs them
with `$WHEN`=`standup`, in both modes.

**a. Pending verification.** Entries in `progress.context.pending_verification`
(`checkpoint.py show` prints them) whose `check_after` is `$TODAY` or earlier.

**b. Orphan scan.** PRs merged in the last 30 days (newest 50) and the open issues:

```bash
SINCE=$(date -v-30d +%Y-%m-%d 2>/dev/null || date -d '30 days ago' +%Y-%m-%d)
gh pr list --repo "$REPO_OWNER_NAME" --state merged --search "merged:>=$SINCE" \
  --json number,title,body,mergedAt --limit 50 > /tmp/co-dwerker-merged.json
gh issue list --repo "$REPO_OWNER_NAME" --state open --json number,title --limit 200 \
  > /tmp/co-dwerker-open.json
```

Run the §10 pipeline on the two files and drop `reconcile_dismissed` pairs.

**c. Planned-queue hygiene.** For each number in `planned_issues`,
`gh issue view $N --repo "$REPO_OWNER_NAME" --json state --jq .state`; drop the closed ones with
a one-line note and `checkpoint.py set --set planned_issues='[...]'`. No question.

Add a **Left behind** section to the standup and ask and act per §10. Then
`checkpoint.py mark 1.reconcile completed`.

### `1.recommend`

Propose 2–4 issues for today with a one-line reason each (priority, dependency chain, quick win).
Offer more than fits in a day so "what's next" is always clear. `checkpoint.py mark 1.recommend completed`.

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
`checkpoint.py mark 2.brainstorm completed --set design_doc=<absolute path>` (absolute, because
it is read again from inside the worktree on resume).

### `2.board` (project mode; otherwise `gate 2 --skip board`)

```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json \
  | jq -r '.items[] | select(.content.number? == '$ISSUE_NUMBER') | .id'        # ITEM_ID
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID \
  --single-select-option-id $STATUS_ROLE_IN_PROGRESS_ID
checkpoint.py set --set item_id=$ITEM_ID
```

`$STATUS_ROLE_IN_PROGRESS_ID` is `status_role_map.in_progress`. When it is `null`, still record
`item_id` and say "board has no in-progress status; skipping the move".

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

Invoke `superpowers:writing-plans`; it turns the design doc into an implementation plan. Then set
the resolution set (conventions §10): start from `[$ISSUE_NUMBER]`; if the plan also fully covers
other open issues, add them to `resolves_issues`; if it covers part of one, put that number in
`refs_issues` instead.

`checkpoint.py mark 3.2 completed --set plan_doc=<absolute path> --set resolves_issues='[...]' --set refs_issues='[...]'`

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

Invoke `superpowers:subagent-driven-development` (at most two subagents in flight; that skill
serializes implementers, so the second slot is a reviewer). `superpowers:executing-plans` is only
for a platform without subagents, which Claude Code is not. If that skill judges the plan's tasks
too tightly coupled to dispatch, do the work yourself on the session model; the legwork tier then
covers only the bulk mechanical actions in conventions §2. Follow the skill through its TDD cycles
and commits.

This paragraph replaces that skill's "Model Selection" section and the required `model` line in
its implementer template. The legwork tier applies when your system prompt names the top model in
the conventions §2 lineup (today `fable`). Then each implementer for a fully specified task is
`general-purpose` with `model: "opus"` (the legwork model; the §2 lineup is authoritative),
briefed the way that skill's template describes plus the worktree path and the user's
instructions verbatim; it runs the task's tests and linters and fixes its own breakage before
reporting. Everything else in the loop omits `model`: spec and quality reviewers, re-reviewers,
and the fresh implementers of fix rounds 4 and 5. Fix rounds 1 to 3 resume the legwork
implementer with fixes you have specified, not raw findings. A task whose plan entry lacks the
files, the code or a near-complete sample, the test commands, or the acceptance criteria is not
legwork: complete the plan entry first, or do the task on the session model.

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

Re-read `resolves_issues` and `refs_issues` against what was actually implemented and correct them
(`checkpoint.py set --set …`). If any resolved issue should only be closed for good after a later
observation (tomorrow's scheduled run, a deploy, a customer confirming), record it with the
condition and the date to ask on, and ask the user for the date if the design did not give one:
`checkpoint.py set --set verify_later='[{"issue": N, "condition": "<observable>", "check_after": "YYYY-MM-DD"}]'`.
Those issues still get a `Closes` line; Phase 5 writes the verification record.

Compose the test plan from `progress.context` (local-app.md §6 lists the local-app lines). Fill in
every `<placeholder>` and every `$VAR` below with literal text before running; the quoted heredoc
does not expand variables. One `Closes #N` line per entry of `resolves_issues` and one `Refs`
line per entry of `refs_issues`; GitHub honours one issue per keyword, so never write
`Closes #16 #17`.

```bash
gh pr create --title "<concise title>" --body "$(cat <<'EOF'
## Summary
<what changed and why, as bullets>

Closes #$ISSUE_NUMBER
Closes #<each further number in resolves_issues, one per line>
Refs #<each number in refs_issues> — <what this PR did and what remains>

## Test plan
- [x] Existing tests pass; new tests cover the change
- [x] Linting passes
<local app verification line(s) when applicable>

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
checkpoint.py set --set pr_number=<number> --set pr_url=<url>
```

Delete the `Refs` line when `refs_issues` is empty.

### `3.8` Review and approval

Invoke `co-dwerker:pr-review`. It runs `pr-review-toolkit:review-pr`, fixes findings until the
review is clean, moves the board item to its `in_review` role in project mode, surfaces discovered work,
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
checkpoint.py mark 5.merge completed
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
Otherwise `checkpoint.py mark 5.ci completed`.

### `5.docs-merge` (when `docs_pr_number` is set; otherwise `--skip docs-merge`)

`gh pr merge $DOCS_PR_NUMBER --repo "$DOCS_REPO" --squash --delete-branch`

No approval step here: the docs repo owner reviews companion docs in GitBook after the sync
(docs skill header). It runs after `5.merge` so published docs never lead the code.

### `5.close-issue`

Close every issue the PR declared it resolves (conventions §10), not only `$ISSUE_NUMBER`. For
each `N` in `resolves_issues`:

```bash
gh issue view $N --repo "$REPO_OWNER_NAME" --json state --jq .state
```

- `OPEN` and not in `verify_later` → the merge did not auto-close it (a missing keyword, or the
  PR merged into a non-default branch):
  `gh issue close $N --repo "$REPO_OWNER_NAME" --reason completed --comment "Resolved by PR #$PR_NUMBER (merged $TODAY). Closed by co-dwerker Phase 5."`
- In `verify_later` (open or closed) → record it and say so on the issue:
  ```bash
  checkpoint.py set --append pending_verification='{"issue": N, "pr": $PR_NUMBER, "condition": "<condition>", "check_after": "<check_after>", "recorded": "$TODAY"}'
  gh issue comment $N --repo "$REPO_OWNER_NAME" --body "Fix merged in PR #$PR_NUMBER. Pending verification: <condition>. co-dwerker will ask about this at the first standup on or after <check_after>."
  ```
  If GitHub already closed it on merge, leave it closed; the record is what brings it back.
- `CLOSED` otherwise → nothing to do.

For each `N` in `refs_issues`: `checkpoint.py set --append reconcile_dismissed='{"issue": N, "pr": $PR_NUMBER}'`.
The PR body mentions them, so without this the next standup's orphan scan offers them as
candidates for closing.

Mark `5.close-issue` completed (and `5.docs-merge` / `5.board` when they ran).

### `5.board` (project mode; otherwise `--skip board`)

`gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_ROLE_DONE_ID`

`$STATUS_ROLE_DONE_ID` is `status_role_map.done`. When it is `null`, say that only the board's own
"Item closed" workflow will move the item and continue.

### `5.cleanup`

- Worktree first: native → `ExitWorktree` with `action: "remove"`; fallback → from the main
  checkout, `git worktree remove "$WORKTREE_PATH"`. Then delete the branch, which the squash merge
  leaves "unmerged" in git's eyes: `git branch -D "$BRANCH_NAME"` and
  `git push origin --delete "$BRANCH_NAME"` (skip the push if the repo auto-deletes head branches).
- Delete the per-issue artifacts left in the main checkout (the worktree's copies went with it):
  `.co-dwerker.baseline-tests.json`, `.co-dwerker.baseline-localapp.json`,
  `.co-dwerker.localapp-*.log`.
- Remove a docs-repo clone only if this session created it (`docs_repo_cloned`).
- `checkpoint.py mark 5.cleanup completed`, `checkpoint.py gate 5` (with the skips that apply),
  then `checkpoint.py finish-issue`.

## Phase 6: Next

### `6.progress`

Show what was completed today and the remaining queue (project mode: item list; repo mode: open
issues with labels). Mark `6.progress` completed.

### `6.queue`

Queue not empty: ask "Issue #N (title) is next in the queue. Start brainstorming?" Options:
**Start #N (Recommended)** → Phase 2 after `checkpoint.py start-issue N --phase 2`; **Pick a
different issue**; **Wrap up** → suggest `/co-dwerker:exit`.

Queue empty: say so and offer `/co-dwerker:new-issue`, picking an existing issue, or
`/co-dwerker:exit`. Mark `6.queue` completed either way.

## First-run setup

Project board fields (project mode) and P0–P3 labels (both modes):
`${CLAUDE_PLUGIN_ROOT}/references/setup-project-board.md`.
