#!/usr/bin/env python3
"""
usage_limiter.py — plan-usage guard for Claude Code (claude-extra-usage-limiter-bellwether).

WHY THIS EXISTS
---------------
On a Claude subscription, "extra-usage credits" (pay-as-you-go overage past the
plan's included 5-hour and 7-day usage) can be enabled at the account or
organization level. On a Teams plan a member cannot turn them off. Once a usage
window hits 100%, Claude Code keeps working on credits with no pause. This script
is a *local* guard that watches plan usage and stops work BEFORE it spills into
credits, so credits are only ever spent when the user explicitly opts in.

There is NO officially-supported way to read plan usage from a hook or the CLI.
The community-standard workaround is to read the undocumented cache field
`cachedUsageUtilization` that Claude Code persists in ~/.claude.json. This script
does that. It is UNSUPPORTED and MAY BREAK on a Claude Code update, which is why
the SessionStart self-check fails LOUD the moment the shape changes.

The cache goes stale (observed: 4% cached while live usage was 42%, with no
refresh during ~10 minutes of heavy work). So this script actively, and with a
throttle, refreshes the cache by spawning a detached `claude -p /usage`, guarded
against recursion by the RECURSION_ENV variable.

MODES (pick with --mode)
------------------------
  statusline  -> one compact status-bar line (reads stdin JSON, merges live rate_limits)
  gate        -> PreToolUse: HARD-DENY tool calls at/above block_pct, warn at warn_pct
  context     -> UserPromptSubmit: inject a one-line usage status into the turn
  selfcheck   -> SessionStart: validate the cache shape, fail LOUD if broken;
                 also record $CLAUDE_PLUGIN_ROOT in the plugin-root pointer file
  dump        -> print the parsed reading as JSON (debugging / "know when it breaks")

All hook modes FAIL OPEN (never brick the session): if usage data is missing or
stale, they allow the action but say so loudly. Only a KNOWN reading at/above the
block threshold denies a tool call.

CONFIG
------
Defaults live in DEFAULTS below. Any key may be overridden in
~/.claude/claude-extra-usage-limiter.json. Paths are overridable through the
CEUL_CLAUDE_JSON, CEUL_STATE_DIR and CEUL_CONFIG environment variables (used by
the test suite; not needed in normal use).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

# -----------------------------------------------------------------------------
# CONFIG — defaults; override any key in ~/.claude/claude-extra-usage-limiter.json
# -----------------------------------------------------------------------------
DEFAULTS = {
    "warn_pct": 85,  # wind-down warning at/above this % of a plan window
    "block_pct": 97,  # HARD-DENY tool calls at/above this % (protects against runaway)
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
BLIND_MARKER = os.path.join(STATE_DIR, "last-blind")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
LOG_FILE = os.path.join(STATE_DIR, "limiter.log")
PLUGIN_ROOT_FILE = os.path.join(STATE_DIR, "plugin-root")

# Set in the environment of the spawned `claude -p /usage` refresh so every hook
# in that child session no-ops instead of recursing.
RECURSION_ENV = "CLAUDE_EXTRA_USAGE_LIMITER_REFRESH"

# Shell metacharacters that turn a "git commit ..." into something else entirely.
# A checkpoint command containing any of these is NOT treated as a checkpoint.
SHELL_CHAIN_CHARS = ("&&", "||", ";", "|", "`", "$(", "\n", ">", "<")

# ANSI colors for the status line.
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"


# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------
def _log(msg: str) -> None:
    """Append a debug line. Best-effort; never raises."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOG_FILE, "a") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except Exception:
        pass


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
    # A zero refresh interval would spawn `claude -p /usage` on every hook call.
    for key in ("refresh_after_min", "stale_loud_min", "warn_throttle_min"):
        if cfg[key] < 1:
            _log(f"config key {key!r} below 1 ignored: {cfg[key]!r}")
            cfg[key] = DEFAULTS[key]
    if not cfg["warn_pct"] < cfg["block_pct"]:
        _log("config ignored: warn_pct must be < block_pct; using defaults for both")
        cfg["warn_pct"], cfg["block_pct"] = DEFAULTS["warn_pct"], DEFAULTS["block_pct"]
    return cfg


CFG = load_config()


