import json

import localapp_diff as diff


def _entry(raw, normalized=None, offset=1.0, multiline=False):
    return {
        "captured_at_offset_seconds": offset,
        "raw": raw,
        "normalized": normalized or raw,
        "multiline": multiline,
    }


def _app(name, status, errors=(), warnings=()):
    return {
        "name": name,
        "type": "custom",
        "boot_status": status,
        "log_errors": list(errors),
        "log_warnings": list(warnings),
    }


def _write(tmp_path, filename, apps, commit="abc"):
    p = tmp_path / filename
    p.write_text(json.dumps({"apps": apps, "commit": commit}))
    return str(p)


def _run_diff(tmp_path, baseline_apps, current_apps, config=None):
    base = (
        _write(tmp_path, "base.json", baseline_apps)
        if baseline_apps is not None
        else str(tmp_path / "none.json")
    )
    cur = _write(tmp_path, "cur.json", current_apps, commit="def")
    cfg = str(tmp_path / ".co-dwerker.json")
    if config is not None:
        (tmp_path / ".co-dwerker.json").write_text(json.dumps(config))
    code = diff.main(["diff", "--baseline", base, "--current", cur, "--config", cfg, "--json"])
    report = json.loads((tmp_path / ".co-dwerker.localapp-diff.json").read_text())
    return code, report


def test_clean_when_identical(tmp_path):
    e, w = _entry("ERROR old"), _entry("WARN old")
    code, report = _run_diff(
        tmp_path, [_app("web", "started", [e], [w])], [_app("web", "started", [e], [w])]
    )
    assert code == 0 and report["result"] == "clean"
    app = report["apps"][0]
    assert app["boot"]["outcome"] == "ok"
    assert len(app["errors"]["pre_existing"]) == 1
    assert len(app["warnings"]["pre_existing"]) == 1


def test_new_error_blocks(tmp_path):
    code, report = _run_diff(
        tmp_path,
        [_app("web", "started")],
        [_app("web", "started", errors=[_entry("ERROR new thing")])],
    )
    assert code == 2 and report["result"] == "block"
    assert report["apps"][0]["errors"]["new"][0]["normalized"] == "ERROR new thing"


def test_boot_regression_blocks(tmp_path):
    code, report = _run_diff(tmp_path, [_app("web", "started")], [_app("web", "failed_to_start")])
    assert code == 2
    assert report["apps"][0]["boot"]["outcome"] == "regression"


def test_new_warning_needs_decision_and_groups_repeats(tmp_path):
    cur = _app(
        "web",
        "started",
        warnings=[
            _entry("2026-01-01 WARN slow query 12ms", "WARN slow query"),
            _entry("2026-01-02 WARN slow query 40ms", "WARN slow query"),
        ],
    )
    code, report = _run_diff(tmp_path, [_app("web", "started")], [cur])
    assert code == 1 and report["result"] == "needs_decision"
    new = report["apps"][0]["warnings"]["new"]
    assert len(new) == 1 and new[0]["count"] == 2


def test_dismissed_warning_is_filtered_from_both_sides(tmp_path):
    cur = _app("web", "started", warnings=[_entry("WARN noisy")])
    code, report = _run_diff(
        tmp_path, [_app("web", "started")], [cur], config={"dismissed_warnings": ["WARN noisy"]}
    )
    assert code == 0
    w = report["apps"][0]["warnings"]
    assert len(w["dismissed"]) == 1 and w["new"] == []


def test_resolved_entries_reported(tmp_path):
    code, report = _run_diff(
        tmp_path,
        [_app("web", "started", errors=[_entry("ERROR gone")], warnings=[_entry("WARN gone")])],
        [_app("web", "started")],
    )
    assert code == 0
    app = report["apps"][0]
    assert len(app["errors"]["resolved"]) == 1 and len(app["warnings"]["resolved"]) == 1


