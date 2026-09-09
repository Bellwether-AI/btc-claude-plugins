# claude-extra-usage-limiter-bellwether — Design

Date: 2026-09-09
Status: approved (Matt Lax, in-session)
Source: `~/.claude/scripts/usage_tripwire.py` + `~/.claude/settings.json` wiring, built 2026-09-04

## Purpose

Package the existing usage-tripwire hook system as a Claude Code plugin in the
`btc-claude-plugins` marketplace so any Bellwether user (or anyone else) can install it.
The plugin watches Claude plan usage (5-hour session window and 7-day window), tells Claude
to wind down when a window nears its limit, and hard-denies tool calls before usage spills
into pay-as-you-go extra-usage credits.

Non-goals: changing thresholds or gating semantics; controlling billing at the account
level (impossible from a client); supporting API-key sessions (no plan windows exist).

## Constraints

- Plugins can ship hooks but **cannot set `statusLine`**; that is a user setting.
- Plugin install path is versioned: `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`.
  Anything outside the hook system (status line) needs a version-independent path.
- The data source is the undocumented `cachedUsageUtilization` block in `~/.claude.json`.
  It may change in any Claude Code release. Detection must fail loudly, gating must fail open.
- Repo pushes to GitHub, so Python is linted (ruff + black) and unit-tested (pytest).
- Existing plugins and Matt's live installation must not be disturbed by this work.

## Plugin layout

```
plugins/claude-extra-usage-limiter-bellwether/
  .claude-plugin/plugin.json      name, description, version 1.0.0, author
  hooks/hooks.json                PreToolUse "*" gate; UserPromptSubmit context; SessionStart selfcheck
  scripts/usage_limiter.py        engine (python3 stdlib only, executable)
  scripts/tests/                  pytest suite + fixtures
  skills/setup/SKILL.md           /claude-extra-usage-limiter-bellwether:setup
  skills/status/SKILL.md          /claude-extra-usage-limiter-bellwether:status
  references/claude-md-snippet.md policy text users may paste into ~/.claude/CLAUDE.md
  pyproject.toml                  ruff/black/pytest config (mirrors co-dwerker)
  README.md
```

## Engine: `scripts/usage_limiter.py`

Same behavior as `usage_tripwire.py`, generalized:

| Aspect | Before | After |
|---|---|---|
| User name in messages | "Matt" | "the user" |
| Thresholds/intervals | constants | constants as defaults, overridable by `~/.claude/claude-extra-usage-limiter.json` |
| State dir | `~/.claude/.usage-tripwire/` | `~/.claude/.claude-extra-usage-limiter/` |
| Paths | hardcoded | overridable via env vars `CEUL_CLAUDE_JSON`, `CEUL_STATE_DIR`, `CEUL_CONFIG` (tests) |
| Recursion env var | `CLAUDE_USAGE_TRIPWIRE_REFRESH` | `CLAUDE_EXTRA_USAGE_LIMITER_REFRESH` |
| Plugin root pointer | none | SessionStart writes `$CLAUDE_PLUGIN_ROOT` to `<state>/plugin-root` |

Config file keys (all optional): `warn_pct` (85), `block_pct` (97), `refresh_after_min` (5),
`stale_loud_min` (20), `warn_throttle_min` (3). Invalid values fall back to defaults and are
logged; a malformed file never breaks a hook.

Modes: `statusline`, `gate`, `context`, `selfcheck`, `dump` — unchanged semantics:
- **gate**: unknown/stale → allow + throttled "guard is blind" message; ≥ block → deny unless
  checkpoint action (`git add|commit|stash`, writes under `/memory/`, `/scratchpad`, `MEMORY.md`);
  ≥ warn → allow + wind-down `additionalContext`; else silent allow.
- **context**: one-line usage sentence + threshold advice + "never spend credits without the
  user's explicit per-instance approval".
- **selfcheck**: loud failure naming the missing field; otherwise "Active" note. Also writes
  the plugin-root pointer file.
- **statusline**: model, branch, `⛽ S:<pct>⟲<reset>  W:<pct>  💳<credits>`, colored by worst
  window; merges live `rate_limits` from stdin when present and sane (0–100).
