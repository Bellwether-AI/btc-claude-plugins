---
name: setup
description: Use when the user asks to install, configure, or repair the extra-usage limiter status line or hooks — "set up the usage limiter", "install the usage status line", "the usage gauge is missing", "finish installing the limiter" — or right after installing the plugin.
disable-model-invocation: true
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage_limiter.py" --mode dump), Bash(jq * ~/.claude/settings.json), Bash(jq * ~/.claude/settings.json > ~/.claude/settings.json.tmp && mv ~/.claude/settings.json.tmp ~/.claude/settings.json), Bash(cp ~/.claude/settings.json ~/.claude/settings.json.bak-*), Bash(mkdir -p ~/.claude/.claude-extra-usage-limiter), Bash(printf '%s' "${CLAUDE_PLUGIN_ROOT}" > ~/.claude/.claude-extra-usage-limiter/plugin-root), Bash(test -f ~/.claude/claude-extra-usage-limiter.json || printf * > ~/.claude/claude-extra-usage-limiter.json), Bash(grep -q claude-extra-usage-limiter:begin ~/.claude/CLAUDE.md*), Bash(cat "${CLAUDE_PLUGIN_ROOT}/references/claude-md-snippet.md" >> ~/.claude/CLAUDE.md), Read, AskUserQuestion
---

# Extra-Usage Limiter: Setup

The plugin's hooks (PreToolUse gate, UserPromptSubmit context, SessionStart self-check) are
active the moment the plugin is enabled. Two things a plugin cannot do for the user are done
here: install the **status line** and remove any **hand-wired copies** of the same hooks so
nothing fires twice. Everything below edits only `~/.claude/settings.json`,
`~/.claude/claude-extra-usage-limiter.json`, the pointer file, and (with consent) `~/.claude/CLAUDE.md`.
Never touch `permissions`, other hooks, or any other key. Always quote `"${CLAUDE_PLUGIN_ROOT}"`;
home directories with spaces are common.

Run the steps in order. Print each command's result briefly. If a command fails, stop, show
the error, and tell the user which steps completed and how to roll back (Step 8).

## Step 1 — Confirm the guard can see plan usage

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage_limiter.py" --mode dump
```

If `"ok": false`, stop and explain the `error` field. Two common causes: the session is signed
in with an API key (there are no plan windows to guard, the plugin does nothing useful), or
Claude Code changed the shape of `cachedUsageUtilization` in `~/.claude.json` (the plugin needs
an update; point the user at the README's "When it breaks" section). Do not continue.

## Step 2 — Back up settings.json

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak-$(date +%Y%m%d-%H%M%S)
```

If `~/.claude/settings.json` does not exist, tell the user to create it containing `{}` and
re-run setup; do not create it yourself. Remember the backup filename for Step 8.

## Step 3 — Install the status line

Read the current value:

```bash
jq '.statusLine' ~/.claude/settings.json
```

- If it is `null`, or its `command` already contains `claude-extra-usage-limiter`, install
  (or refresh) it without asking.
- Otherwise a different status line is configured. Show it to the user and use
  `AskUserQuestion` with two options: **Replace it with the usage gauge (Recommended)** and
  **Keep my current status line**. If they keep theirs, skip to Step 4 and note in Step 8 that
  the gauge was not installed.

Install by merging the shipped fragment (this preserves every other key in the file; if `jq`
fails the `mv` does not run, so the original is never replaced by a broken file):

```bash
jq --slurpfile sl "${CLAUDE_PLUGIN_ROOT}/references/statusline.json" '.statusLine = $sl[0]' ~/.claude/settings.json > ~/.claude/settings.json.tmp && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
```

## Step 4 — Seed the pointer file

The status line finds the plugin through `~/.claude/.claude-extra-usage-limiter/plugin-root`.
The SessionStart hook rewrites it every session (so upgrades self-heal), but seed it now so the
gauge appears immediately:

```bash
mkdir -p ~/.claude/.claude-extra-usage-limiter
printf '%s' "${CLAUDE_PLUGIN_ROOT}" > ~/.claude/.claude-extra-usage-limiter/plugin-root
```

## Step 5 — Remove hand-wired copies of the hooks

Earlier versions of this guard were installed by hand as `usage_tripwire.py` hook entries. If
both those and the plugin's hooks run, every banner appears twice. List them (tolerant of any
hook shape):

```bash
jq '[.hooks // {} | to_entries[] | .key as $ev | (.value | if type == "array" then .[] else empty end) | (.hooks // [] | .[]?) | select((.command // "") | test("usage_tripwire")) | $ev] | unique' ~/.claude/settings.json
```

If the result is `[]`, say so and continue. Otherwise show the events found and use
`AskUserQuestion`: **Remove the old hand-wired hooks (Recommended)** / **Leave them; I will
clean up myself**. On yes:

```bash
jq 'if (.hooks | type) != "object" then . else .hooks |= with_entries(.value |= (if type == "array" then map(if (.hooks | type) == "array" then .hooks |= map(select(((.command // "") | test("usage_tripwire")) | not)) else . end | select((.hooks // [1]) | length > 0)) else . end) | select((.value | type) != "array" or (.value | length) > 0)) end' ~/.claude/settings.json > ~/.claude/settings.json.tmp && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
```

Then re-run the listing command and confirm it prints `[]`. Do not delete
`~/.claude/scripts/usage_tripwire.py` or any other file; the user can remove those later.

## Step 6 — Default config file

```bash
test -f ~/.claude/claude-extra-usage-limiter.json || printf '{\n  "warn_pct": 85,\n  "block_pct": 97,\n  "refresh_after_min": 5,\n  "stale_loud_min": 20,\n  "warn_throttle_min": 3\n}\n' > ~/.claude/claude-extra-usage-limiter.json
```

Tell the user this file is where thresholds live and that changes apply on the next hook run
(no restart).

## Step 7 — Offer the CLAUDE.md policy text

Check for the marker:

```bash
grep -q claude-extra-usage-limiter:begin ~/.claude/CLAUDE.md 2>/dev/null && echo present || echo absent
```

If absent, explain that the hooks already inject a one-line policy each turn, but a standing
section in `~/.claude/CLAUDE.md` makes the wind-down behavior explicit for every session, and
use `AskUserQuestion`: **Append the policy section to ~/.claude/CLAUDE.md (Recommended)** /
**Skip**. On yes:

```bash
cat "${CLAUDE_PLUGIN_ROOT}/references/claude-md-snippet.md" >> ~/.claude/CLAUDE.md
```

## Step 8 — Report

Print, in plain language: the backup filename and the rollback command
(`cp <backup> ~/.claude/settings.json`), whether the status line was installed, whether old
hooks were removed, the config file path, and whether CLAUDE.md was updated. Finish with a
one-line reading from `--mode dump` (session %, week %, credits state). Claude Code reloads
settings.json on its own; no restart is needed.

Windows note: the status line command uses POSIX shell syntax and runs under Git Bash when
present. On a Windows machine without Git Bash, install it or skip Step 3; the hooks themselves
still work as long as `python3` is on the PATH.