def _marker_age_min(path: str) -> float:
    """Age of a marker file in minutes, or a large number if it does not exist."""
    try:
        return (time.time() - os.path.getmtime(path)) / 60.0
    except Exception:
        return 1e9


def _touch(path: str) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(path, "w") as fh:
            fh.write(str(time.time()))
    except Exception:
        pass


def _parse_iso(s):
    """Parse an ISO-8601 timestamp (with tz) to an aware datetime, or None."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _fmt_reset(dt) -> str:
    """Human 'resets 7:59pm' style in local time; '' if unknown."""
    if dt is None:
        return ""
    try:
        local = dt.astimezone()
        return local.strftime("%-I:%M%p").lower()
    except Exception:
        return ""


def _pct_color(pct) -> str:
    if pct is None:
        return C_DIM
    if pct >= CFG["block_pct"]:
        return C_RED
    if pct >= CFG["warn_pct"]:
        return C_YELLOW
    return C_GREEN


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v  # nan != nan


def _pct(v):
    """A percentage is only KNOWN if it is a finite number in 0..100; anything else is None.

    Claude Code has leaked epoch timestamps into percentage fields before. Treating such a
    value as a real reading would hard-deny every tool call, so it is rejected here and the
    reading falls through to the loud fail-open path instead.
    """
    return v if (_is_num(v) and 0 <= v <= 100) else None


def _age_str(r: dict) -> str:
    age = r.get("age_min")
    return f"usage data is {age:.0f}m old" if _is_num(age) else "usage timestamp missing"


# -----------------------------------------------------------------------------
# Read + normalize the usage cache.
# -----------------------------------------------------------------------------
def read_usage(stdin_json: dict | None = None) -> dict:
    """
    Return a normalized reading dict. Never raises.

    Keys:
      ok            bool     — cache read + minimally-valid shape
      error         str|None — why not ok
      age_min       float|None — how old the cache reading is
      stale         bool     — age_min > stale_loud_min
      session_pct / session_reset (datetime|None)
      week_pct / week_reset
      worst_pct     max(session, week) used for gating
      credits_enabled / credits_used / credits_limit / credits_ccy / credits_dp
      spend_limit_reached
      source        'stdin+cache' | 'cache' | None
    """
    r = {
        "ok": False,
        "error": None,
        "age_min": None,
        "stale": True,
        "session_pct": None,
        "session_reset": None,
        "week_pct": None,
        "week_reset": None,
        "worst_pct": None,
        "credits_enabled": None,
        "credits_used": None,
        "credits_limit": None,
        "credits_ccy": "USD",
        "credits_dp": 2,
        "spend_limit_reached": None,
        "source": None,
    }

    # --- cache (~/.claude.json) ---
    try:
        with open(CLAUDE_JSON) as fh:
            doc = json.load(fh)
    except Exception as e:
        r["error"] = f"cannot read {CLAUDE_JSON}: {e}"
        return r
    if not isinstance(doc, dict):
        r["error"] = f"{CLAUDE_JSON} is not a JSON object (format changed?)"
        return r

    cu = doc.get("cachedUsageUtilization")
    if not isinstance(cu, dict):
        r["error"] = "cachedUsageUtilization missing (Claude Code format changed?)"
        return r

    util = cu.get("utilization")
    if not isinstance(util, dict):
        r["error"] = "cachedUsageUtilization.utilization missing (format changed?)"
        return r

    fetched_ms = cu.get("fetchedAtMs")
    if _is_num(fetched_ms):
        r["age_min"] = (time.time() * 1000 - fetched_ms) / 60000.0

    fh_win = util.get("five_hour") or {}
    sd_win = util.get("seven_day") or {}
    if isinstance(fh_win, dict):
        r["session_pct"] = _pct(fh_win.get("utilization"))
        r["session_reset"] = _parse_iso(fh_win.get("resets_at"))
    if isinstance(sd_win, dict):
        r["week_pct"] = _pct(sd_win.get("utilization"))
        r["week_reset"] = _parse_iso(sd_win.get("resets_at"))

    ex = util.get("extra_usage") or {}
    if isinstance(ex, dict):
        r["credits_enabled"] = ex.get("is_enabled")
        r["credits_used"] = ex.get("used_credits")
        r["credits_limit"] = ex.get("monthly_limit")
        r["credits_ccy"] = ex.get("currency", "USD")
        r["credits_dp"] = ex.get("decimal_places", 2)
        r["spend_limit_reached"] = ex.get("spend_limit_reached")

    r["source"] = "cache"

    # --- merge live stdin rate_limits (status line only), if valid & sane ---
    # Live data appears only for some plans and only after the first API response.
    # _pct() rejects the known epoch-leak bug (a used_percentage far above 100).
    if isinstance(stdin_json, dict):
        rl = stdin_json.get("rate_limits")
        rl = rl if isinstance(rl, dict) else {}
        fh_live = rl.get("five_hour")
        fh_live = fh_live if isinstance(fh_live, dict) else {}
        sd_live = rl.get("seven_day")
        sd_live = sd_live if isinstance(sd_live, dict) else {}
        up = _pct(fh_live.get("used_percentage"))
        if up is not None:
            r["session_pct"] = up
            ra = fh_live.get("resets_at")
            if _is_num(ra):
                r["session_reset"] = datetime.fromtimestamp(ra, tz=timezone.utc)
            r["age_min"] = 0.0  # live
            r["source"] = "stdin+cache"
        wp = _pct(sd_live.get("used_percentage"))
        if wp is not None:
            r["week_pct"] = wp
            ra = sd_live.get("resets_at")
            if _is_num(ra):
                r["week_reset"] = datetime.fromtimestamp(ra, tz=timezone.utc)

    # worst window drives gating
    cands = [p for p in (r["session_pct"], r["week_pct"]) if _is_num(p)]
    r["worst_pct"] = max(cands) if cands else None

    r["stale"] = (r["age_min"] is None) or (r["age_min"] > CFG["stale_loud_min"])
    r["ok"] = r["worst_pct"] is not None
    if not r["ok"] and r["error"] is None:
        r["error"] = "no session/weekly utilization values in 0..100 found (format changed?)"

    # best-effort shared state file for observability/debugging
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        snap = dict(r)
        snap["session_reset"] = _fmt_reset(r["session_reset"])
        snap["week_reset"] = _fmt_reset(r["week_reset"])
        snap["written_at"] = datetime.now().isoformat(timespec="seconds")
        with open(STATE_FILE, "w") as fh:
            json.dump(snap, fh, indent=2)
    except Exception:
        pass

    return r


def credits_str(r: dict) -> str:
    """'$4.71/$150' style, or '' if unknown."""
    used, lim, dp = r.get("credits_used"), r.get("credits_limit"), r.get("credits_dp")
    if not _is_num(used) or not _is_num(lim):
        return ""
    dp = int(dp) if (_is_num(dp) and 0 <= dp <= 10) else 2
    div = 10**dp
    sign = "$" if (r.get("credits_ccy") == "USD") else ""
    return f"{sign}{used / div:.2f}/{sign}{lim / div:.0f}"


# -----------------------------------------------------------------------------
# Active, throttled, recursion-safe refresh of the cache.
# -----------------------------------------------------------------------------
def maybe_refresh(reading: dict) -> None:
    """Spawn a detached `claude -p /usage` to refresh the cache, if warranted."""
    if os.environ.get(RECURSION_ENV) == "1":
        return  # we ARE the refresh child; do nothing
    age = reading.get("age_min")
    fresh_enough = _is_num(age) and age <= CFG["refresh_after_min"]
    if fresh_enough:
        return
    if _marker_age_min(REFRESH_MARKER) <= CFG["refresh_after_min"]:
        return  # a refresh was already kicked off recently
    _touch(REFRESH_MARKER)  # claim the slot before spawning (avoids thundering herd)

    claude = shutil.which("claude")
    if not claude:
        for cand in ("/opt/homebrew/bin/claude", os.path.join(HOME, ".claude/local/claude")):
            if os.path.exists(cand):
                claude = cand
                break
    if not claude:
        _log("refresh skipped: claude binary not found on PATH")
        return

    env = os.environ.copy()
    env[RECURSION_ENV] = "1"
    try:
        subprocess.Popen(
            [claude, "-p", "/usage"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        _log(f"refresh spawned (age={age})")
    except Exception as e:
        _log(f"refresh spawn failed: {e}")


# -----------------------------------------------------------------------------
# Output helpers for hook JSON.
# -----------------------------------------------------------------------------
def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def status_sentence(r: dict) -> str:
    """One-line plain-text status used inside injected context."""
    parts = []
    if _is_num(r["session_pct"]):
        rs = _fmt_reset(r["session_reset"])
        parts.append(f"session {r['session_pct']:.0f}%" + (f" (resets {rs})" if rs else ""))
    if _is_num(r["week_pct"]):
        parts.append(f"week {r['week_pct']:.0f}%")
    cs = credits_str(r)
    if cs:
        state = "ENABLED" if r.get("credits_enabled") else "off"
        parts.append(f"extra-usage credits {state} ({cs} used)")
    age = r.get("age_min")
    if _is_num(age):
        parts.append(f"data {age:.0f}m old")
    return "Plan usage: " + ", ".join(parts) if parts else "Plan usage: unavailable"


# Checkpoint actions are NOT denied in the block state, so a final commit/memory
# write is always possible before stopping. They are not force-allowed either:
# the hook simply stays silent and the user's normal permission rules apply.
def is_checkpoint_action(stdin_json: dict) -> bool:
    if not isinstance(stdin_json, dict):
        return False
    tool = stdin_json.get("tool_name", "")
    ti = stdin_json.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    if tool == "Bash":
        cmd = ti.get("command")
        cmd = cmd.strip() if isinstance(cmd, str) else ""
        if any(ch in cmd for ch in SHELL_CHAIN_CHARS):
            return False  # "git commit -m x && <anything>" is not a checkpoint
        words = cmd.split()
        if len(words) >= 2 and words[0] == "git" and words[1] in ("add", "commit", "stash"):
            return True
        # The plugin's own read-only status probe must work while blocked.
        return "usage_limiter.py" in cmd and "--mode dump" in cmd
    if tool in ("Write", "Edit", "NotebookEdit"):
        fp = ti.get("file_path") or ti.get("notebook_path")
        if not isinstance(fp, str):
            return False
        parts = fp.replace("\\", "/").split("/")
        return "memory" in parts[:-1] or "scratchpad" in parts[:-1] or parts[-1] == "MEMORY.md"
    return False


def _record_plugin_root() -> None:
    """Persist $CLAUDE_PLUGIN_ROOT so the user's statusLine can find this script."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(PLUGIN_ROOT_FILE, "w") as fh:
            fh.write(root)
    except Exception as e:
        _log(f"could not write plugin-root pointer: {e}")


