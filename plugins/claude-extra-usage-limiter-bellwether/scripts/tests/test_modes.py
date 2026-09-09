import json

from tests.conftest import make_cache

LS = {"tool_name": "Bash", "tool_input": {"command": "ls"}}


def run_mode(capsys, fn, stdin=None):
    fn(stdin)
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


# --- gate ---------------------------------------------------------------------


def test_gate_healthy_is_silent_allow(env, capsys):
    env.write_cache(make_cache(session=10, week=20))
    m = env.load()
    assert run_mode(capsys, m.mode_gate, LS) == {}


def test_gate_warn_adds_context_not_deny(env, capsys):
    env.write_cache(make_cache(session=90, week=20))
    m = env.load()
    out = run_mode(capsys, m.mode_gate, LS)
    hs = out["hookSpecificOutput"]
    assert "permissionDecision" not in hs
    assert "Wind down" in hs["additionalContext"] and "the user" in hs["additionalContext"]
    assert "winding down" in out["systemMessage"]


def test_gate_warn_banner_is_throttled(env, capsys):
    env.write_cache(make_cache(session=90, week=20))
    m = env.load()
    first = run_mode(capsys, m.mode_gate, LS)
    second = run_mode(capsys, m.mode_gate, LS)
    assert "systemMessage" in first and "systemMessage" not in second
    assert "additionalContext" in second["hookSpecificOutput"]  # context still injected


def test_gate_block_denies(env, capsys):
    env.write_cache(make_cache(session=98, week=20))
    m = env.load()
    out = run_mode(capsys, m.mode_gate, LS)
    hs = out["hookSpecificOutput"]
    assert hs["permissionDecision"] == "deny"
    assert "credits are ENABLED" in hs["permissionDecisionReason"]
    assert "Tell the user" in hs["permissionDecisionReason"]


def test_gate_block_on_weekly_window_too(env, capsys):
    env.write_cache(make_cache(session=5, week=99))
    m = env.load()
    assert run_mode(capsys, m.mode_gate, LS)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_gate_block_allows_checkpoint(env, capsys):
    env.write_cache(make_cache(session=98, week=20))
    m = env.load()
    commit = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
    assert run_mode(capsys, m.mode_gate, commit)["hookSpecificOutput"]["permissionDecision"] == (
        "allow"
    )


def test_gate_respects_custom_thresholds(env, capsys):
    env.write_config(json.dumps({"warn_pct": 50, "block_pct": 60}))
    env.write_cache(make_cache(session=65, week=20))
    m = env.load()
    assert run_mode(capsys, m.mode_gate, LS)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_gate_stale_fails_open(env, capsys):
    env.write_cache(make_cache(session=99, week=99, age_min=60))
    m = env.load()
    out = run_mode(capsys, m.mode_gate, LS)
    assert "permissionDecision" not in out.get("hookSpecificOutput", {})
    assert "blind" in out["systemMessage"]


def test_gate_missing_cache_fails_open(env, capsys):
    m = env.load()  # no cache file written
    out = run_mode(capsys, m.mode_gate, LS)
    assert "permissionDecision" not in out.get("hookSpecificOutput", {})


def test_gate_noop_in_refresh_child(env, capsys, monkeypatch):
    env.write_cache(make_cache(session=99, week=99))
    monkeypatch.setenv("CLAUDE_EXTRA_USAGE_LIMITER_REFRESH", "1")
    m = env.load()
    assert run_mode(capsys, m.mode_gate, LS) == {}


def test_gate_tolerates_none_stdin(env, capsys):
    env.write_cache(make_cache(session=98, week=20))
    m = env.load()
    assert run_mode(capsys, m.mode_gate, None)["hookSpecificOutput"]["permissionDecision"] == "deny"


# --- checkpoint classifier ------------------------------------------------------


def test_is_checkpoint_action(env):
    m = env.load()
    yes = [
        {"tool_name": "Bash", "tool_input": {"command": "git add -A"}},
        {"tool_name": "Bash", "tool_input": {"command": " git stash push -m x"}},
        {"tool_name": "Write", "tool_input": {"file_path": "/x/memory/notes.md"}},
        {"tool_name": "Edit", "tool_input": {"file_path": "/x/scratchpad/a.txt"}},
        {"tool_name": "Write", "tool_input": {"file_path": "/x/MEMORY.md"}},
        {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "/x/memory/n.ipynb"}},
    ]
    no = [
        {"tool_name": "Bash", "tool_input": {"command": "git push"}},
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf x"}},
        {"tool_name": "Write", "tool_input": {"file_path": "/x/src/app.py"}},
        {"tool_name": "Agent", "tool_input": {}},
        {"tool_name": "Bash", "tool_input": {}},
    ]
    assert all(m.is_checkpoint_action(a) for a in yes)
    assert not any(m.is_checkpoint_action(a) for a in no)


# --- context ---------------------------------------------------------------------


