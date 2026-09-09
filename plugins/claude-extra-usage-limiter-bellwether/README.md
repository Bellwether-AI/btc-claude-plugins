# claude-extra-usage-limiter-bellwether

A local guard that stops Claude Code **before** your plan usage spills into pay-as-you-go
**extra-usage credits**.

On a Claude subscription, extra-usage credits can be switched on at the account level. On a
Teams plan they are an organization setting a member cannot turn off. When a usage window hits
100%, Claude Code simply keeps going on credits: no pause, no prompt. This plugin is the local
substitute for the off switch you may not have.

It watches the 5-hour session window and the 7-day weekly window and acts on the worse of the two:

| Usage of worst window | What happens |
|---|---|
| under 85% | silent; status line green |
| 85%–96% (**warn**) | status line yellow; Claude is told to wind down, commit, and avoid subagents/loops |
| 97%+ (**block**) | status line red; the **PreToolUse hook denies tool calls**, so work physically stops |

**Checkpoint escape hatch.** Even in the block state, a plain `git add` / `git commit` /
`git stash` command, a write to a file inside a `memory/` or `scratchpad/` directory or named
`MEMORY.md`, and the plugin's own `--mode dump` probe are not denied, so a final checkpoint is
always possible. "Plain" means no `&&`, `;`, `|`, backticks, or `$(...)`: a chained command is
not a checkpoint. Checkpoints are not force-approved either; your normal permission rules
still apply to them.

**Fail-open by design.** A tool call is denied only on a *known* reading: a finite number in
0–100 at or above the block threshold. Missing data, a stale cache, a leaked timestamp or
other garbage in the usage field, a malformed file, or a crash inside the hook all *allow* the
action and say so loudly. It never bricks a session.

## Install

```
/plugin marketplace add Bellwether-AI/btc-claude-plugins
/plugin install claude-extra-usage-limiter-bellwether@btc-claude-plugins
/claude-extra-usage-limiter-bellwether:setup
```

The hooks are active as soon as the plugin is enabled. `setup` does the two things a plugin
cannot do on its own: installs the status line into `~/.claude/settings.json` (after backing it
up) and, with your consent, removes any hand-wired copies of the same hooks so banners do not
appear twice. It also writes a default config file and offers to append a short policy section
to your `~/.claude/CLAUDE.md`.

Requirements: `python3` (standard library only), `jq` (setup only), Claude Code signed in with a
claude.ai subscription. API-key sessions have no plan windows; the plugin does nothing useful
there and its self-check says so.

## What you see

**Status line** (refreshes every 30 s):

```
Fable 5.1 (main) ⛽ S:14%⟲1:20pm  W:51%  💳$4.71/$150
```

`S` is the session window with its reset time, `W` the weekly window, `💳` extra-usage credits
used this month (red when credits are enabled). `⚠stale 25m` appears when the reading is old.

**Each prompt** gets one line of context:

```
[extra-usage-limiter] Plan usage: session 14% (resets 1:20pm), week 51%, extra-usage credits
ENABLED ($4.71/$150 used), data 1m old. Never spend extra-usage credits without the user's
explicit per-instance approval.
```

**Session start** prints `[extra-usage-limiter] Active (warn 85%, hard-block 97%)` or a loud
self-check failure naming the missing field.

## Skills

| Skill | Use it for |
|---|---|
| `/claude-extra-usage-limiter-bellwether:setup` | Install or repair the status line, remove old hand-wired hooks, write the default config |
| `/claude-extra-usage-limiter-bellwether:status` | Plain-language reading of both windows, credits, guard band, and troubleshooting pointers |

## Configuration

`~/.claude/claude-extra-usage-limiter.json` (created by `setup`; every key optional):

| Key | Default | Meaning |
|---|---|---|
| `warn_pct` | 85 | wind-down warning at/above this % of a plan window |
| `block_pct` | 97 | hard-deny tool calls at/above this % |
| `refresh_after_min` | 5 | refresh the usage cache when older than this (active work only) |
| `stale_loud_min` | 20 | announce loudly when the reading is older than this |
| `warn_throttle_min` | 3 | minimum gap between repeated warn banners |

Invalid values are logged and ignored. `warn_pct` must be below `block_pct` or both revert to
defaults. Changes apply on the next hook run; no restart.

