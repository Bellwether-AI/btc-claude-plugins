# co-dwerker v1.2.0: issues resolved by a PR get closed, and left-behind issues get caught

**Date:** 2026-09-24
**Plugin:** `plugins/co-dwerker` (v1.1.0 → v1.2.0)
**Status:** approved in conversation (the user asked for the planning session and pre-approved
implementation; design decisions below were made from the evidence and are called out for review)

## 1. Problem

Issues whose fix has merged are being left open, and therefore left in Todo on the project board.
The user discovered this on `Bellwether-Technology/PolicyConductor-Functions-Python#16` and closed
it by hand on 2026-09-24.

Evidence gathered on 2026-09-24:

- PR #22 (merged 2026-09-08) fixed five issues at once (#16 #17 #18 #20 #21). Its body referenced
  them but contained no closing keyword, so GitHub auto-closed nothing. #17, #18, #20, #21 were
  still open 16 days later, in Todo on the board.
- Issue #16 was also deliberately left open pending next-day verification ("verify the 2026-09-09
  05:00 UTC run succeeds"). No later session returned to it.
- PR #49 said "Closes nothing on its own — #43 closes with the frontend PR". The frontend PR did not
  close it either; the user closed #43 by hand on 2026-09-17, and #43 was still in the state file's
  `planned_issues` on 2026-09-23.
- Of 14 merged PRs in that repo, 5 carried a closing keyword and 6 closed nothing.
- The project board is not the failure. Its built-in "Item closed" and "Auto-close issue" workflows
  are enabled, and across all 169 items there were zero closed issues not in Done for that repo.
  The board faithfully mirrors issue state; the issues simply never closed.
- The board's Status options are `User Submitted, Planned, Todo, In progress, Done`. The skills
  assume `Backlog, Ready, In Progress, In Review, Done`. There is no "In Review", so the pr-review
  board step has no valid target and the new-issue skill offers statuses that do not exist.

Root causes in the skill text:

1. The work skill models exactly one issue per PR. `Closes #$ISSUE_NUMBER` names only the active
   issue, and Step 5.close-issue closes only that number. Batched PRs and multi-PR issues fall
   outside the model.
2. There is no "fixed, pending verification" outcome. The only outcomes are open and closed, so the
   agent leaves a comment and nothing tracks the follow-up.
3. Exit step 3 reconciles the board against what the agent remembers, not issue state against
   merged PRs. Since the board already tracks issue state, the step catches nothing.
4. Standup has no "left behind" check, so eight later sessions never surfaced the orphans.
5. Board status names are hard-coded in five places instead of mapped once from the real board.

## 2. Goals and non-goals

Goals:

- Every issue a PR fully resolves is named in the PR with a closing keyword, and Phase 5 closes any
  the merge did not, with a comment linking the PR.
- Issues that need later verification are recorded with the condition and a check-after date, and
  the next standup asks about them.
- Standup and exit both surface open issues that merged PRs reference, and ask close or keep.
- Board transitions work on any board by mapping the real Status options to three roles.

Non-goals:

- No new scripts. The orphan scan is two `gh` calls plus `jq`, run by the agent.
- No change to Phase 3 execution, baselines, local-app verification, or the review pipeline.
- No attempt to auto-close without a human confirmation outside Phase 5. Phase 5 closes only the
  issues the PR itself declared it resolves; everything else is a question.
- No backfill tooling for other repos. The standup check handles backlog gradually.

## 3. Design

### 3.1 The resolution set (work skill, Steps 3.2 and 3.7)

Three new per-issue context keys, all lists of issue numbers in the current repo:

| Key | Meaning | Default |
|-----|---------|---------|
| `resolves_issues` | issues this PR fully resolves; each gets `Closes #N` | `[ISSUE_NUMBER]` |
| `refs_issues` | issues this PR touches but does not resolve; each gets `Refs #N` with a reason | `[]` |
| `verify_later` | subset of `resolves_issues` whose closure waits on an observation | `[]` |

