"""The central invariant: only a KNOWN reading in 0..100 at/above block_pct may deny.

Everything else — garbage values, missing timestamps, malformed stdin, crashes — must
fail OPEN (no deny), exit 0, and print parseable JSON (or nothing) on stdout.
"""

import json
import os
import subprocess
import sys
import time

import pytest

from tests.conftest import SCRIPT, make_cache

LS = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
BAD_PCTS = [-5, 101, 1788962159321, 1e12, float("inf"), float("nan"), "99", True, None, [99]]


def gate(m, capsys, stdin=LS):
    m.mode_gate(stdin)
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


def decision(out):
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision")


# --- garbage percentages can never deny ------------------------------------------------


@pytest.mark.parametrize("bad", BAD_PCTS, ids=repr)
def test_out_of_range_session_pct_never_denies(env, capsys, bad):
    doc = make_cache(session=0, week=0)
    doc["cachedUsageUtilization"]["utilization"]["five_hour"]["utilization"] = bad
    doc["cachedUsageUtilization"]["utilization"]["seven_day"]["utilization"] = bad
    env.write_cache(doc)  # json.dumps emits Infinity/NaN literals; json.load reads them back
    m = env.load()
    r = m.read_usage(None)
    assert r["ok"] is False and r["worst_pct"] is None
    out = gate(m, capsys)
    assert decision(out) is None
    assert "blind" in out["systemMessage"]


def test_epoch_leak_in_cache_fails_open_not_closed(env, capsys):
    """The exact bug the original script only guarded on the stdin path."""
    doc = make_cache(session=1788962159321, week=10)
    env.write_cache(doc)
    m = env.load()
    r = m.read_usage(None)
    assert r["session_pct"] is None and r["week_pct"] == 10 and r["worst_pct"] == 10
    assert decision(gate(m, capsys)) is None


def test_selfcheck_is_loud_when_all_pcts_are_garbage(env, capsys):
    doc = make_cache()
    doc["cachedUsageUtilization"]["utilization"]["five_hour"]["utilization"] = -1
    doc["cachedUsageUtilization"]["utilization"]["seven_day"]["utilization"] = 500
    env.write_cache(doc)
    m = env.load()
    m.mode_selfcheck({})
    out = json.loads(capsys.readouterr().out)
    assert "SELF-CHECK FAILED" in out["systemMessage"]
    assert "0..100" in out["systemMessage"]


# --- missing / bad fetchedAtMs -------------------------------------------------------------


@pytest.mark.parametrize("fetched", [None, "yesterday", -1e18], ids=repr)
def test_missing_or_bad_timestamp_is_stale_and_does_not_crash(env, capsys, fetched):
    doc = make_cache(session=99, week=99)
    if fetched is None:
        del doc["cachedUsageUtilization"]["fetchedAtMs"]
    else:
        doc["cachedUsageUtilization"]["fetchedAtMs"] = fetched
    env.write_cache(doc)
    m = env.load()
    out = gate(m, capsys)
    assert decision(out) is None
    assert "crashed" not in out.get("systemMessage", "")
    assert "blind" in out["systemMessage"]
    if fetched is None:
        assert "timestamp missing" in out["systemMessage"]
    # statusline and selfcheck also survive
    m.mode_statusline({})
    sl = capsys.readouterr().out
    assert "guard error" not in sl and "⚠stale" in sl
    m.mode_selfcheck({})
    sc = json.loads(capsys.readouterr().out)
    assert "crashed" not in sc.get("systemMessage", "")


# --- a display-string problem must not cancel a deny ------------------------------------------


@pytest.mark.parametrize("dp", ["2", -1, 99, None, [2]], ids=repr)
def test_bad_decimal_places_keeps_the_deny(env, capsys, dp):
    doc = make_cache(session=99, week=10)
    doc["cachedUsageUtilization"]["utilization"]["extra_usage"]["decimal_places"] = dp
    env.write_cache(doc)
    m = env.load()
    out = gate(m, capsys)
    assert decision(out) == "deny"
    assert "crashed" not in out.get("systemMessage", "")


def test_credit_note_exception_keeps_the_deny(env, capsys, monkeypatch):
    env.write_cache(make_cache(session=99, week=10))
    m = env.load()

    def boom(_):
        raise RuntimeError("display bug")

    monkeypatch.setattr(m, "credits_str", boom)
    out = gate(m, capsys)
    assert decision(out) == "deny"


# --- malformed stdin / cache root ----------------------------------------------------------


@pytest.mark.parametrize("stdin", [5, "x", [1], {"tool_name": "Bash", "tool_input": "x"}], ids=repr)
def test_malformed_stdin_at_block_still_denies_or_ignores_cleanly(env, capsys, stdin):
    env.write_cache(make_cache(session=99, week=10))
    m = env.load()
    if isinstance(stdin, dict):
        # a Bash call with a non-dict tool_input is NOT a checkpoint: deny stands
        assert decision(gate(m, capsys, stdin)) == "deny"
    else:
        # main() normalizes non-object stdin to None before dispatch; mode_gate itself
        # must also survive being handed garbage directly
        out = gate(m, capsys, stdin)
        assert "crashed" not in out.get("systemMessage", "")


