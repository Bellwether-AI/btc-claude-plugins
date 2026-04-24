---
name: agent-eval-updates
description: Run a full tuning iteration for BTC Azure Function "Agents" (ticket_prioritizer, ticket_reviewer, hudu_doc_reviewer, azure_config_reviewer, etc.) in the btc_agent_evals project. Pulls fresh human-rated evaluations from CosmosDB, reads recent git history of both BTCAgentPrompts and BTC-Python-Agents so you don't re-fix already-fixed patterns, filters pre-fix artifacts from genuine post-fix failures, analyzes each pattern for prompt-vs-code fix (or both), proposes targeted changes for user approval, implements them in per-agent git worktrees, runs a 15-minute soak + directed webhook replays locally, and opens per-agent PRs. Designed to run with high autonomy — the user only decides on agent scope at the start, approves the proposed fix set, approves the start of coding, and approves the final wrap-up. Use this whenever the user says any variant of "do another tuning round", "run agent evals", "pull the reviews and iterate", "tune the agents", "Round N tuning", or asks about iterating on any BTC agent in /Users/mattlax/nonedrive/projects/btc_agent_evals/ based on reviewer feedback. Also trigger when the user references CosmosDB eval ratings, star ratings, or evaluator comments for a BTC agent.
---

# Agent Eval Updates — BTC Tuning Workflow

This skill runs the end-to-end iteration loop for BTC Azure Function Agents in `/Users/mattlax/nonedrive/projects/btc_agent_evals/`. It is designed to be **high-autonomy**: you do most of the research, analysis, and implementation yourself, and check in with the user only at four gates — scope (Phase 0), proposed fix set (Phase 3), approval to start coding (Phase 4), and full wrap-up (Phase 9).

You are NOT a checklist executor that asks the user every trivial question. You ARE a senior engineer who reads git history, studies the data, thinks through the prompt-vs-code tradeoff for each failure pattern, presents a coherent recommendation, and drives the work to merged PRs. The user is there to make genuine judgment calls, not to babysit.

## When to trigger

- "Let's do another tuning round", "run agent evals", "pull the reviews", "tune the agents", "Round N tuning".
- The user references CosmosDB evaluation data, star ratings, or evaluator comments for any BTC agent.
- Working inside `/Users/mattlax/nonedrive/projects/btc_agent_evals/` and the user asks about improving any agent's output quality.

## Project structure

This parent folder is a container holding multiple GitHub repos side-by-side plus some local tooling. Each repo is cloned into a subfolder with the same name as the repo:

```
/Users/mattlax/nonedrive/projects/btc_agent_evals/             ← parent project folder (NOT itself a git repo)
├── BTC-Python-Agents/         ← clone of github.com/Bellwether-AI/BTC-Python-Agents  (CODE: Python Azure Functions)
├── BTCAgentPrompts/           ← clone of github.com/Bellwether-AI/BTCAgentPrompts    (PROMPTS: markdown system prompts)
├── ConnectWise-MCP-Server/    ← clone of github.com/Bellwether-AI/ConnectWise-MCP-Server (rarely touched)
├── Hudu-MCP-Server/           ← clone of github.com/Bellwether-AI/Hudu-MCP-Server   (rarely touched)
├── eval_data/                 ← query_evals.py outputs (JSON per run); local-only, gitignored
├── query_evals.py             ← CosmosDB pull tool; reuse, do not rewrite
├── project_state.md           ← round-by-round tuning state; append each Round N summary here
├── CLAUDE.md                  ← project instructions + last-round agent default
└── .worktrees/                ← ephemeral git worktrees; created + destroyed each round
```

**Key repo mapping** (commit here, push there, open PRs against main on the matching GitHub repo):

| GitHub repo | Local folder | What lives here | What you edit |
|-------------|--------------|-----------------|---------------|
| `Bellwether-AI/BTC-Python-Agents` | `BTC-Python-Agents/` | Azure Function App (Python 3.12+), all agent logic, handlers, models, tests, CHANGELOG/RELEASE_NOTES | Deterministic code fixes + agent code + tests |
| `Bellwether-AI/BTCAgentPrompts` | `BTCAgentPrompts/` | System prompts (markdown), CHANGELOG/RELEASE_NOTES | Prompt edits |

