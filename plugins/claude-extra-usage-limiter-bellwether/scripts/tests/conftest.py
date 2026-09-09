"""Shared fixtures: point every path the engine touches at a tmp dir and reload it."""

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "usage_limiter.py"


def load_module():
    """Import usage_limiter.py fresh so module-level config/paths pick up the env."""
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
                    "is_enabled": credits,
                    "used_credits": 471,
                    "monthly_limit": 15000,
                    "currency": "USD",
                    "decimal_places": 2,
                    "spend_limit_reached": False,
                },
            },
        }
    }


class Env:
    def __init__(self, claude_json, state, config):
        self.claude_json = claude_json
        self.state = state
        self.config = config

    def write_cache(self, doc):
        self.claude_json.write_text(json.dumps(doc))

    def write_config(self, text):
        self.config.write_text(text)

    def load(self):
        return load_module()


@pytest.fixture
def env(tmp_path, monkeypatch):
    claude_json = tmp_path / "claude.json"
    state = tmp_path / "state"
    config = tmp_path / "config.json"
    monkeypatch.setenv("CEUL_CLAUDE_JSON", str(claude_json))
    monkeypatch.setenv("CEUL_STATE_DIR", str(state))
    monkeypatch.setenv("CEUL_CONFIG", str(config))
    monkeypatch.delenv("CLAUDE_EXTRA_USAGE_LIMITER_REFRESH", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    return Env(claude_json, state, config)