- **refresh**: detached, throttled `claude -p /usage` when cache age > `refresh_after_min`;
  child hooks no-op via the recursion env var.

Every mode is wrapped so a crash logs and emits a warning instead of failing the hook.

## hooks/hooks.json

```json
{
  "hooks": {
    "PreToolUse":       [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/scripts/usage_limiter.py --mode gate", "timeout": 10}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/scripts/usage_limiter.py --mode context", "timeout": 10}]}],
    "SessionStart":     [{"hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/scripts/usage_limiter.py --mode selfcheck", "timeout": 15}]}]
  }
}
```

## Status line (pointer-file mechanism)

`setup` writes to `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "python3 \"$(cat ~/.claude/.claude-extra-usage-limiter/plugin-root 2>/dev/null)/scripts/usage_limiter.py\" --mode statusline 2>/dev/null || printf '⛽ usage: run /claude-extra-usage-limiter-bellwether:setup'",
  "refreshInterval": 30
}
```

The SessionStart hook refreshes the pointer every session, so plugin upgrades self-heal;
older cache versions stay on disk so there is no gap between upgrade and next session start.

## Skills

**setup** (`disable-model-invocation: true`; user-invoked only):
1. Run `--mode dump`; if not `ok`, stop and explain (wrong plan type / format change).
2. Back up `~/.claude/settings.json` to `settings.json.bak-<timestamp>`.
3. Install the `statusLine` entry above (jq merge; preserves every other key). If a different
   statusLine exists, show it and ask before replacing.
4. Detect hook entries in settings.json whose command contains `usage_tripwire.py`; offer to
   remove them so hooks do not fire twice. Never touch other hooks or `permissions`.
5. Write `~/.claude/claude-extra-usage-limiter.json` with defaults if absent.
6. Offer to append `references/claude-md-snippet.md` to `~/.claude/CLAUDE.md` (skip if a
   marker line is already present).
7. Print what changed and how to roll back (restore the backup).

**status**: runs `--mode dump`, prints the reading in plain language, and points to the log
and state files for troubleshooting.

## Tests (`scripts/tests/`)

Fixtures: a fake `~/.claude.json` with a valid cache, a cache missing `utilization`, and a
`rate_limits` stdin payload with an epoch leak. Tests set the `CEUL_*` env vars to a tmp dir
and call the module functions directly (import via path). Cover:
- `read_usage`: valid parse, missing block, missing utilization, staleness, worst-window choice,
  live stdin merge, epoch-leak rejection.
- `load_config`: defaults, override, malformed file.
- `is_checkpoint_action`: git add/commit/stash, memory/scratchpad writes, negatives.
- `mode_gate` decisions: healthy → `{}`; warn → additionalContext; block → deny; block +
  checkpoint → allow; stale → fail-open with message.
- `mode_selfcheck`: writes pointer file; loud failure when broken.
- `maybe_refresh`: no spawn when fresh, when recursion env set, or when marker recent.
`subprocess.Popen` is replaced with a recording stub via monkeypatch (pytest built-in).

## Repo integration

- `.claude-plugin/marketplace.json`: add entry (version 1.0.0).
- `.github/workflows/sync-versions.yml`: add plugin name to the loop.
- Root `README.md`: plugin table row. Root `CHANGELOG.md` / `RELEASE_NOTES.md`: new sections.
- Work on branch `feature/claude-extra-usage-limiter` (worktree from origin/main). PR to main.

## Matt's migration (separate, explicit step after the PR merges)

Install the plugin from the marketplace, run `setup`, confirm the status line and hooks fire,
then remove the three `usage_tripwire.py` hook entries from `~/.claude/settings.json`. Keep
`~/.claude/scripts/usage_tripwire.py` on disk until satisfied. Ask before each destructive step.

## Risks

- Data source is unsupported; the SessionStart self-check is the tripwire for breakage.
- Plugin hooks and hand-wired hooks both firing would duplicate banners (mitigated by setup step 4).
- `claude -p /usage` refresh depends on the `claude` binary being on PATH in the hook env.
