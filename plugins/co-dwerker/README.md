# co-dwerker

Structured daily development workflow plugin for Claude Code. Takes GitHub issues from standup
to merged PR by composing the superpowers and pr-review-toolkit skills, verifies the app actually
boots before a PR is opened, and persists enough state that the next session resumes exactly
where the last one stopped.

Two work modes, remembered per repo:

- **Repo mode** — GitHub Issues with P0–P3 priority labels; no board required
- **Project mode** — a GitHub Projects board with Status and Priority fields

## Skills

| Skill | Use it for |
|-------|-----------|
| `/co-dwerker:work` | The full session: repo detection, resume, standup, brainstorm, execute, docs, close, next |
| `/co-dwerker:pr-review` | Review any PR: automated review, fix findings, board update, approval gate |
| `/co-dwerker:docs` | Create or update companion documentation for a PR or issue |
| `/co-dwerker:new-issue` | Create a GitHub issue, with board priority/status in project mode |
| `/co-dwerker:exit` | Wind down: state file, board, memories, session record, summary |

`/co-dwerker:work-bellwether-project` remains as a hidden alias that redirects to `work`.

## Workflow

```
Repo Detection → Resume Check → Mode → Project* → Standup → Brainstorm → Execute → Docs** → Close → Next
                                                      ^                                             |
                                                      +---------------------- loop -----------------+
```

\* project mode only · \*\* also standalone via `/co-dwerker:docs`

**Execute** runs autonomously from an approved design to a review-ready PR: baseline tests,
baseline local-app boot, plan, isolate in a worktree, implement with TDD, verify tests, verify
the app boots and diff its logs against the baseline, changelog, PR, review. Every step is
checkpointed to `.co-dwerker.state.json` so nothing is skipped and a crash or compacted context
resumes at the right step.

## What v1.0.0 changed

Built for current Claude Code on Fable-class models:

- **Checkpoints instead of task tools.** Step tracking through `TaskCreate` silently did nothing
  on Fable 5 / Opus 4.8 / Sonnet 5 (those tools are off by default). `scripts/checkpoint.py`
  writes progress into the state file at every step boundary and gates each phase on it.
- **Scripts for the deterministic work.** `localapp_capture.py` boots the app, watches it, and
  records normalized errors and warnings; `localapp_diff.py` diffs baseline against verification.
  One script for both runs means the diff compares like with like.
- **Model policy.** Suggests `/model best` (latest Fable where available, else Opus) and lets
  subagents inherit the session model. Never Haiku.
- **`skills/` layout** with `${CLAUDE_PLUGIN_ROOT}` paths, structured `AskUserQuestion` gates,
  native-worktree-aware cleanup, and waits that the Bash tool can actually execute.
- **Half the size.** The work skill went from 786 to ~350 lines; shared conventions live in one
  reference file instead of five copies.

## Prerequisites

Install separately:

- **superpowers** — brainstorming, writing-plans, executing-plans / subagent-driven-development,
  verification-before-completion, using-git-worktrees
- **pr-review-toolkit** — review-pr
- **commit-commands** — commit
- **episodic-memory** — search-conversations

Plus `gh` (authenticated) and `python3` (3.9+, stdlib only). The skills run the scripts as
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py`, which each skill pre-approves via `allowed-tools`.
The capture script starts your app in its own process group and always stops it (TERM, then KILL)
when the watch ends.

## Model policy

co-dwerker performs best on the most capable model available. At session start it suggests
`/model best` if you are not already there. Subagents are dispatched without a `model` override so
they inherit the session's model; `fork` subagents also inherit the conversation. Haiku is never
used. Cost is managed by running at most two subagents at a time, not by lowering model quality.

## Files the plugin writes

| File | Where | Purpose |
|------|-------|---------|
| `.co-dwerker.json` | repo root, committed | `docs_repo`, `docs_path`, `local_app_command`, `local_app_skip`, `dismissed_warnings` |
| `.co-dwerker.state.json` | main checkout, git-excluded | live `progress` checkpoints plus `last_session` summary |
| `~/.claude/co-dwerker-last-repo.json` | home | lets `work` find the repo when launched elsewhere |
| `.git/info/exclude` | clone-local | the scripts add the state file and the per-issue artifact names below; no committed file is edited |
| `.co-dwerker.baseline-tests.json` | repo root, git-excluded | pre-existing test/lint failures (per issue) |
| `.co-dwerker.baseline-localapp.json`, `.co-dwerker.verify-localapp.json`, `.co-dwerker.localapp-diff.json`, `.co-dwerker.localapp-*.log` | repo root, git-excluded | local-app captures and diff (per issue) |

Schemas: `references/conventions.md` §9.

## Layout

```
plugins/co-dwerker/
├── skills/<name>/SKILL.md      work, exit, pr-review, docs, new-issue, work-bellwether-project (hidden)
├── references/                 conventions, repo-detection, baseline-tests, local-app, setup-project-board
├── scripts/                    checkpoint.py, localapp_capture.py, localapp_diff.py, tests/
└── pyproject.toml              ruff / black / pytest config
```

## GitHub Project board (project mode)

Expected fields, created on first run if missing:

| Field | Type | Values |
|-------|------|--------|
| Status | Single select | Backlog, Ready, In Progress, In Review, Done |
| Priority | Single select | P0-Critical, P1-High, P2-Medium, P3-Low |

## GitHub labels (both modes)

Created on first run if missing: `P0-Critical` (#B60205), `P1-High` (#D93F0B), `P2-Medium`
(#FBCA04), `P3-Low` (#0E8A16).

## Development

```bash
cd plugins/co-dwerker
uvx ruff check scripts && uvx black --check scripts
uvx --from pytest pytest
git ls-files -s scripts/*.py        # every script must be mode 100755
```

## Installation

```bash
/plugin install co-dwerker@btc-claude-plugins
```