def test_fixed_boot_is_positive_not_blocking(tmp_path):
    code, report = _run_diff(tmp_path, [_app("web", "failed_to_start")], [_app("web", "started")])
    assert code == 0
    assert report["apps"][0]["boot"]["outcome"] == "fixed"


def test_still_failing_with_changed_mode_is_noted_not_blocking(tmp_path):
    code, report = _run_diff(
        tmp_path, [_app("web", "timeout")], [_app("web", "crashed_during_idle")]
    )
    assert code == 0
    boot = report["apps"][0]["boot"]
    assert boot["outcome"] == "still_failing" and "failure mode changed" in boot["note"]


def test_missing_baseline_file_reports_unbaselined(tmp_path):
    cur = _app("web", "started", errors=[_entry("ERROR x")], warnings=[_entry("WARN y")])
    code, report = _run_diff(tmp_path, None, [cur])
    assert code == 1
    assert report["baseline_file"] is None
    app = report["apps"][0]
    assert app["boot"]["outcome"] == "no_baseline"
    assert len(app["errors"]["unbaselined"]) == 1 and len(app["warnings"]["unbaselined"]) == 1
    assert app["errors"]["new"] == []  # unbaselined errors do not hard-block


def test_skipped_baseline_app_is_treated_as_no_baseline(tmp_path):
    cur = _app("web", "started", errors=[_entry("ERROR x")])
    code, report = _run_diff(tmp_path, [_app("web", "skipped")], [cur])
    assert code == 1
    assert report["apps"][0]["boot"]["baseline"] == "skipped"
    assert report["apps"][0]["errors"]["unbaselined"]


def test_app_missing_from_current_needs_decision(tmp_path):
    code, report = _run_diff(
        tmp_path, [_app("api", "started"), _app("web", "started")], [_app("web", "started")]
    )
    assert code == 1
    assert report["apps_missing_from_current"] == ["api"]


def test_local_app_skip_config_short_circuits(tmp_path, capsys):
    cur = _write(tmp_path, "cur.json", [_app("web", "failed_to_start")])
    cfg = tmp_path / ".co-dwerker.json"
    cfg.write_text(json.dumps({"local_app_skip": True}))
    code = diff.main(["diff", "--current", cur, "--config", str(cfg)])
    assert code == 0
    assert "local_app_skip" in capsys.readouterr().out


def test_dismiss_is_idempotent_and_preserves_other_keys(tmp_path):
    cfg = tmp_path / ".co-dwerker.json"
    cfg.write_text(json.dumps({"docs_repo": "org/docs", "dismissed_warnings": ["A"]}))
    diff.main(["dismiss", "--config", str(cfg), "--normalized", "B", "--normalized", "A"])
    diff.main(["dismiss", "--config", str(cfg), "--normalized", "B"])
    data = json.loads(cfg.read_text())
    assert data["docs_repo"] == "org/docs"
    assert data["dismissed_warnings"] == ["A", "B"]


def test_dismiss_creates_config_when_missing(tmp_path):
    cfg = tmp_path / ".co-dwerker.json"
    diff.main(["dismiss", "--config", str(cfg), "--normalized", "X"])
    assert json.loads(cfg.read_text()) == {"dismissed_warnings": ["X"]}


def test_text_report_lists_normalized_for_new_warnings(tmp_path, capsys):
    base = _write(tmp_path, "base.json", [_app("web", "started")])
    cur = _write(
        tmp_path,
        "cur.json",
        [
            _app(
                "web",
                "started",
                warnings=[_entry("2026 WARN thing 1234abcd1234abcd", "WARN thing <hex>")],
            )
        ],
    )
    code = diff.main(
        ["diff", "--baseline", base, "--current", cur, "--config", str(tmp_path / "nope.json")]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "NEW WARNINGS (1 unique)" in out
    assert "normalized: WARN thing <hex>" in out
    assert out.strip().endswith("RESULT: needs_decision")