Prompt PRs go to `BTCAgentPrompts`. Code PRs go to `BTC-Python-Agents`. Feature requests filed as issues typically go to `BTC-Python-Agents` (because they'll be implemented there).

**Tools used locally** (do NOT import instructions from other Bellwether projects):
- `uv` for Python dependency + execution (`uv run python ...`, `uv run func start`, `uv run pytest`).
- `func` from Homebrew (`/opt/homebrew/bin/func`) — Azure Functions Core Tools v4.
- `azurite` via nvm (requires `. ~/.nvm/nvm.sh` first; binary at `~/.nvm/versions/node/*/bin/azurite`).
- `az login` active, with the right subscription selected. CosmosDB lives in `BTC - Sponsored - 6000 annual` subscription — if queries 403, ask the user to `az account set`.
- `gh` for GitHub issues + PRs.

**Do NOT** set `DOTNET_ROOT` or install .NET runtime — those come from PolicyConductor (a different, PowerShell+.NET-based Bellwether project) and do not apply here. **Do NOT** copy `local.settings.json` templates from other projects.

## The four user gates

| Gate | Phase | What you ask | Default |
|------|-------|--------------|---------|
| G1: Scope | 0 | Which agents this round? | Last round's agents (from project `CLAUDE.md`) |
| G2: Fix proposal | 3 | Do these proposed fixes land right, and for each failure, is the fix prompt / code / both? | You propose, user adjusts |
| G3: Start coding | 4 | Approve writing edits, branches, issues? | Wait for explicit "yes" |
| G4: Wrap-up | 9 | Merge + cleanup? | Wait for explicit "yes" |

Everything else runs without pausing. Long research, git archaeology, eval filtering, proposal drafting, local test orchestration — all you.

---

## Phase 0 — Scope (G1)

Check the project `CLAUDE.md` for a `## Last Round` section recording which agents were tuned most recently (this skill writes it there at the end of Phase 9). Use `AskUserQuestion` with those agents as the recommended default.

If no record exists, list available agents with `uv run python query_evals.py --list-agents` and ask.

Also confirm in the same question set:
- **Since-date** for eval pull: look up the previous round's last-merged tuning PR:
  ```bash
  gh pr list --repo Bellwether-AI/BTCAgentPrompts --state merged --limit 5 --json number,title,mergedAt
  gh pr list --repo Bellwether-AI/BTC-Python-Agents --state merged --limit 10 --json number,title,mergedAt
  ```
  Use the most recent tuning-related PR's `mergedAt` as the default.
- **Parallel or sequential** — default parallel (single interaction, independent branches/PRs per agent).

Make one consolidated ask at the start; don't split these across multiple turns.

---

## Phase 1 — Autonomous Context Load

Do all of this without pausing:

### 1a. Pull evaluations

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals
uv run python query_evals.py -a <agent> --since YYYY-MM-DDT00:00:00Z
# one run per agent under scope
```

Outputs land in `eval_data/<agent>_evals_<timestamp>.json` (full) and `<agent>_summary_<timestamp>.json` (extracted).

### 1b. Fetch fresh origin/main on both repos (no checkout)

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/BTCAgentPrompts && git fetch origin
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/BTC-Python-Agents && git fetch origin
```

**Do NOT** check out main or otherwise disturb the working trees. They may contain leftover modifications from prior sessions — preserve those for Phase 9 cleanup. Use `origin/main` directly when you need the current state of files.

### 1c. Git history analysis (critical — this is what makes Round N+1 not re-fix Round N's patterns)

For each repo, read since the since-date:

```bash
# BTCAgentPrompts
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/BTCAgentPrompts
git log --oneline origin/main --since=YYYY-MM-DD
git log --stat  origin/main --since=YYYY-MM-DD
git show origin/main:CHANGELOG.md | head -200
git show origin/main:RELEASE_NOTES.md | head -200

# BTC-Python-Agents — especially important: deterministic logic changes live here
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/BTC-Python-Agents
git log --oneline origin/main --since=YYYY-MM-DD
git log --stat  origin/main --since=YYYY-MM-DD
git show origin/main:CHANGELOG.md | head -300
git show origin/main:RELEASE_NOTES.md | head -300
```

Pay special attention to:
- **Inter-round merges** — non-tuning merges that happened between the previous tuning round and now. They can silently shift behavior and change what signals hit the LLM.
- **Recent changes to specific prompts or agent files** for the agents under scope: `git log --follow origin/main -- <specific_file>`.
- **Deterministic logic added in prior rounds** — skip-phrase detection, override detection, status gates, board whitelists, resource filters, API field lists, note-type handling, identifier matching. If a "new" failure pattern in this round overlaps with something a prior round added deterministic logic for, the fix may be tuning the existing logic rather than writing new logic.

### 1d. Read current prompts + agent code (from origin/main, not the working tree)

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/BTCAgentPrompts
git show origin/main:prompts/ServiceDeskLeadAssistant/TicketPrioritizerAgent/TicketPrioritizerAgent.md
git show origin/main:prompts/SupportManagerAssistant/TicketReviewerAgent/TicketReviewerAgent.md

cd /Users/mattlax/nonedrive/projects/btc_agent_evals/BTC-Python-Agents
git show origin/main:btc_agents/ticket_prioritizer_agent.py
git show origin/main:btc_agents/ticket_reviewer_agent.py
git show origin/main:handlers/ticket_reviewer_handler.py
git show origin/main:handlers/connectwise_handler.py
# ...whatever is relevant to the agents under scope; see BTC-Python-Agents/CLAUDE.md for the mapping
```

### 1e. Read prior tuning memory

Pull `~/.claude/projects/-Users-mattlax-nonedrive-projects/memory/btc-agent-evals.md` for compact round-by-round history. Check `MEMORY.md` for the BTC Agent Evals project entry (current as-of date + PR links). Use `feedback_btc_evals_branching.md` as the authoritative rule for branch naming + per-agent splits.

---

## Phase 2 — Triage (autonomous)

### 2a. Pre-fix artifact filter

**Critical.** Eval items carry two timestamps: `_ts` is when the LLM ran; `content.ratingDetails.timestamp` is when the human rated. If the previous round's fix PR merged + deployed at time T, any item with `_ts < T_deployed` is a pre-fix artifact and must be excluded from genuine-failure analysis regardless of rating timestamp.

Use the bundled helper (resolved via the plugin root so it works no matter how the plugin was installed):

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/agent-eval-updates/scripts/filter_prefix_artifacts.py" \
  --input eval_data/<agent>_evals_<timestamp>.json \
  --prior-fixes 70,71,16 \
  --repo-map "70=BTC-Python-Agents,71=BTC-Python-Agents,16=BTCAgentPrompts" \
  --output eval_data/<agent>_post_fix_<timestamp>.json
```

If `${CLAUDE_PLUGIN_ROOT}` is not set (e.g. the skill is being invoked outside the plugin loader), fall back to a relative path from the skill directory: `python scripts/filter_prefix_artifacts.py ...`.

The script fetches `mergedAt` for each prior-fix PR via `gh pr view`, compares each eval item's `_ts` against the latest prior-fix merge time, writes a filtered JSON, and prints a summary: `N pre-fix artifacts excluded, M post-fix items retained, K×1⭐ L×2⭐ ...`.

If the filter excludes >30% of the sample, call that out in the Phase 3 proposal — it means Round N-1's fix landed close to the eval window and may have handled most of the apparent failures.

### 2b. Sample-size policy

State the effective post-fix sample per agent and scope the round accordingly:

| Post-fix sample | Scope posture |
|-----------------|---------------|
| 0–4 items | Narrow, targeted fixes only. Resist broad prompt rewrites. |
| 5–20 items | Standard round — address 2–4 failure patterns. |
| 20+ items | Broad round — can consider larger prompt restructures + deterministic logic additions. |

### 2c. Pattern grouping with prompt-vs-code analysis

For each post-fix 1–3 star item, extract: ticket ID, evaluator comment (verbatim), LLM output summary, and which prompt rule or code path is implicated. Group by root cause.

**For every pattern, the prompt-vs-code question is asked — no exceptions.** Framing:

- **Judgment call / nuance** → prompt fix (e.g., "recurring + user can work = P3", N/A rules, scoring calibration).
- **Hard rule / deterministic signal** → code fix (e.g., skip-phrase list, status/board gate, API field addition, override prefix, member-matching algorithm).
- **Input data gap** → code fix (missing enrichment field, wrong note-type handling, missing API call).
- **Both** → change prompt AND code (rare but real — e.g., add a new field to enrichment AND teach the prompt how to use it).

**Cross-check against git history.** Before proposing any fix, ask: "is there already deterministic logic in `BTC-Python-Agents` that *should* have caught this, and the failure is because it's misconfigured or the prompt isn't leveraging it?" If yes, the fix is usually to the existing logic, not new logic.

Separate genuine failures from **feature requests** — a 4-star rating with a comment like "correct but we shouldn't review these users at all" is a feature request that gets an issue in `BTC-Python-Agents`, not a prompt fix.

### 2d. Compose the proposal packet

One structured packet per agent:

```
AGENT: <name>
  Post-fix sample: N items (rating distribution)
  Pre-fix artifacts excluded: M (from filter output)

  PATTERN 1: <one-line summary>
    Representative tickets: #X, #Y
    Evaluator quote: "..."
    Root cause: <which prompt rule / which code path>
    Fix type: prompt | code | both
    Proposed change:
      - If prompt: exact section + new wording
      - If code: file, function, behavior change
    Rationale + existing-logic cross-check: <...>
    Maps to issue: (to be filed in Phase 5)

  PATTERN 2: ...

  FEATURE REQUEST (if any): ...
```

---

## Phase 3 — Propose (G2 gate)

Present the per-agent proposal packets to the user. Use `AskUserQuestion` where genuine choices exist (e.g., two viable wordings, add-new-N/A-rule vs tighten-existing-rule, prompt-only vs prompt+code for a given pattern). Do NOT use `AskUserQuestion` to ask "does this look good?" — present the packet, then ask targeted questions on the genuine tradeoffs.

Do not begin writing any files, creating any branches, or filing any issues until the user has signed off on the fix set.

---

## Phase 4 — Wait for coding approval (G3 gate)

After proposal sign-off, explicitly ask: "OK to proceed with filing issues, creating branches, and applying edits?" Per the user's global CLAUDE.md, exiting plan mode or signing off on a proposal does NOT itself authorize coding. Wait for an explicit approval line.

---

## Phase 5 — File Issues

One GH issue per approved fix in the appropriate repo:

- Prompt fixes → `gh issue create --repo Bellwether-AI/BTCAgentPrompts ...`
- Code fixes → `gh issue create --repo Bellwether-AI/BTC-Python-Agents ...`
- Deferred feature requests → typically `Bellwether-AI/BTC-Python-Agents` (since that's where they'd be implemented).

Issue body template: source (round + representative ticket IDs), problem, root cause (specific file/line or prompt section), proposed fix, acceptance criteria.

Capture issue numbers — PR bodies will reference them and commit bodies will `closes #N`.

---

## Phase 6 — Worktrees + Edits

One worktree per `(repo × agent)` pair — always from `origin/main`, never from the working tree:

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals
mkdir -p .worktrees

# Prompt worktrees (one per agent) — only for agents with prompt changes
cd BTCAgentPrompts
git worktree add ../.worktrees/btc-agent-prompts-<agent> -b tuning/<agent>-YYYY-MM-DD origin/main

# Code worktrees (one per agent) — only for agents with code changes
cd ../BTC-Python-Agents
git worktree add ../.worktrees/btc-python-agents-<agent> -b tuning/<agent>-YYYY-MM-DD origin/main
```

Branch naming: `tuning/<agent_name>-YYYY-MM-DD`. One branch per agent per repo. See memory `feedback_btc_evals_branching.md` — do NOT bundle.

Apply edits inside each worktree. Prompt-only worktrees (`BTCAgentPrompts/`) can commit directly.

**If code changed in `BTC-Python-Agents` worktree(s), DO NOT just "run ruff+pytest".** Follow the full disciplined flow in `references/btc-python-agents-coding.md`, which composes superpowers skills the same way `/co-dwerker:work` Phase 3 does:

1. `superpowers:brainstorming` (if design isn't obvious)
2. `superpowers:writing-plans` (every code change)
3. `superpowers:test-driven-development` (for new deterministic logic)
4. `superpowers:executing-plans` or `superpowers:subagent-driven-development`
5. `superpowers:verification-before-completion` (hard gate — lint + black --check + full pytest)
6. Logical-chunk commits (functionality → tests → docs)

The reference also carries the **architectural invariants** from the BTC-Python-Agents repo's own `CLAUDE.md` that code changes must honor:
- Handler vs Agent separation (business logic ONLY in `btc_agents/`)
- CosmosDB RU optimization (2 writes max, `logger.info()` not `update_status()` for progress)
- Tests never mutate production code
- Agent factory/registry for new agents
- Disabled-function inventory (don't accidentally re-enable what's intentionally off)

Read `references/btc-python-agents-coding.md` before touching any file in a `btc-python-agents-<agent>/` worktree.

---

## Phase 7 — Local Testing (autonomous)

The standard flow every round:

### 7a. Start the local stack

```bash
# azurite (nvm-based)
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/BTC-Python-Agents
mkdir -p __azurite__
export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
nohup azurite --silent --location __azurite__ --debug __azurite__/debug.log > __azurite__/stdout.log 2>&1 &

# func
nohup uv run func start > ../func-start.log 2>&1 &
```

### 7b. Set up the scratch prompt overlay (no blob upload)

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals
mkdir -p .worktrees/test-prompts
cd BTCAgentPrompts
git archive origin/main prompts/ | tar -x -C ../.worktrees/test-prompts/

# Overlay each agent worktree's edited prompt(s) on top of origin/main baseline
cp ../.worktrees/btc-agent-prompts-<agent>/prompts/.../<file>.md \
   ../.worktrees/test-prompts/prompts/.../<file>.md
# Repeat for each agent with prompt edits
```

Point `BTC-Python-Agents/local.settings.json` `LOCAL_PROMPT_BASE_PATH` at the scratch dir (absolute path). `USE_BLOB_STORAGE_PROMPTS` should already be `"false"`; leave it.

**Do NOT** upload to the production blob. CI/CD does that on merge.

If code changes landed in a `BTC-Python-Agents` worktree, func MUST be started from that worktree (or symlinked) so the new code is what runs. The scratch overlay only handles prompt changes; code changes need the actual edited source tree.

### 7c. Soak for ~15 minutes on real backlog + traffic

The `ticket-prioritizer-testing` / `ticket-reviewer-testing` ServiceBus subscriptions accumulate real production events. Let the func drain the backlog and pick up live mlax-triggered traffic for ~15 minutes before pushing test webhooks.

Verify scratch prompts actually loaded: grep `func-start.log` for `System prompt length: <N> characters` and confirm `N` matches the edited file's byte count.

### 7d. Push directed test webhooks for the specific failure cases

For each failure pattern, extract the eval item's `input.rawEvent` from the CosmosDB-pulled JSON. Rewrite `member_id` to `claude.test.round<N>` (NOT `mlax`) so `TICKET_*_RESOURCE_FILTER=mlax` prevents any accidental ConnectWise automations on closed historical tickets. LLM evaluation + CosmosDB write still run.

```bash
for tid in <list>; do
  curl -s -X POST http://localhost:7071/api/webhook \
    -H "Content-Type: application/json" \
    --data @/tmp/webhook_${tid}.json
  sleep 2
done
```

### 7e. Watch + evaluate

Tail `func-start.log` filtered to the test ticket IDs + decision/completion keywords. In parallel, query `agent-output-test` CosmosDB container for those ticket IDs since the soak start.

Debounce is 120s default — expect webhook-queued tickets to take 2+ minutes to fire. Skip-phrase / override detectors may intercept some (log it; not a bug).

For each test ticket, evaluate against the evaluator's original desired outcome:
- Did the LLM output match the expected decision / actionability?
- If it diverged, is the divergence justified by *current* ticket state (tickets may have evolved since the eval — files restored, ticket closed, etc.)? That's existing de-escalation logic working correctly, not a tuning failure.

### 7f. Report to the user

Compact evaluation report:
- Soak stats: total items written during the soak, decision distribution per agent, any false positives observed.
- Per-test-ticket result: output vs expected, with reasoning.
- Recommendation: merge as-is / iterate on one pattern / hold.

The user's standard success criterion is **no new false positives** during the soak. Specific test-ticket matches are a secondary signal — their current state may differ from eval-time state.

---

## Phase 8 — Docs + PRs (autonomous, then code-PR review loop)

For each agent worktree that has edits:

1. `CHANGELOG.md` — insert `## [Unreleased] - YYYY-MM-DD Round N Prompt Tuning — <agent>` at the top with line-per-fix entries referencing their issues.
2. `RELEASE_NOTES.md` — prose summary under matching date section.
3. Commit: `tune(<agent>): Round N — <summary>` with body listing each fix + issue.
4. Push: `git push -u origin tuning/<agent>-YYYY-MM-DD`.
5. Open PR with `gh pr create` — body includes failure-pattern table, local-testing evidence, issue references, and an explicit note about the expected CHANGELOG/RELEASE_NOTES conflict with parallel agent PRs in this repo.

Both repos may have PRs this round. Open PRs in each repo that received changes. Reference cross-repo issues where relevant.

### 8a. PR review loop — REQUIRED for code PRs in BTC-Python-Agents

For each PR opened against `Bellwether-AI/BTC-Python-Agents` (not for prompt-only PRs against `BTCAgentPrompts` — those can skip this):

1. Invoke `pr-review-toolkit:review-pr` on the PR.
2. For each finding: decide (accept / push back with reasoning / clarify with user if unclear). Apply accepted fixes in the worktree.
3. After fixes, re-run verification inside the worktree (`uv run ruff check .`, `uv run black --check .`, `uv run pytest` — all three clean) before committing the review-fix commit + pushing.
4. If the fixes were substantial, re-run `pr-review-toolkit:review-pr` to make sure nothing new was introduced.
5. Repeat until a review pass completes with no new blocking findings.

Full detail: `references/btc-python-agents-coding.md` step I.

### 8b. Final lint + test gate — REQUIRED before user approval on code PRs

**Even after the review loop reports clean**, run lint + tests one final time from the code worktree before handing the PR to the user for approval. This catches any last-mile change (a comment tweak, a cosmetic rename, a touched-up docstring) that happened after the last formal verification.

From the BTC-Python-Agents worktree, as **separate** bash commands (chained `&&` triggers extra permission prompts):

```bash
uv run ruff check .
uv run black --check .
uv run pytest
```

Plus one final sync with main + re-test (per user's global Pre-Merge Checklist):

```bash
git fetch origin main
git merge origin/main
uv run pytest
```

All must be green. If anything fails, fix, commit, push, and repeat 8b. Only announce the PR as ready when this final pass is clean.

For prompt-only PRs in `BTCAgentPrompts`, 8a and 8b are optional but a quick user look-over at the prompt wording is still a good idea — offer it rather than skipping silently.

**Expected conflicts:** Per-agent branches insert at the same position in `CHANGELOG.md` + `RELEASE_NOTES.md`. This is intentional — resolve at merge time by keeping BOTH sections. Do not pre-coordinate.

---

## Phase 9 — Merge + Cleanup (G4 gate)

Ask the user: "full wrap-up now, or leave PRs open for review?" If full wrap-up:

1. Merge first PR in a repo: `gh pr merge <N> --squash --delete-branch`.
2. In the next PR's worktree in that repo: `git fetch origin`, then `git merge origin/main`, resolve CHANGELOG + RELEASE_NOTES conflicts (keep BOTH Round N sections, first-merged first then this one), commit, push. Merge. Repeat per PR in that repo.
3. Repeat for the other repo if it has PRs.
4. Stop services: `pkill -f "func start"`, `pkill -f azurite` (follow up with `kill -9 <pids>` if stubborn).
5. Revert `BTC-Python-Agents/local.settings.json` `LOCAL_PROMPT_BASE_PATH` to `../BTCAgentPrompts/prompts`.
6. Remove worktrees + scratch:
   ```bash
   # From the parent repo (BTCAgentPrompts or BTC-Python-Agents), for each worktree:
   git worktree remove ../.worktrees/<name>
   # Then scratch and service dirs:
   rm -rf /Users/mattlax/nonedrive/projects/btc_agent_evals/.worktrees/test-prompts
   rm -rf /Users/mattlax/nonedrive/projects/btc_agent_evals/BTC-Python-Agents/__azurite__
   rm -f /Users/mattlax/nonedrive/projects/btc_agent_evals/func-start.log
   rmdir /Users/mattlax/nonedrive/projects/btc_agent_evals/.worktrees
   ```
7. **Leftover working-tree state** — if `BTCAgentPrompts/` or `BTC-Python-Agents/` primary working trees have accumulated uncommitted modifications from prior rounds, stash (don't discard):
   ```bash
   git stash push -u -m "pre-round-N-cleanup YYYY-MM-DD: leftover state on <branch>"
   git checkout main
   git pull --ff-only origin main
   ```
8. Update `project_state.md` — append Round N section with failure patterns, fixes, PR numbers, local-testing evidence.
9. Update memory `btc-agent-evals.md` + `MEMORY.md` BTC Agent Evals project entry (refresh "as-of" date + PR links).
10. Update project `CLAUDE.md` (or a `## Last Round` section therein) — record which agents were tuned this round so next round's Phase 0 can default to them.

---

## Critical invariants (don't deviate)

1. **Pre-fix artifact filter** on every round — `_ts` vs last round's fix PR merge time. Miss this and you'll invent failure patterns that don't exist.
2. **Per-agent branches + PRs** — never bundle. See `feedback_btc_evals_branching.md`.
3. **Prompt-vs-code analysis required for every failure pattern** — the question is always asked, even if the answer is "prompt only this time."
4. **Cross-check against recent CHANGELOGs before proposing new logic** — avoid re-fixing.
5. **No blob upload from this skill.** CI/CD handles prod blob on merge. Local tests use `LOCAL_PROMPT_BASE_PATH`.
6. **Scratch overlay pattern for local tests** — one func instance serves overlaid prompts from multiple per-agent worktrees.
7. **Wait for explicit coding approval** (G3) even after proposal sign-off. User's global CLAUDE.md rule.
8. **Stash, don't discard, leftover working-tree state**.
9. **This is Python Azure Functions** — do not apply `DOTNET_ROOT` or other .NET instructions from PolicyConductor or similar projects.
10. **Accept the CHANGELOG conflict** between per-agent PRs in the same repo — it's the price of the per-agent split.
11. **Code PRs in BTC-Python-Agents go through the full disciplined flow** (superpowers skills, architectural invariants, PR review loop). See `references/btc-python-agents-coding.md`. Do NOT shortcut to "ruff check && pytest" for a BTC-Python-Agents code change.
12. **Final lint + test after the PR review loop** (Phase 8b) — even if the last review iteration was "clean", re-run `ruff check .`, `black --check .`, `pytest` one last time as an explicit gate before user approval. Catches drift from small post-review edits.

---

## Common gotchas

- `az account show` may be on the wrong subscription. CosmosDB lives in `BTC - Sponsored - 6000 annual`. Ask user to `az account set` if queries 403.
- `TICKET_*_RESOURCE_FILTER=mlax` only gates *automations* (CW writes). LLM evaluation + CosmosDB output run regardless. Safe to webhook with non-mlax `member_id` for test replays on closed historical tickets.
- Debounce = 120s default; DebounceWorker timer every 2s after due. Webhook-queued tickets don't execute instantly.
- Skip-phrase and override detectors (Round 3 deterministic logic) may intercept test tickets containing phrases like "do not prioritize" in notes from prior rounds. Not a bug; log it.
- ServiceBus testing subscriptions accumulate real traffic; freshly-started func spends time draining backlog. The 15-minute soak absorbs this.
- Tickets may have evolved since their original eval — `no_change` when an issue has been resolved since is correct behavior (de-escalation rules working), not a tuning failure.
- Chained git commands with `&&` sometimes trigger extra permission prompts per the user's global CLAUDE.md pre-merge checklist note; prefer running git commands as separate Bash calls when it matters.

---

## What this skill does NOT do

- Build new agents from scratch — see `BTC-Python-Agents/CLAUDE.md`.
- Handle schema migrations — separate workstream.
- Merge PRs without user approval for full wrap-up.
- Discard leftover local state — always stash.

---

## Reference files

- `references/cosmos-query.md` — `query_evals.py` usage, CosmosDB document schema, filtering patterns.
- `references/local-testing.md` — scratch-overlay details, azurite/func startup, webhook replay crafting, debounce timing, resource-filter semantics.
- `references/triage-patterns.md` — recurring failure pattern categories from prior rounds and the prompt-vs-code heuristics that apply to each.
- `references/pr-workflow.md` — per-agent branch naming, CHANGELOG/RELEASE_NOTES conflict resolution, GH issue + PR body templates.
- `references/btc-python-agents-coding.md` — **REQUIRED READING when a round includes code changes to BTC-Python-Agents.** Architectural invariants (handler/agent separation, CosmosDB RU rules, testing-never-mutates-production), superpowers-skill-driven implementation flow (brainstorm → plan → TDD → execute → verify), PR review loop, and the final lint + test gate before handoff.

## Bundled scripts

- `scripts/filter_prefix_artifacts.py` — takes an eval JSON + list of prior fix-PR numbers across both repos, fetches `mergedAt` via `gh pr view`, filters items by `_ts`, emits post-fix-only JSON + a summary.