Step 3.2 (plan) sets them: when the plan covers other open issues in full, add them to
`resolves_issues`; when it covers part of one, add it to `refs_issues`. Step 3.7 re-reads them
and may adjust after implementation. The rule stated in the skill: never put an issue under
`Closes` that the PR only partially addresses, and never leave an issue the PR fully fixes out of
`Closes` because "it should be verified first"; that is what `verify_later` is for.

`verify_later` entries carry the condition. Stored as `verify_later='[{"issue": 16, "condition":
"the 2026-09-09 05:00 UTC RefreshBbssamToken run succeeds", "check_after": "2026-09-09"}]'`.

Cross-repo issues are out of scope for these keys; the PR body may still say
`Closes Org/Repo#N` by hand, as PRs #24 and #27 did.

### 3.2 PR body (Step 3.7)

The template's single `Closes #$ISSUE_NUMBER` line becomes one `Closes #N` line per
`resolves_issues` entry, followed by one `Refs #N — <what remains>` line per `refs_issues` entry.
Issues in `verify_later` still get `Closes #N` (GitHub closes them on merge; Phase 5 handles the
verification record instead of reopening).

The skill states why: GitHub only auto-closes on the keywords `close(s|d)`, `fix(es|ed)`,
`resolve(s|d)` immediately followed by `#N`, one issue per keyword. A bare `#N`, a title
reference, or "(#17 #18 #16)" closes nothing, which is exactly what happened to PR #22.

### 3.3 Close (Step 5.close-issue)

Replaces the single-issue text:

```
For each N in resolves_issues:
  state = gh issue view N --repo "$REPO_OWNER_NAME" --json state --jq .state
  if state == OPEN and N not in verify_later:
      gh issue close N --repo "$REPO_OWNER_NAME" --reason completed \
        --comment "Resolved by PR #$PR_NUMBER (merged $TODAY). Closed by co-dwerker Phase 5."
  if N in verify_later (open or closed):
      checkpoint.py set --append pending_verification='{"issue": N, "pr": $PR_NUMBER,
        "condition": "<condition>", "check_after": "<date>", "recorded": "$TODAY"}'
      gh issue comment N --repo "$REPO_OWNER_NAME" --body "Fix merged in PR #$PR_NUMBER.
        Pending verification: <condition>. co-dwerker will ask about this at the first
        standup on or after <date>."
      if state == CLOSED: leave it closed (GitHub closed it on merge); the record is what matters.
```

`pending_verification` is a session-level list (survives `finish-issue`), copied to the top level
of the state file by `end-session`.

### 3.4 Standup: `1.reconcile` ("Left behind")

New step between `1.report` and `1.recommend`, tracked in `checkpoint.py` so `gate 1` requires
it. Both modes. Three sources, one question.

**a. Pending verification.** Entries in `pending_verification` (context, falling back to the
top-level copy) with `check_after <= TODAY`.

**b. Orphan scan.** Open issues referenced by PRs merged in the last 30 days:

```bash
SINCE=$(date -v-30d +%Y-%m-%d 2>/dev/null || date -d '30 days ago' +%Y-%m-%d)
gh pr list --repo "$REPO_OWNER_NAME" --state merged --search "merged:>=$SINCE" \
  --json number,title,body --limit 50 > /tmp/co-dwerker-merged.json
gh issue list --repo "$REPO_OWNER_NAME" --state open --json number,title --limit 200 > /tmp/co-dwerker-open.json
jq -n --slurpfile prs /tmp/co-dwerker-merged.json --slurpfile open /tmp/co-dwerker-open.json '
  ($open[0] | map({key: (.number|tostring), value: .title}) | from_entries) as $open
  | $prs[0][] | . as $pr
  | [ ($pr.body // "") | scan("(?:^|[^A-Za-z0-9_/-])#([0-9]+)") | .[0] ] | unique[]
  | select($open[.] != null)
  | {pr: $pr.number, pr_title: $pr.title, issue: (.|tonumber), issue_title: $open[.]}'
```