## How it gets the data (and why that is fragile)

There is **no supported API** for plan usage in a hook or the CLI. The plugin reads the
*undocumented* cache Claude Code keeps at:

```
~/.claude.json -> cachedUsageUtilization.utilization
                    .five_hour   { utilization, resets_at }
                    .seven_day   { utilization, resets_at }
                    .extra_usage { is_enabled, used_credits, monthly_limit, spend_limit_reached }
                  cachedUsageUtilization.fetchedAtMs
```

The status line also merges the documented live `rate_limits` object from its stdin JSON when
present. Every percentage, from the cache or from stdin, is accepted only if it is a finite
number in 0–100. A known Claude Code bug has leaked an epoch timestamp into `used_percentage`;
such a value is treated as unknown, which makes the guard fail open rather than deny everything.

That cache goes stale (observed: 4% cached while live usage was 42%, with no refresh during ten
minutes of heavy work). So the plugin refreshes it by spawning a detached `claude -p /usage`, at
most once every `refresh_after_min` minutes, and only while you are actively working. Hooks
only fire on activity, so an idle machine costs nothing. Recursion is prevented by the
`CLAUDE_EXTRA_USAGE_LIMITER_REFRESH=1` environment variable, which makes every hook in the
spawned child a no-op.

## Status line mechanics

Plugins cannot set `statusLine`, and the plugin's install path changes with every version. So
the SessionStart hook writes the current plugin root to
`~/.claude/.claude-extra-usage-limiter/plugin-root`, and the status line command `setup`
installs reads that pointer. Upgrades self-heal at the next session start; if the pointer is
ever missing, the status line says `run /claude-extra-usage-limiter-bellwether:setup`.

## When it breaks (it will)

The data source is unsupported and can change in any Claude Code release. If the percentages
disappear or turn into something outside 0–100, **session start prints a loud self-check
failure** and the status line shows `⛽ usage: unavailable`. If only the timestamp field
disappears, the reading is reported as stale instead. In both cases hooks allow everything and
say the guard is blind until the plugin is fixed.

```bash
python3 <plugin-root>/scripts/usage_limiter.py --mode dump    # what parsed, what didn't
tail ~/.claude/.claude-extra-usage-limiter/limiter.log           # refresh + crash log
cat  ~/.claude/.claude-extra-usage-limiter/state.json            # last reading
jq '.cachedUsageUtilization.utilization | keys' ~/.claude.json   # has the shape moved?
```

`<plugin-root>` is the content of the pointer file above. The fix is in `read_usage()`.

## Limitations

- This stops **Claude Code's tool calls**, which is where nearly all token burn happens. It
  cannot stop billing at the account level. On a Teams plan the only hard financial control is
  an **individual monthly spend limit set by an org Owner** (Admin settings › Usage).
- Plugin hooks run in addition to any hooks in your own `settings.json`. If you previously
  installed the same guard by hand, let `setup` remove those entries or you will see every banner
  twice.
- The gate hook adds roughly 30–50 ms to every tool call (one local JSON read, no network).
- **Windows.** Hooks run wherever `python3` is on the PATH. The status line command uses POSIX
  shell syntax (`$(...)`, `||`), which Claude Code runs through Git Bash when installed and
  PowerShell otherwise; without Git Bash the gauge will not render. The hooks still work.
- `refresh_after_min`, `stale_loud_min`, and `warn_throttle_min` have a floor of 1 minute so a
  misconfiguration cannot spawn a refresh on every tool call.

## Uninstall

```
/plugin uninstall claude-extra-usage-limiter-bellwether@btc-claude-plugins
```

Then remove the `statusLine` key from `~/.claude/settings.json` (or restore the backup `setup`
made), and delete `~/.claude/.claude-extra-usage-limiter/` and
`~/.claude/claude-extra-usage-limiter.json` if you like.

## Development

```bash
cd plugins/claude-extra-usage-limiter-bellwether
uv run --no-project --with pytest pytest
uv run --no-project --with ruff ruff check .
uv run --no-project --with black black --check .
```

Tests point every path at a temp dir through `CEUL_CLAUDE_JSON`, `CEUL_STATE_DIR`, and
`CEUL_CONFIG`; nothing touches your real `~/.claude`.
