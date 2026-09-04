import json

import checkpoint


def _run(tmp_path, *argv):
    state = tmp_path / ".co-dwerker.state.json"
    return checkpoint.main(["--state-file", str(state), *argv]), state


def _read(state):
    return json.loads(state.read_text())


def test_start_issue_creates_progress_block(tmp_path):
    code, state = _run(tmp_path, "start-issue", "42", "--phase", "2", "--set", "work_mode=repo")
    assert code == 0
    prog = _read(state)["progress"]
    assert prog["issue"] == 42
    assert prog["phase"] == "2"
    assert prog["status"] == "in_progress"
    assert prog["completed_steps"] == []
    assert prog["context"]["work_mode"] == "repo"


def test_mark_and_gate_flow(tmp_path):
    _run(tmp_path, "start-issue", "7")
    for step in checkpoint.PHASES["3"][:-1]:
        _run(tmp_path, "mark", f"3.{step}", "completed")
    code, state = _run(tmp_path, "gate", "3")
    assert code == 1  # 3.8 still missing
    _run(tmp_path, "mark", "3.8", "completed")
    code, _ = _run(tmp_path, "gate", "3")
    assert code == 0
    prog = _read(state)["progress"]
    assert prog["step"] == "3.8"
    assert prog["status"] == "completed"


def test_gate_skip_for_inapplicable_step(tmp_path):
    _run(tmp_path, "start-issue", "7")
    for step in ["merge", "ci", "close-issue", "cleanup"]:
        _run(tmp_path, "mark", f"5.{step}", "completed")
    code, _ = _run(tmp_path, "gate", "5")
    assert code == 1
    code, _ = _run(tmp_path, "gate", "5", "--skip", "docs-merge", "--skip", "board")
    assert code == 0


def test_reopening_a_step_removes_it_from_completed(tmp_path):
    _run(tmp_path, "start-issue", "7")
    _run(tmp_path, "mark", "3.5a", "completed")
    _, state = _run(tmp_path, "mark", "3.5a", "in_progress")
    assert "3.5a" not in _read(state)["progress"]["completed_steps"]


def test_set_and_append_context_values_parse_json(tmp_path):
    _run(tmp_path, "start-issue", "7")
    _run(tmp_path, "set", "--set", "pr_number=57", "--set", "pr_url=https://x/pull/57")
    _run(tmp_path, "set", "--append", "local_app_pids=111", "--append", "local_app_pids=222")
    _, state = _run(tmp_path, "set", "--append", "local_app_pids=111")  # idempotent
    ctx = _read(state)["progress"]["context"]
    assert ctx["pr_number"] == 57
    assert ctx["pr_url"] == "https://x/pull/57"
    assert ctx["local_app_pids"] == [111, 222]


def test_mark_accepts_unknown_step_with_note(tmp_path, capsys):
    _run(tmp_path, "start-issue", "7")
    code, _ = _run(tmp_path, "mark", "3.99", "completed")
    assert code == 0
    assert "not in the built-in step manifest" in capsys.readouterr().err


def test_finish_issue_clears_progress_and_keeps_session_keys(tmp_path):
    _run(tmp_path, "start-issue", "7", "--set", "planned_issues=[7, 8]", "--set", "pr_number=1")
    _run(tmp_path, "mark", "3.1", "completed")
    _, state = _run(tmp_path, "finish-issue")
    data = _read(state)
    assert data["completed_this_session"] == [7]
    prog = data["progress"]
    assert prog["issue"] is None
    assert prog["completed_steps"] == []
    assert prog["context"]["planned_issues"] == [8]
    assert "pr_number" not in prog["context"]


def test_preserves_other_state_file_keys(tmp_path):
    state = tmp_path / ".co-dwerker.state.json"
    state.write_text(json.dumps({"work_mode": "project", "last_session": {"date": "2026-09-01"}}))
    checkpoint.main(["--state-file", str(state), "start-issue", "3"])
    data = _read(state)
    assert data["work_mode"] == "project"
    assert data["last_session"]["date"] == "2026-09-01"
    assert data["progress"]["issue"] == 3


def test_refuses_to_clobber_invalid_json(tmp_path):
    state = tmp_path / ".co-dwerker.state.json"
    state.write_text("{not json")
    try:
        checkpoint.main(["--state-file", str(state), "start-issue", "3"])
    except SystemExit as exc:
        assert "not valid JSON" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit")
    assert state.read_text() == "{not json"