# -----------------------------------------------------------------------------
# Modes
# -----------------------------------------------------------------------------
def mode_statusline(stdin_json):
    r = read_usage(stdin_json)
    maybe_refresh(r)

    model = ""
    branch = ""
    try:
        model = (stdin_json.get("model") or {}).get("display_name", "") if stdin_json else ""
    except Exception:
        pass
    try:
        sj = stdin_json or {}
        cwd = sj.get("cwd") or (sj.get("workspace") or {}).get("current_dir")
        if cwd:
            gitpath = os.path.join(cwd, ".git")
            gitdir = gitpath
            # A worktree/submodule has .git as a FILE containing "gitdir: <path>".
            if os.path.isfile(gitpath):
                with open(gitpath) as fh:
                    line = fh.read().strip()
                if line.startswith("gitdir:"):
                    gitdir = line.split(":", 1)[1].strip()
            head = os.path.join(gitdir, "HEAD")
            if os.path.exists(head):
                with open(head) as fh:
                    ref = fh.read().strip()
                branch = ref.split("/")[-1] if ref.startswith("ref:") else ref[:7]
    except Exception:
        pass

    if not r["ok"]:
        line = (
            f"{C_RED}⛽ usage: unavailable{C_RESET} "
            f"{C_DIM}(guard blind — see limiter.log){C_RESET}"
        )
    else:
        col = _pct_color(r["worst_pct"])
        s = f"{r['session_pct']:.0f}%" if _is_num(r["session_pct"]) else "?"
        rs = _fmt_reset(r["session_reset"])
        w = f"{r['week_pct']:.0f}%" if _is_num(r["week_pct"]) else "?"
        seg = f"{col}⛽ S:{s}{C_RESET}"
        if rs:
            seg += f"{C_DIM}⟲{rs}{C_RESET}"
        seg += f"  W:{w}"
        cs = credits_str(r)
        if cs:
            cc = C_RED if r.get("credits_enabled") else C_DIM
            seg += f"  {cc}💳{cs}{C_RESET}"
        if r.get("stale"):
            age = r.get("age_min")
            age_txt = f"{age:.0f}m" if _is_num(age) else "?"
            seg += f"  {C_YELLOW}⚠stale {age_txt}{C_RESET}"
        line = seg

    prefix = ""
    if model:
        prefix += f"{C_DIM}{model}{C_RESET} "
    if branch:
        prefix += f"{C_DIM}({branch}){C_RESET} "
    sys.stdout.write(prefix + line)


