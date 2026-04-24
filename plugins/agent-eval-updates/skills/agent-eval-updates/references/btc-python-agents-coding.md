# BTC-Python-Agents coding reference

When a tuning round includes **code changes** to `Bellwether-AI/BTC-Python-Agents` (not just prompt edits in `Bellwether-AI/BTCAgentPrompts`), follow the full disciplined workflow below. Prompt-only rounds can skip most of this file — but you should still skim "Architectural invariants" when proposing any change.

## Where the authoritative coding rules live

The canonical rules for this codebase live in the repo's own `CLAUDE.md`, always present inside whichever clone you have:

```
<any local clone>/BTC-Python-Agents/CLAUDE.md
```

The parent project always has a clone at `/Users/mattlax/nonedrive/projects/btc_agent_evals/BTC-Python-Agents/`. The user may also keep a separate "pure-code workspace" sibling clone at `/Users/mattlax/nonedrive/projects/BTC-Python-Agents/` for hands-on coding work outside the tuning flow — if that path exists and has `main` checked out cleanly, it's often the freshest reference. Either way, both clones point at the same GitHub repo.

To refresh your understanding of the codebase (agent patterns, RU rules, disabled-function inventory, etc.), read from whichever clone has `main` synced — or use `git show origin/main:CLAUDE.md` directly to guarantee current-tip content regardless of working-tree state.

Further reading referenced by that CLAUDE.md:

- `docs/architecture_overview.md` — high-level design + Mermaid diagram.
- `docs/adding_new_agent.md` — how to register a new agent through the factory/registry.
- `docs/agent_patterns.md` — standard agent behaviours.
- `docs/testing_guide.md` — shared fixtures and helpers.
- `.states/cosmosdb_optimization_summary.md` — full RU-optimization analysis.

## Architectural invariants (must hold for every code change)

These are from the authoritative CLAUDE.md. Violating any of these should halt the change and force a redesign — do not rationalize around them.

### 1. Handler vs Agent separation

**ALL business logic lives in `btc_agents/`. Handlers in `handlers/` only fetch raw data.**

- Handlers (`handlers/`) may: auth, fetch from Azure SDK/APIs/DB, retry, return raw unprocessed data.
- Handlers must NOT: evaluate, score, decide, threshold-compare, interpret.
- Agents (`btc_agents/`) own all decision-making, threshold evaluation, scoring, and recommendation logic.

Correct shape:
```
handler.get_vm_metrics()       → returns raw CPU samples with timestamps
agent._process_raw_metrics()   → counts samples above/below thresholds from config
```

Wrong shape:
```
handler.get_vm_metrics()       → computes averages, returns {"high_cpu": true}
agent.whatever()               → passes through handler's decision
```

If you find yourself wanting to add a threshold comparison in a handler, stop — that logic belongs on the agent side.

### 2. CosmosDB RU optimization

Each agent should have exactly **two** DB writes: `start()` and `complete()` (or `fail()`).

- Do NOT call `update_status("processing")` or similar mid-flight — use `logger.info()` for progress instead. Each `update_status()` is a full document REPLACE (~115 RU) on documents that can be 100KB–5MB.
- Do NOT store the same data in both `input.context` and `structuredResult` — reference by ID instead.
- Do NOT store the full LLM request/response in the doc — just token counts.

Only use `update_status()` when you genuinely need to persist state that must survive a mid-execution crash.

### 3. Testing never mutates production code

**Never change a file in `btc_agents/` or `handlers/` to make a test pass.** If production code is untestable, the test approach must change, not the production code.

- Mock at the boundary: Azure SDK clients, HTTP clients, MCP servers, OpenAI client.
- Use `unittest.mock.patch` and `pytest` fixtures.
- Test both success and error paths.
- Async tests use `pytest-asyncio` (already configured).

### 4. Agent factory / registry

New agents are registered in `btc_agents/agent_registry.py` via `AGENT_CONFIGS` and constructed through `AgentFactory.create("<agent_key>")`. Don't instantiate agents directly from trigger functions — go through the factory. See `docs/adding_new_agent.md` for the end-to-end pattern.

### 5. Disabled functions and tests (don't accidentally re-enable)

