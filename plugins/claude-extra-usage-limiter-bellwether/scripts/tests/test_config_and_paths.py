import json

from tests.conftest import SCRIPT, make_cache


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
    env.write_config(json.dumps({"warn_pct": "high", "block_pct": 50}))  # block < default warn
    m = env.load()
    assert m.CFG["warn_pct"] == 85 and m.CFG["block_pct"] == 97


def test_paths_come_from_env(env):
    m = env.load()
    assert m.CLAUDE_JSON == str(env.claude_json)
    assert m.STATE_DIR == str(env.state)
    assert m.PLUGIN_ROOT_FILE == str(env.state / "plugin-root")
    assert m.RECURSION_ENV == "CLAUDE_EXTRA_USAGE_LIMITER_REFRESH"


def test_read_usage_valid(env):
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


def test_read_usage_missing_file(env):
    m = env.load()
    r = m.read_usage(None)
    assert not r["ok"] and "cannot read" in r["error"]


def test_read_usage_stale(env):
    env.write_cache(make_cache(age_min=45))
    m = env.load()
    assert m.read_usage(None)["stale"] is True


def test_live_stdin_merge_and_epoch_leak_rejected(env):
    env.write_cache(make_cache(session=14, week=51))
    m = env.load()
    live = {
        "rate_limits": {
            "five_hour": {"used_percentage": 60, "resets_at": 1789000000},
            "seven_day": {"used_percentage": 1788962159321},
        }
    }
    r = m.read_usage(live)
    assert r["session_pct"] == 60 and r["source"] == "stdin+cache"
    assert r["week_pct"] == 51  # leaked epoch rejected, cache value kept
    assert r["worst_pct"] == 60


def test_no_personal_name_in_source():
    text = SCRIPT.read_text()
    assert "Matt" not in text
    assert "usage_tripwire" not in text