Piped to real `jq`, not `gh --jq` (gojq's Go regex differs; the pattern above avoids lookbehind
so it runs in both, but the two-file join needs `--slurpfile`). Bare `#N` references are
candidates, not proof: PR bodies also cite follow-up issues they filed and issue numbers from
other repos. The skill says so, and the user decides.

**c. Planned-queue hygiene.** Any number in `planned_issues` whose issue is closed is dropped
from the list with a one-line note. No question.

**Report and ask.** Add a **Left behind** section to the standup with one line per candidate:
`#N <title> — referenced by merged PR #P <title>` or `#N <title> — pending verification since
<date>: <condition>`. If the section is empty, mark `1.reconcile` completed and say "nothing left
behind". Otherwise one `AskUserQuestion`: **Close all listed as completed (Recommended)** /
**Close some (say which)** / **Leave all open**. Closing uses:

```bash
gh issue close N --repo "$REPO_OWNER_NAME" --reason completed \
  --comment "Latent close (co-dwerker standup $TODAY): resolved by PR #P, merged <date>, which carried no closing keyword for this issue."
```

For a pending-verification entry the comment names the condition instead of the missing keyword.
Every closed or kept-open pending entry is removed from `pending_verification`; a kept-open one
the user still wants tracked gets a new `check_after`. Kept-open orphans are not re-asked: record
them under a session-level `reconcile_dismissed` list of `{issue, pr}` pairs so the same pair is
skipped next time.

### 3.5 Exit step 3: reconcile issues, then the board

Rewritten. First issues, then board, and each only fixes discrepancies.

**Issues.** For every PR in this session's merged set (`--prs-merged` plus `progress.context.pr_number`
when merged): `gh pr view P --json body,mergedAt`, extract same-repo `#N` references with the
same pattern as 3.4, check each for `state == OPEN`, and ask the same three-option question. Then
list `pending_verification` so the summary carries it.

**Board (project mode).** The board's own workflows usually keep Status in step with issue state.
Only look for items that disagree with it:

```bash
gh api graphql -f query='query($org:String!,$num:Int!,$after:String){
  organization(login:$org){projectV2(number:$num){items(first:100,after:$after){
    pageInfo{hasNextPage endCursor}
    nodes{id fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}
      content{__typename ... on Issue{number state repository{nameWithOwner}}}}}}}}' \
  -f org="$REPO_OWNER" -F num=$PROJECT_NUMBER
```

(repeat with `-f after=<endCursor>` while `hasNextPage`). Items where the issue is CLOSED and
Status is not the `done` role, or OPEN and Status is the `done` role, are the discrepancies;
fix the first kind with `item-edit` to `done`, and ask about the second kind. Owner login here
is `$REPO_OWNER`; for a user-owned project the query root is `user(login:)` instead.

### 3.6 Board status roles (Phase 0b, 2.board, pr-review §3, 5.board, new-issue §4)

Phase 0b stops expecting exact option names. After fetching the Status field it builds
`status_role_map` = `{"in_progress": <option id or null>, "in_review": <option id or null>,
"done": <option id or null>}` by case-insensitive name match:

| Role | Accepted names |
|------|----------------|
| `in_progress` | In Progress, In progress, Doing, Active, Working |
| `in_review` | In Review, In review, Review, Reviewing, PR Open |
| `done` | Done, Complete, Completed, Closed, Shipped |

A role with no match is asked once: "This board has no `<role>` status. Which option should
co-dwerker use, or skip that transition?" with the real option names (up to three) plus **Skip
this transition**. `null` means skip. The map is a session-level key so pr-review, new-issue,
and exit read it from the state file. The setup reference still documents the recommended
five-option set as what a new board gets; existing boards are mapped, not rewritten.

Consumers:

- Step 2.board sets `in_progress`; when null, notes "board has no in-progress status; skipping".
- pr-review §3 sets `in_review`; when null, says so and moves on (this replaces the current
  standalone-fetch block, which also gains the same mapping when run standalone).
- Step 5.board sets `done`; when null, says the board's "Item closed" workflow is the only thing
  that will move it and continues.
- new-issue §4 offers the board's real option names (the ones not mapped to `done`, up to three)
  instead of the hard-coded Backlog / Ready / In Progress.

