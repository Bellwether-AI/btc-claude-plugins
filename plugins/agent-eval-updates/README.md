# agent-eval-updates

High-autonomy tuning iteration for BTC Azure Function Agents (`ticket_prioritizer`, `ticket_reviewer`, `hudu_doc_reviewer`, `azure_config_reviewer`, etc.) in the [`btc_agent_evals`](../../../btc_agent_evals) project.

This plugin ships a single skill — `agent-eval-updates` — that runs the full end-to-end eval-review-to-merged-PR iteration loop. Designed to run with high autonomy: the user makes decisions at four gates, the skill does the rest (research, triage, implementation, local testing, PRs, cleanup).

## What the skill does

1. **Phase 0 — Scope (user gate G1):** confirm which agents + since-date + sequence.
2. **Phase 1 — Autonomous context load:** pull CosmosDB evaluations, fetch `origin/main` on both repos, read git history + CHANGELOGs + current prompts + agent code.
3. **Phase 2 — Triage:** pre-fix artifact filter via bundled script, sample-size-aware scoping, prompt-vs-code categorization per pattern, cross-check against recent changelogs.
4. **Phase 3 — Propose (user gate G2):** present structured per-agent proposal packets, use `AskUserQuestion` only for genuine tradeoffs.
5. **Phase 4 — Wait for coding approval (user gate G3).**
6. **Phase 5 — File GH issues** per approved fix in the relevant repo.
7. **Phase 6 — Worktrees + edits:** per-agent worktrees from `origin/main`. For BTC-Python-Agents code changes, follows the full superpowers-skill-driven flow (brainstorming → writing-plans → TDD → executing-plans → verification).
8. **Phase 7 — Local testing:** azurite + func, scratch prompt overlay pattern (no blob upload), 15-minute soak on real ServiceBus backlog + directed webhook replays.
9. **Phase 8 — Docs + PRs:** CHANGELOG + RELEASE_NOTES per agent, open PRs. Code PRs go through `pr-review-toolkit:review-pr` loop + final lint/test gate.
10. **Phase 9 — Merge + cleanup (user gate G4):** resolve expected CHANGELOG conflict between per-agent PRs, stop services, stash leftover state, update `project_state.md` + memory + project `CLAUDE.md` Last Round marker.

## The four user gates

| Gate | Phase | Question |
|------|-------|----------|
| G1 | 0 | Which agents this round? |
| G2 | 3 | Do these proposed fixes land right? (prompt / code / both for each) |
| G3 | 4 | OK to start coding? |
| G4 | 9 | Merge + full wrap-up? |

Everything else runs without pausing. The skill reads git history, studies the data, makes prompt-vs-code tradeoff calls itself, and drives the work to merged PRs.

## Critical invariants

- **Pre-fix artifact filter** every round — compare eval item `_ts` against previous round's fix-PR `mergedAt`. Miss this and you'll invent failure patterns that don't exist.
- **Per-agent branches + per-agent PRs** — never bundle multiple agents. The user wants per-agent revert/audit.
- **Prompt-vs-code analysis** for every failure pattern — not just for obvious code-shaped ones.
- **No blob uploads from this plugin** — CI/CD handles prod blob on merge. Local tests use `LOCAL_PROMPT_BASE_PATH`.
- **Code PRs in BTC-Python-Agents go through the full disciplined flow** — superpowers skills + `pr-review-toolkit:review-pr` loop + final lint/test gate before user approval.
- **Stash, don't discard, leftover working-tree state** in the parent repos.
- **BTC-Python-Agents is Python** — do not apply `DOTNET_ROOT` or other .NET instructions from other Bellwether projects.

## Bundled resources

- `skills/agent-eval-updates/SKILL.md` — main workflow, all 10 phases (0–9), 12 invariants, common gotchas.
- `skills/agent-eval-updates/references/cosmos-query.md` — `query_evals.py` usage + CosmosDB schema + `_ts`-vs-rating-timestamp trap.
- `skills/agent-eval-updates/references/local-testing.md` — scratch-overlay pattern, azurite/func startup, webhook replay crafting, debounce timing, resource-filter semantics.
- `skills/agent-eval-updates/references/triage-patterns.md` — recurring failure-pattern catalog + prompt-vs-code heuristics.
- `skills/agent-eval-updates/references/pr-workflow.md` — branch naming, CHANGELOG conflict resolution, GH issue + PR templates.
- `skills/agent-eval-updates/references/btc-python-agents-coding.md` — BTC-Python-Agents coding invariants (handler/agent separation, RU rules, testing rules) + the full superpowers-driven code-change flow with required PR review loop and final lint gate.
- `skills/agent-eval-updates/scripts/filter_prefix_artifacts.py` — takes an eval JSON + list of prior fix-PR numbers, fetches `mergedAt` via `gh pr view`, filters items by `_ts`, emits post-fix-only JSON + summary.

## Prerequisites

These must be installed separately (already present in a typical Bellwether Claude Code setup):

- **superpowers** — `brainstorming`, `writing-plans`, `using-git-worktrees`, `test-driven-development`, `executing-plans` (or `subagent-driven-development`), `verification-before-completion`
- **pr-review-toolkit** — `review-pr`
- **commit-commands** — `commit` (optional)

Local environment requirements:

- `uv`, `gh` (authenticated), `az` (logged in with access to the CosmosDB subscription)
- Homebrew `func` (Azure Functions Core Tools v4)
- `azurite` via nvm

## Triggers

The skill auto-triggers on phrases like:

- "Let's do another tuning round"
- "Run agent evals"
- "Pull the reviews and iterate"
- "Tune the agents"
- "Round N tuning"
- Any mention of CosmosDB eval ratings, star ratings, or evaluator comments for a BTC agent while in `/Users/mattlax/nonedrive/projects/btc_agent_evals/`.

## Versioning

Semantic versioning per repo convention. See root [CHANGELOG.md](../../CHANGELOG.md) for release history and [RELEASE_NOTES.md](../../RELEASE_NOTES.md) for user-facing notes.

Initial release: `v0.1.0` (2026-04-24).