Several functions are deliberately disabled for memory-footprint reasons. The repo's CLAUDE.md has the authoritative table. Common ones currently disabled:

- `ticket_enrichment_agent_servicebus` — ServiceBus trigger
- `resume_sanitizer_agent` + `resume_sanitizer_timer` — Blob triggers
- `resume_reviewer_agent` — Blob trigger

Corresponding test files have module-level `pytestmark = pytest.mark.skip(...)` or individual `@pytest.mark.skip`. If your change touches any of these, consult the repo's CLAUDE.md "Disabled Functions and Tests" table before proceeding — don't accidentally re-enable what was intentionally turned off.

### 6. Code style

- Line length 88 (Black).
- Double quotes, space indent.
- Type hints on public APIs (imports from `typing`).
- Docstrings in Google/NumPy style where non-trivial.
- `uv run black .` and `uv run ruff check .` must both be clean before committing.

---

## Code-change workflow (when BTC-Python-Agents is in scope)

Use this flow for any non-trivial code change. It composes existing superpowers skills the same way `/co-dwerker:work` Phase 3 does. Small targeted fixes can skip brainstorming and the formal plan, but every code change still MUST run **Verify (F)**, the **PR review loop (I)**, and the **final lint + test re-run (J)** before user approval.

### A. Brainstorm (only if design is not obvious)

If the code change is more than a small targeted fix — e.g., new deterministic logic, new enrichment field, new gate condition, new filter, new handler — invoke `superpowers:brainstorming` before writing any plan. Don't shortcut it; it explores the problem space, asks clarifying questions, and saves a design doc.

Design docs from brainstorming conventionally land at `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` in the repo. Check if prior rounds already have relevant specs there.

For small fixes (tiny bug fix, adding to an existing exclusion list, extending an existing detector) skip brainstorming and go straight to writing-plans.

### B. Plan

Invoke `superpowers:writing-plans`. It produces a step-by-step plan identifying critical files, trade-offs, and TDD steps.

### C. Isolate

The main workflow's Phase 6 already creates the BTC-Python-Agents worktree at `.worktrees/btc-python-agents-<agent>/` on branch `tuning/<agent>-YYYY-MM-DD` from `origin/main`. Ensure it exists before starting implementation. If you need the full skill-driven worktree experience, `superpowers:using-git-worktrees` is available.

### D. Test-Driven Development (for new deterministic logic)

For any new hard rule, filter, gate, or deterministic detector, invoke `superpowers:test-driven-development`. Red → green → refactor. Write the failing test first, then the minimal implementation.

For modifications to existing logic (e.g., extending an existing skip-phrase list), you can skip formal TDD and just add regression tests alongside the change — but still write tests.

### E. Execute

Invoke `superpowers:executing-plans` (or `superpowers:subagent-driven-development` if the plan has independent parallel tasks). Follow the skill's full TDD + commit cycle.

Honor the architectural invariants throughout. If mid-execution you realize the planned approach violates the handler/agent separation or the RU-optimization rules, stop, re-plan, and loop back to step B.

### F. Verify

Invoke `superpowers:verification-before-completion`. This is the hard gate — don't claim "done" without it passing.

The skill will run (or you run manually from the worktree):

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/.worktrees/btc-python-agents-<agent>

# Lint
uv run ruff check .
uv run black --check .

# Full unit test suite — NOT just the tests for your changed files.
# This catches regressions in tests modified by other PRs that merged
# while you were working on yours (per user's global Pre-Merge Checklist).
uv run pytest
```

All three must pass clean. If `black --check` fails, run `uv run black .` to auto-format, commit separately (style commit), and re-run.

Per user's global CLAUDE.md Pre-Merge Checklist:
- Before considering a PR mergeable, sync with `origin/main` and re-run the full test suite.
- Run `git fetch origin main` and `git merge origin/main` as SEPARATE bash commands (chained `&&` triggers extra permission prompts per user preference).

### G. Commit in logical chunks

Per user's global rule: functionality first, tests second, docs third. Each phase is its own commit with a descriptive message.

Commit message shape (used in prior rounds):

```
<type>(<scope>): <Round N summary>

<1–2 sentence explanation of what changed and why>