### 3.7 pr-review standalone

Step 0 derives `$ISSUE_NUMBER` from a single `Closes #N`. It now collects every `Closes|Fixes|Resolves
#N` in the body as the resolution set; the first one remains `$ISSUE_NUMBER` for the board item
lookup, and the whole set is stated in the "Reviewing PR #N for issues …" line.

### 3.8 `checkpoint.py`

| Change | Detail |
|--------|--------|
| `PHASES["1"]` | `["fetch", "report", "reconcile", "recommend"]` |
| `SESSION_KEYS` | add `pending_verification`, `reconcile_dismissed`, `status_role_map` |
| `finish-issue` | append every entry of `context.resolves_issues` (ints) to `completed_this_session` in addition to `issue`; remove each from `planned_issues` |
| `end-session` | write `pending_verification` (list, default `[]`) at the top level from context; `last_session` gains nothing new |
| `show` | print `pending_verification` when non-empty, after `completed_this_session` |
| `--append` | already parses JSON objects; add a test that appending a dict works and de-duplicates |

Tests: one per row above, in `scripts/tests/test_checkpoint.py`, following the existing `_run`
helper. `test_mark_and_gate_flow`-style coverage for `gate 1` blocking on a missing `reconcile`.

### 3.9 Documentation and version

- `references/conventions.md` §3 context table: add `resolves_issues`, `refs_issues`,
  `verify_later` (per-issue; written 3.2/3.7, read 3.7/5.close-issue/exit) and
  `pending_verification`, `reconcile_dismissed`, `status_role_map` (session-level). §9 schema:
  top-level `pending_verification`. New §10 "Closing issues": the keyword rule, the resolution
  set, and the reconciliation question, so the skills can point at it instead of repeating it.
- `references/setup-project-board.md`: a paragraph under Required Fields saying existing boards
  are mapped to roles (§3.6) and only new boards get the five-option set.
- `README.md`: workflow summary mentions Left behind and the role mapping.
- `CHANGELOG.md`, `RELEASE_NOTES.md` at the repo root (the repo keeps both there): a
  `co-dwerker v1.2.0` entry each.
- `plugin.json` and `marketplace.json`: 1.1.0 → 1.2.0.

## 4. Error handling

- Every new `gh` call follows conventions §6: a failure stops with the error and a question.
- The orphan scan's 30-day window and 50-PR limit are stated in the skill; a repo with more
  merges than that gets the newest 50, and the skill says so.
- `jq` absent: the skill says to report it rather than emulate the join by hand.
- A `verify_later` entry without a `check_after` date is invalid; Step 3.7 asks for one.
- Reconciliation never closes without the user's answer except inside Phase 5, where the PR
  itself declared the resolution set and the user approved the PR with those `Closes` lines in it.

## 5. Testing and verification

- `checkpoint.py` changes: pytest, ruff, black clean (`uv run --with pytest pytest`, `uvx ruff
  check .`, `uvx black --check .` from `plugins/co-dwerker`).
- The orphan-scan pipeline is run for real against `Bellwether-Technology/PolicyConductor-Functions-Python`
  during implementation. Expected today: PR #22 → #19, #23; PR #49 → #19, #39; PR #40 → #38, #39;
  PR #52 → #53, #54, #55. All of those are follow-ups the PRs filed, which is the "candidate, not
  proof" case the skill text must describe.
- The board discrepancy query is run for real against project 11 (already verified once on
  2026-09-24; it found and fixed one stale item in the frontend repo).
- Skill text review: `skill-creator` audit of the changed skills, plus `pr-review-toolkit:code-reviewer`
  on the Python, per the plugin's established review pattern.

## 6. Cleanup already performed (2026-09-24, not part of the plugin change)

Closed #17, #18, #20, #21 in PolicyConductor-Functions-Python with latent-close comments naming
PR #22; moved frontend #43's board item from In progress to Done; removed closed #43 from the
Python repo's `planned_issues`. The frontend repo's merged PRs showed no orphans (its two bare
hits were cross-repo references to the Python repo's issue numbers).
