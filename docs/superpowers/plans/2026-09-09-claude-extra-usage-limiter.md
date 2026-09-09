# claude-extra-usage-limiter-bellwether Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `~/.claude/scripts/usage_tripwire.py` as an installable Claude Code plugin in the btc-claude-plugins marketplace, with a setup skill for the status line, a test suite, and docs.

**Architecture:** One stdlib-only Python engine (`scripts/usage_limiter.py`) driven by three plugin hooks (`hooks/hooks.json`) and by a user-installed `statusLine` that finds the engine through a pointer file the SessionStart hook keeps current. Two skills (`setup`, `status`) wrap the user-facing operations. Behavior is identical to the existing script; only names, paths, and configurability change.

**Tech Stack:** Python 3.9+ stdlib, pytest (via `uv run --with pytest`), ruff, black, jq (setup skill), Claude Code plugin hooks.

**Spec:** `docs/superpowers/specs/2026-09-09-claude-extra-usage-limiter-design.md`

## Global Constraints

- Plugin directory: `plugins/claude-extra-usage-limiter-bellwether/`; plugin name exactly `claude-extra-usage-limiter-bellwether`; version `1.0.0`.
- Python: stdlib only in the engine; line length 100; ruff select `E,F,W,I,B,UP`, ignore `UP007,UP045`; target py39. Run tools with `uv run --no-project --with pytest --with ruff --with black <tool>` from the plugin dir.
- Every hook mode FAILS OPEN: never exit non-zero, never emit a `deny` without a known reading ≥ block threshold.
- Defaults: warn 85, block 97, refresh 5 min, stale-loud 20 min, warn-throttle 3 min.
- Messages say "the user", never a personal name.
- Env overrides: `CEUL_CLAUDE_JSON`, `CEUL_STATE_DIR`, `CEUL_CONFIG`. Recursion guard env: `CLAUDE_EXTRA_USAGE_LIMITER_REFRESH=1`.
- Do not modify any other plugin. Do not modify `~/.claude/settings.json` during this plan (migration is a separate, later step).
- Commit after every task with the `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` trailer. Run git from the worktree root `/Users/mattlax/nonedrive/projects/co-dworker/.claude/worktrees/claude-extra-usage-limiter`.

---

### Task 1: Scaffold plugin and port the engine verbatim

**Files:**
- Create: `plugins/claude-extra-usage-limiter-bellwether/.claude-plugin/plugin.json`
- Create: `plugins/claude-extra-usage-limiter-bellwether/hooks/hooks.json`
- Create: `plugins/claude-extra-usage-limiter-bellwether/pyproject.toml`
- Create: `plugins/claude-extra-usage-limiter-bellwether/scripts/usage_limiter.py` (copy of `~/.claude/scripts/usage_tripwire.py`)
- Create: `plugins/claude-extra-usage-limiter-bellwether/scripts/tests/__init__.py` (empty)

**Interfaces:**
- Produces: module `usage_limiter` with functions `read_usage(stdin_json)`, `maybe_refresh(reading)`, `is_checkpoint_action(stdin_json)`, `mode_gate/context/selfcheck/statusline/dump(stdin_json)`, `main()`.

- [ ] **Step 1: Create plugin.json**

```json
{
  "name": "claude-extra-usage-limiter-bellwether",
  "version": "1.0.0",
  "description": "Guards a Claude subscription against pay-as-you-go extra-usage credits. Watches the 5-hour and 7-day plan windows, tells Claude to wind down and checkpoint at 85%, and hard-denies tool calls at 97% (git commit and memory writes stay allowed). Status line shows live usage. Fails open but loud if Claude Code's usage cache changes shape.",
  "author": { "name": "Bellwether AI" }
}
```