- <specific fix 1> (closes #<issue>)
- <specific fix 2> (closes #<issue>)

<optional: local test evidence, merge-conflict note>
```

`commit-commands:commit` can help compose messages, but the shape above is the established project pattern — don't deviate.

### H. Open PR

Open the PR per the main workflow's Phase 8. Body should include failure-pattern table, local testing evidence, `closes #N` references, and the expected CHANGELOG/RELEASE_NOTES conflict note.

### I. PR review loop

**Always** run `pr-review-toolkit:review-pr` against the newly-opened BTC-Python-Agents PR. Loop until clean:

1. Invoke `pr-review-toolkit:review-pr` on the PR.
2. For each finding: decide (accept / push back with reasoning / clarify with user if unclear). Apply accepted fixes in the worktree.
3. After the last fix in a review iteration, re-run the full Verify step (F) — lint + black-check + pytest — and commit + push only if all three are clean.
4. If substantial changes were made in that iteration, re-run `pr-review-toolkit:review-pr`.
5. Repeat until a review pass completes with no new blocking findings.

This loop is non-negotiable for code PRs in BTC-Python-Agents. Prompt-only PRs in BTCAgentPrompts can skip the formal review-toolkit pass (there's no code to lint/test), but ask the user before skipping.

### J. Final lint + test re-run (after the review loop)

**Even if the review loop's last iteration already verified, run lint + tests one final time** as an explicit gate before handing off to the user. The review loop may have ended with a cosmetic change, a comment tweak, or an adjustment that you didn't re-verify — and an Opus-4.7-fueled review can still let through something subtle. This final step exists specifically to catch "oh, I made one more small change after the last verification" drift.

From the BTC-Python-Agents worktree, run as separate commands (not chained with `&&`):

```bash
uv run ruff check .
uv run black --check .
uv run pytest
```

All three must be clean. If any fails, fix, commit, push, re-run. Only proceed to user approval when this final pass is green.

Also do one final sync with main immediately before marking ready:

```bash
git fetch origin main
git merge origin/main
uv run pytest    # re-run after sync to catch cross-PR test-file conflicts
```

### K. User approval and merge

Per the main workflow's Phase 9 (G4 gate), wait for user approval before merging. On approval:

```bash
gh pr merge <N> --repo Bellwether-AI/BTC-Python-Agents --squash --delete-branch
```

Verify CI after merge:

```bash
gh run list --repo Bellwether-AI/BTC-Python-Agents --branch main --limit 1 --json status,conclusion
```

If CI fails, surface immediately to the user. Don't continue the session until it's addressed.

---

## Skills involved (summary)

| When | Skill |
|------|-------|
| Non-obvious design (step A) | `superpowers:brainstorming` |
| Before coding — every code change (step B) | `superpowers:writing-plans` |
| Worktree isolation (step C) | `superpowers:using-git-worktrees` (or main workflow Phase 6) |
| New deterministic logic (step D) | `superpowers:test-driven-development` |
| Implementation (step E) | `superpowers:executing-plans` OR `superpowers:subagent-driven-development` |
| Before claiming done (step F) | `superpowers:verification-before-completion` |
| After PR open (step I) | `pr-review-toolkit:review-pr` |
| Commit messages (step G) | `commit-commands:commit` (optional) |
| Final gate before user approval (step J) | manual lint + test + sync-with-main |

## Related reference: the optional pure-code workspace

If the user has a separate "pure-code" sibling clone at:

```
/Users/mattlax/nonedrive/projects/BTC-Python-Agents/
```

(confirm by listing the path), it's where hands-on day-to-day coding happens outside the tuning flow. That workspace may carry session/state files (`.co-dwerker.state.json`, `.states/`, etc.) recording prior `/co-dwerker:work` sessions — useful context when the user asks "what was I working on last in BTC-Python-Agents?" During a tuning round we don't modify that workspace; we work via the ephemeral worktree under `.worktrees/btc-python-agents-<agent>/`.

If that sibling clone doesn't exist (fresh install, different user, etc.), the `btc_agent_evals` parent project's clone is always present and is sufficient — this whole section is just a "if you see it, here's what it's for" note, not a requirement.