def mode_gate(stdin_json):
    if os.environ.get(RECURSION_ENV) == "1":
        emit({})
        return
    stdin_json = stdin_json or {}
    r = read_usage(stdin_json)
    maybe_refresh(r)
    warn_pct, block_pct = CFG["warn_pct"], CFG["block_pct"]

    # Unknown / stale-loud: FAIL OPEN, but say so (throttled) so we know it's blind.
    if not r["ok"] or r["stale"]:
        if _marker_age_min(BLIND_MARKER) > CFG["warn_throttle_min"]:
            _touch(BLIND_MARKER)
            why = r["error"] or _age_str(r)
            emit(
                {
                    "systemMessage": (
                        f"⚠ extra-usage limiter is blind: {why}. Credit guard not guaranteed."
                    ),
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": (
                            f"[extra-usage-limiter] Cannot confirm plan usage ({why}). "
                            "Be conservative: avoid launching subagents/loops and checkpoint "
                            "often until a fresh reading is available."
                        ),
                    },
                }
            )
        else:
            emit({})
        return

    worst = r["worst_pct"]

    # HARD BLOCK
    if worst >= block_pct:
        if is_checkpoint_action(stdin_json):
            # No permissionDecision: the call goes through the user's normal permission
            # flow. Only a systemMessage so the user sees why other calls are blocked.
            emit(
                {
                    "systemMessage": (
                        f"⛔ {worst:.0f}% usage — checkpoint action not blocked; "
                        "everything else is."
                    )
                }
            )
            return
        rs = _fmt_reset(r["session_reset"]) or "reset time unknown"
        credit_note = ""
        try:
            if r.get("credits_enabled"):
                cs = credits_str(r)
                credit_note = (
                    f" Extra-usage credits are ENABLED ({cs} used), "
                    "so continuing now would spend them."
                )
        except Exception as e:  # a display string must never cancel the deny
            _log(f"credit note skipped: {e}")
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Plan usage at {worst:.0f}% (>= {block_pct}% block threshold)."
                        f"{credit_note} STOP: do not run more tool calls. Checkpoint "
                        f"(git commit) is still allowed. Tell the user where things stand and "
                        f"wait for the reset (~{rs}). Only spend extra-usage credits with the "
                        f"user's explicit per-instance approval."
                    ),
                },
                "systemMessage": (
                    f"⛔ extra-usage limiter: {worst:.0f}% — tool calls blocked to protect "
                    f"extra-usage credits. Reset ~{rs}."
                ),
            }
        )
        return

    # WARN
    if worst >= warn_pct:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": (
                    f"[extra-usage-limiter] Plan usage {worst:.0f}% (warn at {warn_pct}%, "
                    f"hard-block at {block_pct}%). Wind down: finish and commit current work, "
                    "avoid new subagents/loops, and prepare to pause for the reset. Do not "
                    "switch to extra-usage credits without the user's OK."
                ),
            }
        }
        if _marker_age_min(WARN_MARKER) > CFG["warn_throttle_min"]:
            _touch(WARN_MARKER)
            rs = _fmt_reset(r["session_reset"])
            out["systemMessage"] = (
                f"⚠ extra-usage limiter: {worst:.0f}% of your plan window used"
                + (f" (resets {rs})" if rs else "")
                + " — winding down."
            )
        emit(out)
        return

    emit({})  # healthy: silent allow