- [ ] **Step 2: Create hooks/hooks.json**

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "*", "hooks": [ { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/scripts/usage_limiter.py --mode gate", "timeout": 10 } ] }
    ],
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/scripts/usage_limiter.py --mode context", "timeout": 10 } ] }
    ],
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/scripts/usage_limiter.py --mode selfcheck", "timeout": 15 } ] }
    ]
  }
}
```

- [ ] **Step 3: Create pyproject.toml** (copy of `plugins/co-dwerker/pyproject.toml`, unchanged content).

- [ ] **Step 4: Copy the engine**

```bash
cp ~/.claude/scripts/usage_tripwire.py plugins/claude-extra-usage-limiter-bellwether/scripts/usage_limiter.py
chmod +x plugins/claude-extra-usage-limiter-bellwether/scripts/usage_limiter.py
touch plugins/claude-extra-usage-limiter-bellwether/scripts/tests/__init__.py
```

- [ ] **Step 5: Verify it runs and both JSON files parse**

```bash
python3 -c "import json;json.load(open('plugins/claude-extra-usage-limiter-bellwether/.claude-plugin/plugin.json'));json.load(open('plugins/claude-extra-usage-limiter-bellwether/hooks/hooks.json'));print('json ok')"
python3 plugins/claude-extra-usage-limiter-bellwether/scripts/usage_limiter.py --mode dump | head -3
```
Expected: `json ok` and a JSON reading with `"ok": true`.

- [ ] **Step 6: Commit** — `feat(extra-usage-limiter): scaffold plugin and port usage_tripwire.py verbatim`

---

### Task 2: Generalize the engine (names, paths, env overrides, config file)

**Files:**
- Modify: `plugins/claude-extra-usage-limiter-bellwether/scripts/usage_limiter.py`
- Create: `plugins/claude-extra-usage-limiter-bellwether/scripts/tests/conftest.py`
- Create: `plugins/claude-extra-usage-limiter-bellwether/scripts/tests/test_config_and_paths.py`

**Interfaces:**
- Produces: `load_config() -> dict` with keys `warn_pct, block_pct, refresh_after_min, stale_loud_min, warn_throttle_min` (ints/floats); module-level `CFG = load_config()` read by all modes; `PATHS` resolved from env at import via `_paths()`; `RECURSION_ENV = "CLAUDE_EXTRA_USAGE_LIMITER_REFRESH"`; `PLUGIN_ROOT_FILE = <state_dir>/plugin-root`.

- [ ] **Step 1: Write conftest.py**

```python
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "usage_limiter.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("usage_limiter", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["usage_limiter"] = mod
    spec.loader.exec_module(mod)
    return mod


