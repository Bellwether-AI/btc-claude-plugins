---
name: status
description: Use when the user asks how much of their Claude plan usage is left, when the session window resets, whether extra-usage credits are at risk, or whether the usage limiter is working — "usage status", "how close am I to the limit", "is the limiter running", "why did my tool call get blocked".
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/usage_limiter.py *), Bash(cat ~/.claude/.claude-extra-usage-limiter/*), Bash(tail *), Bash(jq *)
---

# Extra-Usage Limiter: Status

Answer from the guard's own reading, never from memory of an earlier turn.

## 1. Read

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/usage_limiter.py --mode dump
```

## 2. Report

If `ok` is true, give the user, in a short list:

- **Session window**: `session_pct` used, resets at `session_reset`.
- **Weekly window**: `week_pct` used, resets at `week_reset`.
- **Extra-usage credits**: `credits_enabled` (ENABLED means a 100% window rolls straight into
  paid credits), `credits_str` used this month, `spend_limit_reached`.
- **Guard band**: compare `worst_pct` with `config.warn_pct` / `config.block_pct` and say which
  applies: healthy (silent), warn (Claude is told to wind down and checkpoint), or block (tool
  calls are denied except `git add/commit/stash` and memory/scratchpad writes).
- **Data age**: `age_min`; if `stale` is true, say a background refresh has been requested and
  the guard is fail-open until it lands.

If `ok` is false, print the `error` field and where to look:

```bash
tail -20 ~/.claude/.claude-extra-usage-limiter/limiter.log
cat ~/.claude/.claude-extra-usage-limiter/state.json
jq '.cachedUsageUtilization.utilization | keys' ~/.claude.json
```

Explain that the guard reads an undocumented Claude Code cache, so a failed reading usually
means a Claude Code update changed its shape (or the session uses an API key, which has no plan
windows). While the reading is unavailable the hooks allow everything and say so.

## 3. Remind

One sentence: the limiter stops Claude Code's tool calls, which is where the token burn is, but
it cannot stop billing at the account level. On a Teams plan only an org Owner can cap a
member's spend. Extra-usage credits are spent only with the user's explicit approval for that
specific instance.