def test_list_rooted_cache_fails_open(env, capsys):
    env.write_cache([1, 2, 3])
    m = env.load()
    r = m.read_usage(None)
    assert r["ok"] is False and "not a JSON object" in r["error"]
    assert decision(gate(m, capsys)) is None


def test_status_sentence_with_nothing_known(env):
    m = env.load()
    r = m.read_usage(None)  # no cache file
    assert m.status_sentence(r) == "Plan usage: unavailable"


def test_statusline_crash_fallback(env, capsys, monkeypatch):
    env.write_cache(make_cache())
    m = env.load()
    monkeypatch.setattr(m.sys, "argv", ["usage_limiter.py", "--mode", "statusline"])
    monkeypatch.setattr(m, "mode_statusline", lambda _: 1 / 0)
    assert m.main() == 0
    assert "guard error" in capsys.readouterr().out


def test_config_refresh_floor(env):
    env.write_config(json.dumps({"refresh_after_min": 0, "warn_throttle_min": 0.2}))
    m = env.load()
    assert m.CFG["refresh_after_min"] == 5 and m.CFG["warn_throttle_min"] == 3


# --- the contract Claude Code depends on: exit 0 + JSON on stdout, for every mode ----------


@pytest.mark.parametrize("mode", ["gate", "context", "selfcheck", "statusline", "dump"])
@pytest.mark.parametrize(
    "cache",
    ["valid", "missing", "malformed", "list", "garbage_pct", "no_timestamp", "block"],
)
@pytest.mark.parametrize("stdin", ["{}", "5", "not json", "", '{"tool_name":"Bash"}'], ids=repr)
def test_subprocess_contract(tmp_path, mode, cache, stdin):
    claude_json = tmp_path / "claude.json"
    if cache == "valid":
        claude_json.write_text(json.dumps(make_cache()))
    elif cache == "malformed":
        claude_json.write_text("{nope")
    elif cache == "list":
        claude_json.write_text("[1]")
    elif cache == "garbage_pct":
        claude_json.write_text(json.dumps(make_cache(session=1e15, week=-3)))
    elif cache == "no_timestamp":
        doc = make_cache(session=99, week=99)
        del doc["cachedUsageUtilization"]["fetchedAtMs"]
        claude_json.write_text(json.dumps(doc))
    elif cache == "block":
        claude_json.write_text(json.dumps(make_cache(session=99, week=99)))
    # "missing": no file
    env = dict(
        os.environ,
        CEUL_CLAUDE_JSON=str(claude_json),
        CEUL_STATE_DIR=str(tmp_path / "state"),
        CEUL_CONFIG=str(tmp_path / "cfg.json"),
        CLAUDE_EXTRA_USAGE_LIMITER_REFRESH="1",  # never spawn `claude` from a test
    )
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    t0 = time.time()
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", mode],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    assert p.returncode == 0, p.stderr
    assert time.time() - t0 < 5
    if mode == "statusline":
        assert p.stdout  # some text, never empty
        assert "guard error" not in p.stdout
        return
    if mode == "dump":
        json.loads(p.stdout)
        return
    # In the refresh child every hook mode emits exactly {} — but the contract we care
    # about is "parseable JSON, exit 0"; a fuller check runs without the recursion env.
    out = json.loads(p.stdout) if p.stdout.strip() else {}
    assert isinstance(out, dict)


@pytest.mark.parametrize("cache", ["missing", "malformed", "garbage_pct", "no_timestamp"])
def test_subprocess_gate_never_denies_on_bad_data(tmp_path, cache):
    claude_json = tmp_path / "claude.json"
    if cache == "malformed":
        claude_json.write_text("{nope")
    elif cache == "garbage_pct":
        claude_json.write_text(json.dumps(make_cache(session=1e15, week=-3)))
    elif cache == "no_timestamp":
        doc = make_cache(session=99, week=99)
        del doc["cachedUsageUtilization"]["fetchedAtMs"]
        claude_json.write_text(json.dumps(doc))
    env = dict(
        os.environ,
        CEUL_CLAUDE_JSON=str(claude_json),
        CEUL_STATE_DIR=str(tmp_path / "state"),
        CEUL_CONFIG=str(tmp_path / "cfg.json"),
        PATH="/nonexistent",  # no `claude` binary -> refresh is skipped, nothing spawns
    )
    env.pop("CLAUDE_EXTRA_USAGE_LIMITER_REFRESH", None)
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", "gate"],
        input=json.dumps(LS),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    assert p.returncode == 0
    out = json.loads(p.stdout)
    assert decision(out) is None
    assert "crashed" not in out.get("systemMessage", "")


def test_subprocess_gate_denies_on_real_block(tmp_path):
    claude_json = tmp_path / "claude.json"
    claude_json.write_text(json.dumps(make_cache(session=99, week=10)))
    env = dict(
        os.environ,
        CEUL_CLAUDE_JSON=str(claude_json),
        CEUL_STATE_DIR=str(tmp_path / "state"),
        CEUL_CONFIG=str(tmp_path / "cfg.json"),
        PATH="/nonexistent",
    )
    env.pop("CLAUDE_EXTRA_USAGE_LIMITER_REFRESH", None)
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", "gate"],
        input=json.dumps(LS),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    assert p.returncode == 0
    assert decision(json.loads(p.stdout)) == "deny"