def mode_context(stdin_json):
    if os.environ.get(RECURSION_ENV) == "1":
        emit({})
        return
    r = read_usage(stdin_json)
    maybe_refresh(r)
    warn_pct, block_pct = CFG["warn_pct"], CFG["block_pct"]

    ctx = "[extra-usage-limiter] " + status_sentence(r) + "."
    if not r["ok"] or r["stale"]:
        ctx += " (Reading is unavailable or stale — guard cannot be guaranteed; be conservative.)"
    elif r["worst_pct"] >= block_pct:
        ctx += (
            f" AT/OVER the {block_pct}% hard stop — do not start new work; "
            "checkpoint and wait for reset."
        )
    elif r["worst_pct"] >= warn_pct:
        ctx += f" Over the {warn_pct}% warn line — wind down and avoid subagents/loops."
    ctx += " Never spend extra-usage credits without the user's explicit per-instance approval."

    emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}})


def mode_selfcheck(stdin_json):
    if os.environ.get(RECURSION_ENV) == "1":
        emit({})
        return
    _record_plugin_root()
    r = read_usage(stdin_json)
    maybe_refresh(r)

    if not r["ok"]:
        # LOUD: this is the "know when it breaks" tripwire.
        emit(
            {
                "systemMessage": (
                    f"⚠⚠ extra-usage limiter SELF-CHECK FAILED: {r['error']}. "
                    "The extra-usage credit guard is NOT protecting this session. "
                    "Likely a Claude Code format change (or an API-key login, which has no "
                    "plan windows). See limiter.log in ~/.claude/.claude-extra-usage-limiter/ "
                    "and fix read_usage() in the plugin's scripts/usage_limiter.py."
                ),
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": (
                        "[extra-usage-limiter] SELF-CHECK FAILED — plan-usage reading "
                        f"unavailable. Reason: {r['error']}. Treat the credit guard as OFF: be "
                        "conservative with subagents/loops and confirm with the user before "
                        "anything that could spend extra-usage credits."
                    ),
                },
            }
        )
        return

    note = (
        f"[extra-usage-limiter] Active (warn {CFG['warn_pct']:.0f}%, "
        f"hard-block {CFG['block_pct']:.0f}%). {status_sentence(r)}"
    )
    if r["stale"]:
        note += " NOTE: reading is stale; a background refresh was requested."
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": note}})


