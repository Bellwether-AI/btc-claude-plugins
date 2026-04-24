# Triage patterns reference

Recurring failure-pattern categories from prior tuning rounds, with prompt-vs-code heuristics. Use this to quickly classify new patterns during Phase 2c.

## Prompt-vs-code decision framing

Every failure pattern is one of these:

| Category | Example | Fix type |
|----------|---------|----------|
| Judgment call / nuance | "Recurring + user can work = P3" | **Prompt** |
| N/A / exclusion list addition | "Mobile devices don't need configs" | **Prompt** |
| Scoring calibration | "Valid dropdown ≥ score 1" | **Prompt** |
| Rewording guidance for an existing reject | "Tell engineer to mark note Resolution-type" | **Prompt** |
| Hard rule (deterministic trigger) | "Skip tickets with 'do not prioritize' in notes" | **Code** |
| Status / board / role gate | "Skip Closed/Completed before LLM" | **Code** |
| API field addition / enrichment gap | "Fetch internalAnalysis + resolution fields" | **Code** |
| Override prefix detection | "Override Review: approve → approve" | **Code** |
| Matching algorithm | "Match engineer by identifier not name" | **Code** |
| New field added → prompt must use it | "member/identifier now in notes" | **Both** |

**Cross-check every pattern against the changelog** before proposing new logic:

- Did a prior round already add deterministic logic for this case? If so, fix is usually *tuning that existing logic* (add to skip-phrase list, expand N/A exceptions), not adding parallel logic.
- Does the prompt already reference a field the code doesn't fetch? That's a code fix (enrichment gap), not a prompt rewrite.

## Pattern catalog from prior rounds

### ticket_prioritizer

**Over-escalation to P1 (pattern)**
- Symptoms: at-risk infrastructure (disk failing but device online), single user blocked escalated to P1, infrastructure-without-actual-outage treated as P1.
- Fixed in: Round 1/2 (hard rules: at-risk ≠ P1, single user ≠ P1).
- If resurfaces: check if a new phrasing is evading the existing prompt rules, OR if the rules got watered down in a later round.

**Over-escalation P3→P2 (pattern)**
- Symptoms: potential issues, slow performance, requests, projects escalated to P2 despite no actual work stoppage.
- Fixed in: Round 2 (explicit P3 examples: slow PC, printers, terminations, cameras, account provisioning).
- If resurfaces: probably missing a specific example; add to P3 signals list.

**Under-escalation at P3 (pattern)**
- Symptoms: single user with FULL work stoppage left at P3.
- Fixed in: Round 2 (P2 threshold clarified: work stoppage must be EXPLICIT).
- If resurfaces: check that the prompt still requires explicit language and hasn't added ambiguous override cases.

**Timing/context ignored (pattern)**
- Symptoms: parts ordered + waiting, user unresponsive 20+ hours, issue already resolved — all escalated based on initial severity.
- Fixed in: Round 2 (de-escalation rules: evaluate CURRENT state, parts-ordered→P3, unresponsive 12hrs→P3).
- If resurfaces: prompt may not be applying current-state rule enough; add specific examples.

**Recurring intermittent (pattern)**
- Symptoms: "recurring" label drives escalation even when current occurrence isn't work-stopping.
- Fixed in: Round 4 (recurring + user-can-work = P3).

**Data loss under-escalation (pattern)**
- Symptoms: shared-server data loss left at P3 because no one is *currently* blocked.
- Fixed in: Round 4 (data loss on shared files = P2 minimum regardless of current work stoppage).

**False user_count (pattern)**
- Symptoms: termination/offboarding tickets inflate "affected user count" because the terminated user gets counted.
- Fixed in: Round 2 (admin task exception: termination subjects are NOT affected users).

### ticket_reviewer