def test_context_mentions_usage_and_policy(env, capsys):
    env.write_cache(make_cache(session=14, week=51))
    m = env.load()
    ctx = run_mode(capsys, m.mode_context, {})["hookSpecificOutput"]["additionalContext"]
    assert "session 14%" in ctx and "week 51%" in ctx
    assert "credits ENABLED" in ctx and "the user's explicit" in ctx
    assert "warn line" not in ctx and "hard stop" not in ctx


def _ctx(capsys, m):
    return run_mode(capsys, m.mode_context, {})["hookSpecificOutput"]["additionalContext"]


def test_context_flags_bands(env, capsys):
    env.write_cache(make_cache(session=90, week=10))
    m = env.load()
    assert "warn line" in _ctx(capsys, m)
    env.write_cache(make_cache(session=99, week=10))
    assert "hard stop" in _ctx(capsys, m)


def test_context_unavailable_is_conservative(env, capsys):
    m = env.load()
    ctx = run_mode(capsys, m.mode_context, {})["hookSpecificOutput"]["additionalContext"]
    assert "unavailable" in ctx and "be conservative" in ctx


# --- selfcheck -------------------------------------------------------------------


def test_selfcheck_writes_plugin_root_pointer(env, capsys, monkeypatch):
    env.write_cache(make_cache())
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/plugins/ceul/1.0.0")
    m = env.load()
    out = run_mode(capsys, m.mode_selfcheck, {})
    assert "Active (warn 85%, hard-block 97%)" in out["hookSpecificOutput"]["additionalContext"]
    assert (env.state / "plugin-root").read_text() == "/plugins/ceul/1.0.0"


def test_selfcheck_without_plugin_root_writes_nothing(env, capsys):
    env.write_cache(make_cache())
    m = env.load()
    run_mode(capsys, m.mode_selfcheck, {})
    assert not (env.state / "plugin-root").exists()


def test_selfcheck_loud_when_broken(env, capsys):
    env.write_cache({"cachedUsageUtilization": {"nope": 1}})
    m = env.load()
    out = run_mode(capsys, m.mode_selfcheck, {})
    assert "SELF-CHECK FAILED" in out["systemMessage"]
    assert "utilization missing" in out["hookSpecificOutput"]["additionalContext"]


# --- refresh ---------------------------------------------------------------------


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
    assert args[0] == ["/usr/local/bin/claude", "-p", "/usage"]
    assert kwargs["env"]["CLAUDE_EXTRA_USAGE_LIMITER_REFRESH"] == "1"
    assert kwargs["start_new_session"] is True


def test_refresh_skipped_when_fresh_or_child(env, monkeypatch):
    env.write_cache(make_cache(age_min=1))
    m = env.load()
    calls = []
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(m.shutil, "which", lambda _: "/usr/local/bin/claude")
    m.maybe_refresh(m.read_usage(None))
    monkeypatch.setenv("CLAUDE_EXTRA_USAGE_LIMITER_REFRESH", "1")
    env.write_cache(make_cache(age_min=30))
    m.maybe_refresh(m.read_usage(None))
    assert calls == []


def test_refresh_skipped_when_no_claude_binary(env, monkeypatch):
    env.write_cache(make_cache(age_min=30))
    m = env.load()
    calls = []
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(m.shutil, "which", lambda _: None)
    monkeypatch.setattr(m.os.path, "exists", lambda _: False)
    m.maybe_refresh(m.read_usage(None))
    assert calls == []


# --- statusline --------------------------------------------------------------------


def test_statusline_renders(env, capsys):
    env.write_cache(make_cache(session=14, week=51))
    m = env.load()
    m.mode_statusline({"model": {"display_name": "Fable 5.1"}})
    out = capsys.readouterr().out
    assert "S:14%" in out and "W:51%" in out and "Fable 5.1" in out and "$4.71/$150" in out


def test_statusline_unavailable(env, capsys):
    m = env.load()
    m.mode_statusline({})
    assert "usage: unavailable" in capsys.readouterr().out


def test_statusline_shows_branch_from_git_dir(env, capsys, tmp_path):
    env.write_cache(make_cache())
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/feature/x\n")
    m = env.load()
    m.mode_statusline({"cwd": str(repo)})
    assert "(x)" in capsys.readouterr().out


# --- entrypoint -----------------------------------------------------------------------


def test_main_unknown_mode_exits_zero(env, monkeypatch, capsys):
    m = env.load()
    monkeypatch.setattr(m.sys, "argv", ["usage_limiter.py", "--mode", "bogus"])
    assert m.main() == 0
    assert "unknown mode" in capsys.readouterr().err


def test_main_crash_is_contained(env, monkeypatch, capsys):
    env.write_cache(make_cache())
    m = env.load()
    monkeypatch.setattr(m.sys, "argv", ["usage_limiter.py", "--mode", "gate"])

    def boom(_):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(m, "mode_gate", boom)
    assert m.main() == 0
    assert "crashed: kaboom" in capsys.readouterr().out