def mode_dump(stdin_json):
    r = read_usage(stdin_json)
    out = dict(r)
    out["session_reset"] = _fmt_reset(r["session_reset"])
    out["week_reset"] = _fmt_reset(r["week_reset"])
    out["credits_str"] = credits_str(r)
    out["config"] = CFG
    out["paths"] = {
        "claude_json": CLAUDE_JSON,
        "state_dir": STATE_DIR,
        "config_file": CONFIG_FILE,
        "plugin_root_file": PLUGIN_ROOT_FILE,
    }
    print(json.dumps(out, indent=2))


# -----------------------------------------------------------------------------
# Entry
# -----------------------------------------------------------------------------
def main() -> int:
    mode = "dump"
    argv = sys.argv[1:]
    if "--mode" in argv:
        i = argv.index("--mode")
        if i + 1 < len(argv):
            mode = argv[i + 1]
    elif argv:
        mode = argv[0]

    stdin_json = None
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                stdin_json = json.loads(raw)
        except Exception:
            stdin_json = None
    if not isinstance(stdin_json, dict):
        stdin_json = None  # a bare number/list/string on stdin is not hook input

    dispatch = {
        "statusline": mode_statusline,
        "gate": mode_gate,
        "context": mode_context,
        "selfcheck": mode_selfcheck,
        "dump": mode_dump,
    }
    fn = dispatch.get(mode)
    if not fn:
        sys.stderr.write(f"unknown mode: {mode}\n")
        return 0  # never fail a hook on our own arg error

    try:
        fn(stdin_json)
    except Exception as e:
        # Absolute backstop: a crashing hook must not brick Claude Code.
        _log(f"mode {mode} crashed: {e}")
        try:
            if mode == "statusline":
                sys.stdout.write(f"{C_RED}⛽ usage: guard error{C_RESET}")
            else:
                emit({"systemMessage": f"⚠ extra-usage limiter {mode} crashed: {e}"})
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