def make_cache(session=10, week=20, age_min=1.0, credits=True):
    """A minimal ~/.claude.json body shaped like Claude Code's cachedUsageUtilization."""
    return {
        "cachedUsageUtilization": {
            "fetchedAtMs": int((time.time() - age_min * 60) * 1000),
            "utilization": {
                "five_hour": {"utilization": session, "resets_at": "2026-09-09T18:20:00Z"},
                "seven_day": {"utilization": week, "resets_at": "2026-09-12T12:00:00Z"},
                "extra_usage": {
                    "is_enabled": credits, "used_credits": 471, "monthly_limit": 15000,
                    "currency": "USD", "decimal_places": 2, "spend_limit_reached": False,
                },
            },
        }
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Point every path the engine touches at tmp_path and return a loader."""
    claude_json = tmp_path / "claude.json"
    state = tmp_path / "state"
    config = tmp_path / "config.json"
    monkeypatch.setenv("CEUL_CLAUDE_JSON", str(claude_json))
    monkeypatch.setenv("CEUL_STATE_DIR", str(state))
    monkeypatch.setenv("CEUL_CONFIG", str(config))
    monkeypatch.delenv("CLAUDE_EXTRA_USAGE_LIMITER_REFRESH", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

    class Env:
        def write_cache(self, doc):
            claude_json.write_text(json.dumps(doc))

        def write_config(self, text):
            config.write_text(text)

        def load(self):
            return _load_module()

    e = Env()
    e.claude_json, e.state, e.config = claude_json, state, config
    return e
```

- [ ] **Step 2: Write failing tests for config + paths + parse**

```python
import json


def test_defaults_when_no_config(env):
    m = env.load()
    assert m.CFG["warn_pct"] == 85 and m.CFG["block_pct"] == 97
    assert m.CFG["refresh_after_min"] == 5 and m.CFG["stale_loud_min"] == 20
    assert m.CFG["warn_throttle_min"] == 3


def test_config_overrides(env):
    env.write_config(json.dumps({"warn_pct": 70, "block_pct": 90}))
    m = env.load()
    assert m.CFG["warn_pct"] == 70 and m.CFG["block_pct"] == 90
    assert m.CFG["refresh_after_min"] == 5  # untouched keys keep defaults


def test_malformed_config_falls_back(env):
    env.write_config("{not json")
    m = env.load()
    assert m.CFG["warn_pct"] == 85


def test_non_numeric_or_inverted_config_values_ignored(env):
    env.write_config(json.dumps({"warn_pct": "high", "block_pct": 50}))  # block < warn default
    m = env.load()
    assert m.CFG["warn_pct"] == 85 and m.CFG["block_pct"] == 97


def test_paths_come_from_env(env):
    m = env.load()
    assert m.CLAUDE_JSON == str(env.claude_json)
    assert m.STATE_DIR == str(env.state)
    assert m.PLUGIN_ROOT_FILE == str(env.state / "plugin-root")
    assert m.RECURSION_ENV == "CLAUDE_EXTRA_USAGE_LIMITER_REFRESH"


def test_read_usage_valid(env):
    from conftest import make_cache
    env.write_cache(make_cache(session=14, week=51))
    m = env.load()
    r = m.read_usage(None)
    assert r["ok"] and r["worst_pct"] == 51 and r["session_pct"] == 14
    assert r["credits_enabled"] is True and m.credits_str(r) == "$4.71/$150"
    assert not r["stale"]


def test_read_usage_missing_block(env):
    env.write_cache({"other": 1})
    m = env.load()
    r = m.read_usage(None)
    assert not r["ok"] and "cachedUsageUtilization" in r["error"]


def test_read_usage_stale(env):
    from conftest import make_cache
    env.write_cache(make_cache(age_min=45))
    m = env.load()
    assert m.read_usage(None)["stale"] is True


def test_live_stdin_merge_and_epoch_leak_rejected(env):
    from conftest import make_cache
    env.write_cache(make_cache(session=14, week=51))
    m = env.load()
    live = {"rate_limits": {"five_hour": {"used_percentage": 60, "resets_at": 1789000000},
                            "seven_day": {"used_percentage": 1788962159321}}}
    r = m.read_usage(live)
    assert r["session_pct"] == 60 and r["source"] == "stdin+cache"
    assert r["week_pct"] == 51  # leaked epoch rejected, cache value kept


def test_no_personal_name_in_source():
    from conftest import SCRIPT
    text = SCRIPT.read_text()
    assert "Matt" not in text
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd plugins/claude-extra-usage-limiter-bellwether && uv run --no-project --with pytest pytest -q
```
Expected: failures on `CFG`, `PLUGIN_ROOT_FILE`, `RECURSION_ENV`, and the personal-name test.

- [ ] **Step 4: Edit the engine**

Replace the CONFIG block (from `WARN_PCT = 85` through `RECURSION_ENV = ...`) with:

```python
# -----------------------------------------------------------------------------
# CONFIG — defaults; override any key in ~/.claude/claude-extra-usage-limiter.json
# -----------------------------------------------------------------------------
DEFAULTS = {
    "warn_pct": 85,  # wind-down warning at/above this % of a plan window
    "block_pct": 97,  # HARD-DENY tool calls at/above this %
    "refresh_after_min": 5,  # refresh the cache when older than this (active work only)
    "stale_loud_min": 20,  # announce loudly when the reading is older than this
    "warn_throttle_min": 3,  # minimum gap between repeated warn banners
}

HOME = os.path.expanduser("~")
CLAUDE_JSON = os.environ.get("CEUL_CLAUDE_JSON") or os.path.join(HOME, ".claude.json")
STATE_DIR = os.environ.get("CEUL_STATE_DIR") or os.path.join(
    HOME, ".claude", ".claude-extra-usage-limiter"
)
CONFIG_FILE = os.environ.get("CEUL_CONFIG") or os.path.join(
    HOME, ".claude", "claude-extra-usage-limiter.json"
)
REFRESH_MARKER = os.path.join(STATE_DIR, "last-refresh")
WARN_MARKER = os.path.join(STATE_DIR, "last-warn")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
LOG_FILE = os.path.join(STATE_DIR, "limiter.log")
PLUGIN_ROOT_FILE = os.path.join(STATE_DIR, "plugin-root")

# Set in the environment of the spawned `claude -p /usage` refresh so every hook
# in that child session no-ops instead of recursing.
RECURSION_ENV = "CLAUDE_EXTRA_USAGE_LIMITER_REFRESH"
```

Add after `_log` is defined:

```python
def load_config() -> dict:
    """DEFAULTS merged with the user's config file. Never raises; bad values are ignored."""
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE) as fh:
            user = json.load(fh)
    except FileNotFoundError:
        return cfg
    except Exception as e:
        _log(f"config ignored ({CONFIG_FILE}): {e}")
        return cfg
    if not isinstance(user, dict):
        _log(f"config ignored ({CONFIG_FILE}): not an object")
        return cfg
    for key in DEFAULTS:
        val = user.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool) and val >= 0:
            cfg[key] = val
        elif key in user:
            _log(f"config key {key!r} ignored: {val!r}")
    if not cfg["warn_pct"] < cfg["block_pct"]:
        _log("config ignored: warn_pct must be < block_pct; using defaults for both")
        cfg["warn_pct"], cfg["block_pct"] = DEFAULTS["warn_pct"], DEFAULTS["block_pct"]
    return cfg


