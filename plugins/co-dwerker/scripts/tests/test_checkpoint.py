import json
import subprocess

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
    assert prog["step_status"] == "completed"
    assert prog["status"] == "in_progress"  # issue status, not step status


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


def test_refuses_to_clobber_invalid_json(tmp_path, capsys):
    state = tmp_path / ".co-dwerker.state.json"
    state.write_text("{not json")
    code = checkpoint.main(["--state-file", str(state), "start-issue", "3"])
    assert code == 2
    assert "not valid JSON" in capsys.readouterr().err
    assert state.read_text() == "{not json"


def test_issues_created_and_main_checkout_survive_issue_boundaries(tmp_path):
    _run(tmp_path, "start-issue", "7", "--set", "main_checkout=/repo")
    _run(tmp_path, "set", "--append", "issues_created=44")
    _run(tmp_path, "finish-issue")
    _, state = _run(tmp_path, "start-issue", "8")
    ctx = _read(state)["progress"]["context"]
    assert ctx["issues_created"] == [44]
    assert ctx["main_checkout"] == "/repo"


def test_set_top_writes_top_level_keys(tmp_path):
    _run(tmp_path, "start-issue", "7")
    code, state = _run(tmp_path, "set", "--top", "repo_owner_name=o/r", "--top", "work_mode=repo")
    assert code == 0
    data = _read(state)
    assert data["repo_owner_name"] == "o/r" and data["work_mode"] == "repo"
    code, _ = _run(tmp_path, "set", "--top", "progress=1")
    assert code == 2


def test_default_state_file_resolves_to_main_checkout_from_worktree(tmp_path, monkeypatch):
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", str(main)], check=True)
    subprocess.run(
        ["git", "-C", str(main), "commit", "-q", "--allow-empty", "-m", "init"], check=True
    )
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "feat"],
        check=True,
    )
    monkeypatch.chdir(tmp_path / "wt")
    assert checkpoint.default_state_file() == str(main / ".co-dwerker.state.json")
    checkpoint.main(["start-issue", "5"])
    checkpoint.main(["mark", "3.3", "completed"])
    assert (main / ".co-dwerker.state.json").exists()
    assert not (tmp_path / "wt" / ".co-dwerker.state.json").exists()
    monkeypatch.chdir(main)
    prog = _read(main / ".co-dwerker.state.json")["progress"]
    assert prog["completed_steps"] == ["3.3"]


def test_default_state_file_outside_git_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert checkpoint.default_state_file() == str(tmp_path / ".co-dwerker.state.json")


def test_end_session_writes_last_session_and_global_file(tmp_path):
    state = tmp_path / ".co-dwerker.state.json"
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _run(
        tmp_path, "start-issue", "42", "--set", "work_mode=repo", "--set", "planned_issues=[42, 43]"
    )
    _run(tmp_path, "set", "--set", "branch=feature/42", "--append", "issues_created=50")
    _run(tmp_path, "mark", "3.5a", "in_progress", "--set", "local_app_skip_reason=no db")
    glob = tmp_path / "global.json"
    code, _ = _run(
        tmp_path,
        "end-session",
        "--repo-owner-name",
        "owner/repo",
        "--prs-created",
        "57",
        "--date",
        "2026-09-04",
        "--global-state-file",
        str(glob),
        "--legacy-state-file",
        str(tmp_path / "legacy.json"),
    )
    assert code == 0
    data = _read(state)
    last = data["last_session"]
    assert last["date"] == "2026-09-04"
    assert last["current_issue"] == 42 and last["current_step"] == "3.5a"
    assert last["branch"] == "feature/42"
    assert last["prs_created"] == [57] and last["issues_created"] == [50]
    assert last["local_app_skip_reason"] == "no db"
    assert data["work_mode"] == "repo" and data["repo_owner_name"] == "owner/repo"
    assert data["repo_local_path"] == str(tmp_path)
    assert data["planned_issues"] == [42, 43]
    assert data["progress"]["issue"] == 42  # live progress untouched for Resume Check
    assert json.loads(glob.read_text()) == {
        "repo_owner_name": "owner/repo",
        "repo_local_path": str(tmp_path),
    }
    assert not (tmp_path / ".gitignore").exists()  # never edits a tracked file
    exclude = (tmp_path / ".git" / "info" / "exclude").read_text()
    assert exclude.count(".co-dwerker.state.json") == 1


def test_show_prints_last_session(tmp_path, capsys):
    _run(tmp_path, "start-issue", "1")
    _run(tmp_path, "end-session", "--global-state-file", str(tmp_path / "g.json"))
    _run(tmp_path, "show")
    out = capsys.readouterr().out
    assert "last_session:" in out and "progress:" in out


def test_status_is_issue_level_and_step_status_tracks_marks(tmp_path):
    _run(tmp_path, "start-issue", "9")
    _, state = _run(tmp_path, "mark", "3.1", "completed")
    prog = _read(state)["progress"]
    assert prog["status"] == "in_progress" and prog["step_status"] == "completed"
    _, state = _run(tmp_path, "finish-issue")
    prog = _read(state)["progress"]
    assert prog["status"] == "completed" and prog["issue"] is None


def test_state_file_is_added_to_git_exclude_not_gitignore(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _run(tmp_path, "start-issue", "1")
    exclude = (tmp_path / ".git" / "info" / "exclude").read_text()
    assert ".co-dwerker.state.json" in exclude
    assert not (tmp_path / ".gitignore").exists()
    status = subprocess.run(
        ["git", "-C", str(tmp_path), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    assert ".co-dwerker.state.json" not in status


def test_exclude_append_preserves_existing_rules_without_trailing_newline(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    exclude = tmp_path / ".git" / "info" / "exclude"
    exclude.write_text("*.log\nnode_modules/")  # no trailing newline
    _run(tmp_path, "start-issue", "1")
    lines = exclude.read_text().splitlines()
    assert "node_modules/" in lines and ".co-dwerker.state.json" in lines


def test_step_id_without_phase_is_rejected(tmp_path, capsys):
    _run(tmp_path, "start-issue", "1")
    code, state = _run(tmp_path, "mark", "3", "completed")
    assert code == 2
    assert "<phase>.<step>" in capsys.readouterr().err
    assert _read(state)["progress"]["completed_steps"] == []


def test_end_session_rejects_bad_number_list(tmp_path, capsys):
    _run(tmp_path, "start-issue", "1")
    code, _ = _run(
        tmp_path,
        "end-session",
        "--completed",
        "57,none",
        "--global-state-file",
        str(tmp_path / "g.json"),
    )
    assert code == 2
    assert "comma-separated list of numbers" in capsys.readouterr().err


def test_nan_values_are_kept_as_strings(tmp_path):
    _run(tmp_path, "start-issue", "1")
    _, state = _run(tmp_path, "set", "--set", "weird=NaN")
    assert _read(state)["progress"]["context"]["weird"] == "NaN"
    json.loads(state.read_text())  # still strictly valid JSON


def test_show_prints_completed_this_session(tmp_path, capsys):
    _run(tmp_path, "start-issue", "1")
    _run(tmp_path, "finish-issue")
    _run(tmp_path, "show")
    assert "completed_this_session: [1]" in capsys.readouterr().out
