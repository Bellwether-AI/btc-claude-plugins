# PR workflow reference

Branch naming, issue templates, PR body templates, and conflict resolution for BTC agent tuning rounds.

## Branching convention

One branch per agent per repo. Date-stamped.

```
tuning/<agent_name>-YYYY-MM-DD
```

Examples:
- `tuning/ticket_prioritizer-2026-04-17` in both `Bellwether-AI/BTCAgentPrompts` and `Bellwether-AI/BTC-Python-Agents` (separate branches in each repo with matching names).
- `tuning/ticket_reviewer-2026-04-17` likewise.

**Never bundle** multiple agents on one branch. Per-agent branching gives the user per-agent revert and audit. See memory `feedback_btc_evals_branching.md`.

Historical variants you'll see in git log (don't create new ones in these styles):
- `tuning/<agent>` (v1)
- `tuning/<agent>-v2` (v2)
- `tuning/YYYY-MM-DD` (Round 3 — bundled both agents; the convention shifted after this)
- `fix/<description>-<issue#>` (targeted fixes outside the tuning cadence)

## Worktree layout

```
/Users/mattlax/nonedrive/projects/btc_agent_evals/
└── .worktrees/
    ├── btc-agent-prompts-<agent>/     # prompt edits for <agent>
    ├── btc-python-agents-<agent>/     # code edits for <agent>  (only if code changes)
    └── test-prompts/                  # scratch overlay for Phase 7 local testing
```

Create from `origin/main`, never from the main repo's working tree (which may carry leftover state from prior sessions).

## Issue template

For each approved fix, file one issue in the appropriate repo:

```
Title: <agent>: <short problem summary>

## Source

Round N evaluation analysis (YYYY-MM-DD). CosmosDB item for ticket
**#<ticket_id> "<summary>"** (<company>), evaluated <rating>⭐ by <evaluator>
on <iso_date>.

## Problem

<What the agent did wrong, with exact LLM summary if relevant>

Evaluator feedback verbatim:

> <evaluator comment>

## Root cause

<Which specific prompt rule/line, or which code path, is implicated.
Cite file + section.>

## Proposed fix

<Specific wording change, or function/file/behavior change.>

## Acceptance

<How you'll know it works — usually "local replay of ticket #X returns
<expected decision/actionability>" or "no regression in Round N+1 eval data".>
```

Filed issues must be referenced in commit bodies (`closes #N`) and PR descriptions.

## Commit message template

```
tune(<agent>): Round N — <short summary>

<1-2 sentences on what changed>

- <fix 1 one-line description> (closes #<issue>)
- <fix 2 one-line description> (closes #<issue>)

<Testing evidence line, if any>

<Optional: note about expected CHANGELOG/RELEASE_NOTES conflict with
parallel per-agent branch in this repo>
```

Follow the user's global commit rule: functionality commit first, tests commit second, docs commit last. Each phase is its own commit with a clear message.

## PR body template

```markdown
## Summary

- <one-line per fix — closes #N>
- <one more>
- Prompt-only / Code-only / Prompt + code — no agent code modified / code changes included

## Background

Round N tuning iteration after Round N-1 (merged YYYY-MM-DD via #<PR>, #<PR>).
Pulled evaluator feedback since that date and <N> genuine post-fix failure
patterns identified after pre-fix artifact filtering excluded <M> items.

| Pattern | Ticket | Fix | Issue |
|---------|--------|-----|-------|
| <pattern 1> | #<id> | <fix summary> | #<issue> |
| <pattern 2> | #<id> | <fix summary> | #<issue> |

## Local testing (YYYY-MM-DD)

- Scratch overlay at `.worktrees/test-prompts/prompts` contained both Round N
  branches' edits.
- 15-minute soak against real mlax-triggered traffic: <stats>.
- Webhook replays for <tickets> <status + evaluation>.
- <Any caveats: skip-phrase interception, ticket state evolution, etc.>

## Merge notes

- **Expected conflict**: `CHANGELOG.md` + `RELEASE_NOTES.md` with the parallel
  `tuning/<other_agent>-YYYY-MM-DD` PR. Resolution: keep both Round N sections.
  Not pre-coordinated — per-agent branch split is intentional for audit/revert.
- <Other notes, e.g., feature request issues filed separately>

## Test plan

- [x] Local prompt load verified
- [x] 15+ min soak against new prompt
- [ ] Post-merge: monitor Round N+1 evaluation data for recurrence

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Resolving the expected conflict

When merging the second per-agent PR in a repo, `CHANGELOG.md` + `RELEASE_NOTES.md` will conflict because both PRs insert at the same position in those files.

Resolution recipe:

```bash
# From the second PR's worktree
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/.worktrees/btc-agent-prompts-<agent2>
git fetch origin
git merge origin/main
# Both files will show conflict markers.
```

For each file:
- The `<<<<<<< HEAD` section is this PR's Round N block.
- The `>>>>>>> origin/main` section is the first-merged PR's Round N block.
- Resolution: keep BOTH — usually in order (first-merged first, then this one).

Edit each file, remove all conflict markers, save. Then:

```bash
git add CHANGELOG.md RELEASE_NOTES.md
git commit -m "resolve CHANGELOG/RELEASE_NOTES conflict with <first_agent> Round N (PR #<N>)"
git push
```

Merge the PR: `gh pr merge <num> --squash --delete-branch`.

## Post-merge cleanup

See SKILL.md Phase 9 for the full checklist. The short version:

1. Stop func + azurite.
2. Revert `LOCAL_PROMPT_BASE_PATH` in `BTC-Python-Agents/local.settings.json`.
3. Remove worktrees + scratch dir + `__azurite__` + `func-start.log`.
4. Stash (not discard) any leftover working-tree state in the main repos.
5. Update `project_state.md`, memory files, and project `CLAUDE.md` Last Round marker.

## `gh` cheat sheet

```bash
# List merged PRs since a date (for finding last round's merge date)
gh pr list --repo Bellwether-AI/BTCAgentPrompts --state merged --limit 10 --json number,title,mergedAt
gh pr list --repo Bellwether-AI/BTC-Python-Agents --state merged --limit 10 --json number,title,mergedAt

# Get the exact merge time of a specific PR (for pre-fix artifact filter)
gh pr view <num> --repo Bellwether-AI/BTCAgentPrompts --json mergedAt,state

# Create an issue
gh issue create --repo Bellwether-AI/BTCAgentPrompts --title "..." --body "$(cat <<'EOF'
...issue body...
EOF
)"

# Create a PR from the current worktree
gh pr create --title "..." --body "$(cat <<'EOF'
...pr body...
EOF
)"

# Merge + delete branch
gh pr merge <num> --repo <repo> --squash --delete-branch

# Update an existing PR body (if you realize you made a typo like `closes #17? no, closes #18`)
gh pr edit <num> --repo <repo> --body "..."
```