CFG = load_config()
```

Then replace every use of `WARN_PCT`, `BLOCK_PCT`, `REFRESH_AFTER_MIN`, `STALE_LOUD_MIN`, `WARN_THROTTLE_MIN` with `CFG["warn_pct"]`, `CFG["block_pct"]`, `CFG["refresh_after_min"]`, `CFG["stale_loud_min"]`, `CFG["warn_throttle_min"]`. Replace "Matt" with "the user" in every string (`Tell Matt where things stand` → `Tell the user where things stand`; `Matt's explicit per-instance approval` → `the user's explicit per-instance approval`; `Matt's OK` → `the user's OK`; `confirm with Matt` → `confirm with the user`). Rewrite the module docstring to describe the plugin (no personal name; mention the config file, env overrides, and pointer file). Update the selfcheck failure text to name `scripts/usage_limiter.py` in the plugin and `limiter.log`.

- [ ] **Step 5: Run tests; expect all pass. Run ruff + black.**

```bash
uv run --no-project --with pytest pytest -q
uv run --no-project --with ruff ruff check . && uv run --no-project --with black black --check .
```
Fix anything reported (use `black .` to reformat).

- [ ] **Step 6: Commit** — `feat(extra-usage-limiter): config file, env-overridable paths, neutral wording`

---

### Task 3: Gate, checkpoint, refresh, and selfcheck tests (plus pointer file)

**Files:**
- Modify: `plugins/claude-extra-usage-limiter-bellwether/scripts/usage_limiter.py` (selfcheck writes pointer)
- Create: `plugins/claude-extra-usage-limiter-bellwether/scripts/tests/test_modes.py`

**Interfaces:**
- Consumes: `CFG`, `read_usage`, `mode_*`, `emit` (writes JSON to stdout), `maybe_refresh`.
- Produces: `mode_selfcheck` writes `os.environ["CLAUDE_PLUGIN_ROOT"]` to `PLUGIN_ROOT_FILE` when set.

- [ ] **Step 1: Write failing tests**

```python
import json

from conftest import make_cache


def run_mode(m, capsys, fn, stdin=None):
    fn(stdin)
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