**Configuration Attachment false positives (pattern)**
- Symptoms: fails tickets for missing Configuration when there is no relevant device (email work, mobile, new device, phone troubleshooting, cloud apps).
- Fixed in: Rounds 1+2 (N/A list: email/cloud/mobile/technician's-own-PC; trigger phrases required for fail).
- If resurfaces: likely a new kind of device-adjacent language evading the trigger list; add to N/A exceptions.

**Third-Party Involvement misidentification (pattern)**
- Symptoms:
  - Internal teams (SOC, BTC) flagged as third-party.
  - Internal tools (Traceless, Huntress, Auvik, NinjaRMM) flagged as third-party.
  - Visiting vendor websites for drivers = flagged as vendor contact.
  - Naming a vendor platform as the subject of admin work (KnowBe4, Dropbox) = flagged as vendor contact.
- Fixed in: Rounds 1/2/4 (exclusion list + explicit "only when external SUPPORT team is contacted").

**Reason Field over-penalization (pattern)**
- Symptoms: valid CW dropdown selection scored 0 because it's "too generic".
- Fixed in: Round 2 (valid dropdown = ALWAYS minimum score 1, never 0).

**Resolution Documentation false rejections (pattern — multiple sub-cases)**
- Symptoms:
  - LLM can't identify closing engineer (matches on name, fails on nicknames/multi-word).
  - LLM misses resolution notes because API didn't fetch `internalAnalysis` or `resolution` fields.
  - Work IS documented but not tagged as Resolution type — rejection implies work is missing.
- Fixed in:
  - Round 3: added `member/identifier` to API fields + prompt; switched to `_get_note_text()` helper.
  - Round 3.5: switched handler to `get_all_ticket_notes`.
  - Fix #69 (PR #70, #16): cemented identifier-based engineer matching.
  - Round 4: split "no documentation" from "no Resolution-typed documentation" in the prompt, with reword-guidance instead of re-do-work implication.

**Closing engineer identification (pattern)**
- Symptoms: multi-engineer tickets evaluated against the wrong engineer's work.
- Fixed in: Round 2 + Round 3 fix PRs (explicitly evaluate CLOSING engineer; match by `member.identifier`).

**Unclosed ticket processing (pattern)**
- Symptoms: reviewer evaluates tickets that aren't yet Closed/Completed.
- Fixed in: Round 1 (status check in `ticket_reviewer_handler` skips non-Closed/Completed).
- This is a **code** fix, a canonical example of status-gate logic before LLM.

**User-based skip (feature request, not a failure)**
- Symptoms: evaluator says "correct, but we shouldn't review these users" (bullpen devices, ephemeral accounts).
- Deferred to BTC-Python-Agents #88 (Round 4).

## Heuristics for mapping evaluator language → fix type

Evaluator says something like → most likely fix type:

- *"this should have been skipped entirely"* → **code** (skip/gate logic before LLM)
- *"the prompt should know that..."* → **prompt** (judgment call)
- *"the API isn't returning X"* / *"X isn't visible"* → **code** (enrichment gap)
- *"when in doubt, do Y"* → **prompt** (scoring/default rule)
- *"the wording of the rejection is misleading"* → **prompt** (reword guidance, not scoring change)
- *"we've already added Z in a prior round, but it's not being applied"* → **code** (existing logic needs fix or tuning)
- *"this kind of ticket should auto-approve"* → **code** (override detection) OR **prompt** (add to scoring rules)

## When to propose code changes even if patterns look prompt-shaped

- If three or more prompt-fixable patterns cluster around the same root cause (e.g., "LLM keeps missing certain data") — consider whether the underlying enrichment is incomplete, which is a code fix.
- If a prompt rule is getting longer and longer to cover a class of cases (exception lists growing), consider whether a deterministic pre-filter is a better shape for it.
- If the evaluator comment references the *mechanism* of the failure ("it's running on closed tickets", "it's not seeing internal notes"), that's almost always a code fix.

## When to resist code changes

- Small sample (< 5 post-fix items) — prefer narrow prompt tweaks; code changes need broader validation.
- Pattern already has deterministic logic that's working most of the time — tune the existing logic, don't add parallel paths.
- The fix would require new enrichment data that's expensive to fetch — consider if a prompt nudge gets 80% of the way there.