def test_gate_healthy_is_silent_allow(env, capsys):
    env.write_cache(make_cache(session=10, week=20))
    m = env.load()
    assert run_mode(m, capsys, m.mode_gate, {"tool_name": "Bash", "tool_input": {"command": "ls"}}) == {}


def test_gate_warn_adds_context_not_deny(env, capsys):
    env.write_cache(make_cache(session=90, week=20))
    m = env.load()
    out = run_mode(m, capsys, m.mode_gate, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    hs = out["hookSpecificOutput"]
    assert "permissionDecision" not in hs and "Wind down" in hs["additionalContext"]
    assert "the user" in hs["additionalContext"]


def test_gate_block_denies(env, capsys):
    env.write_cache(make_cache(session=98, week=20))
    m = env.load()
    out = run_mode(m, capsys, m.mode_gate, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "credits are ENABLED" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_gate_block_allows_checkpoint(env, capsys):
    env.write_cache(make_cache(session=98, week=20))
    m = env.load()
    out = run_mode(m, capsys, m.mode_gate,
                   {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_gate_stale_fails_open(env, capsys):
    env.write_cache(make_cache(session=99, week=99, age_min=60))
    m = env.load()
    out = run_mode(m, capsys, m.mode_gate, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert "permissionDecision" not in out.get("hookSpecificOutput", {})
    assert "blind" in out["systemMessage"]


def test_gate_missing_cache_fails_open(env, capsys):
    m = env.load()  # no cache file written
    out = run_mode(m, capsys, m.mode_gate, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert "permissionDecision" not in out.get("hookSpecificOutput", {})


def test_gate_noop_in_refresh_child(env, capsys, monkeypatch):
    env.write_cache(make_cache(session=99, week=99))
    monkeypatch.setenv("CLAUDE_EXTRA_USAGE_LIMITER_REFRESH", "1")
    m = env.load()
    assert run_mode(m, capsys, m.mode_gate, {"tool_name": "Bash", "tool_input": {"command": "ls"}}) == {}


def test_is_checkpoint_action(env):
    m = env.load()
    yes = [
        {"tool_name": "Bash", "tool_input": {"command": "git add -A"}},
        {"tool_name": "Bash", "tool_input": {"command": " git stash push -m x"}},
        {"tool_name": "Write", "tool_input": {"file_path": "/x/memory/notes.md"}},
        {"tool_name": "Edit", "tool_input": {"file_path": "/x/scratchpad/a.txt"}},
        {"tool_name": "Write", "tool_input": {"file_path": "/x/MEMORY.md"}},
    ]
    no = [
        {"tool_name": "Bash", "tool_input": {"command": "git push"}},
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf x"}},
        {"tool_name": "Write", "tool_input": {"file_path": "/x/src/app.py"}},
        {"tool_name": "Agent", "tool_input": {}},
    ]
    assert all(m.is_checkpoint_action(a) for a in yes)
    assert not any(m.is_checkpoint_action(a) for a in no)


def test_context_mentions_usage_and_policy(env, capsys):
    env.write_cache(make_cache(session=14, week=51))
    m = env.load()
    out = run_mode(m, capsys, m.mode_context, {})
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "session 14%" in ctx and "week 51%" in ctx and "the user's explicit" in ctx


def test_selfcheck_writes_plugin_root_pointer(env, capsys, monkeypatch):
    env.write_cache(make_cache())
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/plugins/ceul/1.0.0")
    m = env.load()
    out = run_mode(m, capsys, m.mode_selfcheck, {})
    assert "Active" in out["hookSpecificOutput"]["additionalContext"]
    assert (env.state / "plugin-root").read_text() == "/plugins/ceul/1.0.0"


def test_selfcheck_loud_when_broken(env, capsys):
    env.write_cache({"cachedUsageUtilization": {"nope": 1}})
    m = env.load()
    out = run_mode(m, capsys, m.mode_selfcheck, {})
    assert "SELF-CHECK FAILED" in out["systemMessage"]


def test_refresh_spawns_once_then_throttles(env, monkeypatch):
    env.write_cache(make_cache(age_min=10))
    m = env.load()
    calls = []
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(m.shutil, "which", lambda _: "/usr/local/bin/claude")
    r = m.read_usage(None)
    m.maybe_refresh(r)
    m.maybe_refresh(r)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0][1:] == ["-p", "/usage"]
    assert kwargs["env"]["CLAUDE_EXTRA_USAGE_LIMITER_REFRESH"] == "1"
    assert kwargs["start_new_session"] is True


def test_refresh_skipped_when_fresh_or_child(env, monkeypatch):
    env.write_cache(make_cache(age_min=1))
    m = env.load()
    calls = []
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: calls.append(a))
    m.maybe_refresh(m.read_usage(None))
    monkeypatch.setenv("CLAUDE_EXTRA_USAGE_LIMITER_REFRESH", "1")
    env.write_cache(make_cache(age_min=30))
    m.maybe_refresh(m.read_usage(None))
    assert calls == []


def test_statusline_renders(env, capsys):
    env.write_cache(make_cache(session=14, week=51))
    m = env.load()
    m.mode_statusline({"model": {"display_name": "Fable 5.1"}})
    out = capsys.readouterr().out
    assert "S:14%" in out and "W:51%" in out and "Fable 5.1" in out and "$4.71/$150" in out
```

- [ ] **Step 2: Run; expect `test_selfcheck_writes_plugin_root_pointer` to fail (pointer not written).**

- [ ] **Step 3: Add pointer write to `mode_selfcheck`** (before the `read_usage` call):

```python
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(PLUGIN_ROOT_FILE, "w") as fh:
                fh.write(root)
        except Exception as e:
            _log(f"could not write plugin-root pointer: {e}")
```

- [ ] **Step 4: Run tests + ruff + black; all green.**

- [ ] **Step 5: Commit** — `test(extra-usage-limiter): gate, checkpoint, refresh, selfcheck coverage; pointer file`

---

### Task 4: Skills and reference snippet

**Files:**
- Create: `plugins/claude-extra-usage-limiter-bellwether/skills/setup/SKILL.md`
- Create: `plugins/claude-extra-usage-limiter-bellwether/skills/status/SKILL.md`
- Create: `plugins/claude-extra-usage-limiter-bellwether/references/claude-md-snippet.md`

- [ ] **Step 1: Write references/claude-md-snippet.md** — the "Session Usage Limits & Extra-Usage Credits" section from `~/.claude/CLAUDE.md`, with "my"/"me" made generic, bounded by marker lines `<!-- claude-extra-usage-limiter:begin -->` and `<!-- claude-extra-usage-limiter:end -->`.

- [ ] **Step 2: Write skills/setup/SKILL.md** with frontmatter:

```yaml
---
name: setup
description: Use when the user asks to install, configure, or repair the extra-usage limiter status line or hooks — "set up the usage limiter", "install the usage status line", "the usage gauge is missing", or right after installing the plugin.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/usage_limiter.py:*), Bash(jq:*), Bash(cp:*), Bash(cat:*), Read, AskUserQuestion
---
```

Body implements spec steps 1–7 exactly, with the literal `jq` commands:

```bash
# 2. backup
cp ~/.claude/settings.json ~/.claude/settings.json.bak-$(date +%Y%m%d-%H%M%S)
# 3. statusLine (merge, preserve everything else)
jq '.statusLine = {"type":"command","command":"python3 \"$(cat ~/.claude/.claude-extra-usage-limiter/plugin-root 2>/dev/null)/scripts/usage_limiter.py\" --mode statusline 2>/dev/null || printf '\''⛽ usage: run /claude-extra-usage-limiter-bellwether:setup'\''","refreshInterval":30}' ~/.claude/settings.json > ~/.claude/settings.json.tmp && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
# 4. find legacy hand-wired hooks
jq '[.hooks // {} | to_entries[] | .key as $ev | .value[] | .hooks[] | select(.command|test("usage_tripwire.py")) | $ev] | unique' ~/.claude/settings.json
# 4b. remove them (only if the user says yes)
jq '.hooks |= with_entries(.value |= map(.hooks |= map(select((.command|test("usage_tripwire.py"))|not)) | select(.hooks|length>0)) | select(.value|length>0))' ~/.claude/settings.json > ~/.claude/settings.json.tmp && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
# 5. default config
[ -f ~/.claude/claude-extra-usage-limiter.json ] || printf '{\n  "warn_pct": 85,\n  "block_pct": 97,\n  "refresh_after_min": 5,\n  "stale_loud_min": 20,\n  "warn_throttle_min": 3\n}\n' > ~/.claude/claude-extra-usage-limiter.json
# also seed the pointer immediately so the status line works before the next session start
mkdir -p ~/.claude/.claude-extra-usage-limiter && printf '%s' "${CLAUDE_PLUGIN_ROOT}" > ~/.claude/.claude-extra-usage-limiter/plugin-root
```

Step 1 gate: run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/usage_limiter.py --mode dump`; if `"ok": false`, stop and explain (API-key login has no plan windows; otherwise the cache format changed). Step 6 checks `grep -q 'claude-extra-usage-limiter:begin' ~/.claude/CLAUDE.md` before offering to append. Step 7 prints the backup filename and `cp <backup> ~/.claude/settings.json` as the rollback.

- [ ] **Step 3: Write skills/status/SKILL.md**

```yaml
---
name: status
description: Use when the user asks how much of their Claude plan usage is left, whether extra-usage credits are at risk, or whether the usage limiter is working — "usage status", "how close am I to the limit", "is the limiter running".
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/usage_limiter.py:*), Bash(cat ~/.claude/.claude-extra-usage-limiter/*), Bash(tail:*)
---
```

Body: run `--mode dump`; report session %, reset time, week %, credits state, data age, and which threshold band applies; if `ok` is false, print the error and point to `~/.claude/.claude-extra-usage-limiter/limiter.log` and `state.json`; remind that gating only stops tool calls, not billing.

- [ ] **Step 4: Validate frontmatter parses** — `python3 -c "import yaml"` is not guaranteed; instead check each SKILL.md starts with `---` and has `name:`/`description:` lines via grep.

- [ ] **Step 5: Commit** — `feat(extra-usage-limiter): setup and status skills, CLAUDE.md policy snippet`

---

### Task 5: README and repo integration

**Files:**
- Create: `plugins/claude-extra-usage-limiter-bellwether/README.md`
- Modify: `.claude-plugin/marketplace.json` (add entry)
- Modify: `.github/workflows/sync-versions.yml` (`for PLUGIN in flywheel co-dwerker claude-extra-usage-limiter-bellwether; do`)
- Modify: `README.md` (root; add plugin to the list)

- [ ] **Step 1: README.md** sections: What it does (table of bands from the instructions doc), Install (`/plugin marketplace add Bellwether-AI/btc-claude-plugins`, `/plugin install claude-extra-usage-limiter-bellwether@btc-claude-plugins`, then `/claude-extra-usage-limiter-bellwether:setup`), How it gets data (undocumented cache + throttled `claude -p /usage` refresh, recursion guard), Configuration (config file keys), Status line (pointer-file mechanism), Troubleshooting (dump, log, state, jq shape check), Limitations (stops tool calls, not billing; Teams org-owner spend limit; will break on format change and says so), Uninstall.

- [ ] **Step 2: marketplace.json entry**

```json
{
  "name": "claude-extra-usage-limiter-bellwether",
  "source": "./plugins/claude-extra-usage-limiter-bellwether",
  "description": "Guards a Claude subscription against pay-as-you-go extra-usage credits. Watches the 5-hour and 7-day plan windows, tells Claude to wind down at 85%, hard-denies tool calls at 97% (commits and memory writes stay allowed), and shows live usage in the status line. Fails open but loud if Claude Code's usage cache changes shape.",
  "version": "1.0.0"
}
```

- [ ] **Step 3: Validate** — `python3 -c "import json;json.load(open('.claude-plugin/marketplace.json'))"`; confirm every `source` path exists; root README renders the new row.

- [ ] **Step 4: Commit** — `feat(extra-usage-limiter): README, marketplace entry, version-sync workflow, root README`

---

### Task 6: Live verification against the real harness

**Files:** none created (results reported in chat; fix anything found, commit fixes).

- [ ] **Step 1: Hook simulation with the real cache** — from the worktree root, with `CLAUDE_PLUGIN_ROOT` set to the plugin dir and `CEUL_STATE_DIR` set to the scratchpad so nothing touches the live state dir:

```bash
export CLAUDE_PLUGIN_ROOT=$PWD/plugins/claude-extra-usage-limiter-bellwether CEUL_STATE_DIR=$SCRATCHPAD/ceul-state
echo '{}' | python3 $CLAUDE_PLUGIN_ROOT/scripts/usage_limiter.py --mode selfcheck; echo; cat $CEUL_STATE_DIR/plugin-root; echo
echo '{}' | python3 $CLAUDE_PLUGIN_ROOT/scripts/usage_limiter.py --mode context; echo
echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | python3 $CLAUDE_PLUGIN_ROOT/scripts/usage_limiter.py --mode gate; echo
echo '{"model":{"display_name":"Fable 5.1"},"cwd":"'$PWD'"}' | python3 $CLAUDE_PLUGIN_ROOT/scripts/usage_limiter.py --mode statusline; echo
```
Expected: selfcheck "Active", pointer equals the plugin dir, context sentence with live numbers, gate `{}`, status line with `S:` `W:` and branch name.

- [ ] **Step 2: Exercise the hooks.json command string exactly as Claude Code will** — `bash -c "$(jq -r '.hooks.PreToolUse[0].hooks[0].command' plugins/claude-extra-usage-limiter-bellwether/hooks/hooks.json)" <<< '{"tool_name":"Bash","tool_input":{"command":"ls"}}'` with `CLAUDE_PLUGIN_ROOT` exported. Expected `{}`.

- [ ] **Step 3: Exercise the statusLine command string from the setup skill** with a temporary pointer file (`CEUL_STATE_DIR` cannot be used here because the command hardcodes the real pointer path; instead run the command with `HOME` pointed at a scratch dir containing `.claude/.claude-extra-usage-limiter/plugin-root` and a copied `.claude.json`). Expected: a rendered gauge. Then remove the pointer and confirm the fallback text prints.

- [ ] **Step 4: Plugin validation** — run `claude plugin validate plugins/claude-extra-usage-limiter-bellwether` if that subcommand exists (`claude plugin --help`); otherwise skip and note it.

- [ ] **Step 5: Confirm the live install is untouched** — `python3 ~/.claude/scripts/usage_tripwire.py --mode dump | head -2` still works and `~/.claude/settings.json` is unchanged (`git -C ~/.claude status --short settings.json` empty).

- [ ] **Step 6: Commit any fixes** — `fix(extra-usage-limiter): live-verification fixes` (skip if none).

---

### Task 7: Changelog, release notes, review, PR

**Files:**
- Modify: `CHANGELOG.md`, `RELEASE_NOTES.md` (root)

- [ ] **Step 1: Self code review** — reread the diff (`git diff origin/main --stat` and the engine file) against the spec; check fail-open paths, no personal names, no stray references to `usage_tripwire`, executable bit on the script.
- [ ] **Step 2: Full lint + tests one last time** from the plugin dir (ruff, black --check, pytest).
- [ ] **Step 3: CHANGELOG.md** — new top section `## [claude-extra-usage-limiter-bellwether v1.0.0] - 2026-09-09` with `### Added` line items (one per file/behavior, ≤ 2 sentences each). **RELEASE_NOTES.md** — new top section in plain language: what it does, how to install, the Teams caveat, known limitation (unsupported data source).
- [ ] **Step 4: Commit** — `docs: CHANGELOG and RELEASE_NOTES for claude-extra-usage-limiter-bellwether v1.0.0`
- [ ] **Step 5: Push and open PR** to `main` with a body summarizing the plugin, the verification performed, and the follow-up migration step. End the body with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
