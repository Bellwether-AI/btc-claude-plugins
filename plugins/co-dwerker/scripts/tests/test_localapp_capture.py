import json
import os
import socket
import subprocess
import sys
import textwrap

import localapp_capture as cap

# --------------------------------------------------------------------------------------
# normalize()
# --------------------------------------------------------------------------------------


def test_normalize_strips_timestamp_uuid_pid_port_and_ansi():
    raw = (
        "\x1b[31m2026-05-15T14:23:00.123Z [Error] AuthMiddleware: failed to load key "
        "(request 123e4567-e89b-12d3-a456-426614174000) pid=4242 at http://localhost:7071/api "
        "addr 0x7fff5fbff8c0   extra   spaces\x1b[0m"
    )
    assert cap.normalize(raw) == (
        "[Error] AuthMiddleware: failed to load key (request <uuid>) pid=<pid> "
        "at http://localhost:<port>/api addr <addr> extra spaces"
    )


def test_normalize_is_stable_across_two_boots():
    a = "2026-01-01 10:00:00 WARNING:root:Deprecated key `legacy_mode` (req 0123456789abcdef0123)"
    b = "2026-02-02 11:11:11 WARNING:root:Deprecated key `legacy_mode` (req fedcba98765432100000)"
    assert cap.normalize(a) == cap.normalize(b)


def test_normalize_keeps_file_paths_and_short_numbers():
    line = "ValueError in app/services/auth.py line 42: expected 3 items"
    assert cap.normalize(line) == line


# --------------------------------------------------------------------------------------
# classify_lines()
# --------------------------------------------------------------------------------------


def _lines(text):
    return [(float(i), ln) for i, ln in enumerate(textwrap.dedent(text).strip("\n").splitlines())]


def test_python_traceback_folds_into_one_error_entry():
    errors, warnings = cap.classify_lines(_lines("""
            INFO starting
            Traceback (most recent call last):
              File "app.py", line 3, in <module>
                main()
              File "app.py", line 2, in main
                raise ValueError("boom")
            ValueError: boom
            INFO still running
            """))
    assert len(errors) == 1
    assert errors[0]["multiline"] is True
    assert errors[0]["line_count"] == 6
    assert errors[0]["raw"].endswith("ValueError: boom")
    assert warnings == []


def test_dotnet_unhandled_exception_folds_stack_frames():
    errors, _ = cap.classify_lines(_lines("""
            Unhandled exception. System.InvalidOperationException: bad state
               at Foo.Bar() in /src/Foo.cs:line 10
               at Program.Main()
            info: Microsoft.Hosting.Lifetime[0]
                  Application started.
            """))
    assert len(errors) == 1
    assert errors[0]["line_count"] == 3


def test_aspnet_fail_block_and_warn_block():
    errors, warnings = cap.classify_lines(_lines("""
            fail: Microsoft.AspNetCore.Server.Kestrel[13]
                  Connection id "0HN" bad request data
                  System.IO.IOException: reset
            warn: Microsoft.AspNetCore.DataProtection[35]
                  No XML encryptor configured
            info: fine
            """))
    assert len(errors) == 1 and errors[0]["line_count"] == 3
    assert len(warnings) == 1 and warnings[0]["line_count"] == 2


def test_single_line_classification_and_error_wins_ties():
    errors, warnings = cap.classify_lines(_lines("""
            WARNING:root:Deprecated config key
            ERROR:app:something failed with a warning attached
            [warn] npm deprecated package
            plain info line
            """))
    assert [e["raw"] for e in errors] == ["ERROR:app:something failed with a warning attached"]
    assert len(warnings) == 2


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def test_parse_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nexport A=1\nB=\"two words\"\nC='x'\nBAD LINE\n\n")
    assert cap.parse_env_file(str(env_file)) == {"A": "1", "B": "two words", "C": "x"}


def test_ensure_git_exclude_appends_once(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    cap.ensure_git_exclude(str(tmp_path), [".a.json", ".b-*.log"])
    cap.ensure_git_exclude(str(tmp_path), [".a.json"])
    content = (tmp_path / ".git" / "info" / "exclude").read_text()
    assert content.count(".a.json") == 1
    assert ".b-*.log" in content


# --------------------------------------------------------------------------------------
# integration: real subprocesses with short timings
# --------------------------------------------------------------------------------------

FAKE_SERVER = textwrap.dedent("""
    import http.server, socketserver, sys, threading, time
    port = int(sys.argv[1])
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("WARNING:root:Deprecated config key legacy_mode", flush=True)
    print("Running on http://127.0.0.1:%d" % port, flush=True)
    time.sleep(0.3)
    print("ERROR:app:Background timer failed "
          "(request 123e4567-e89b-12d3-a456-426614174000)", flush=True)
    while True:
        time.sleep(0.2)
    """)

FAKE_CRASHER = textwrap.dedent("""
    import sys
    print("booting", flush=True)
    print("Traceback (most recent call last):", flush=True)
    print('  File "x.py", line 1, in <module>', flush=True)
    print("KeyError: 'DATABASE_URL'", flush=True)
    sys.exit(1)
    """)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _init_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "server.py").write_text(FAKE_SERVER)
    (tmp_path / "crasher.py").write_text(FAKE_CRASHER)


def test_healthy_boot_end_to_end(tmp_path):
    _init_repo(tmp_path)
    port = _free_port()
    code = cap.main(
        [
            "--mode",
            "baseline",
            "--name",
            "web",
            "--type",
            "python_flask",
            "--command",
            f"{sys.executable} server.py {port}",
            "--repo-root",
            str(tmp_path),
            "--port",
            str(port),
            "--boot-timeout",
            "10",
            "--idle-seconds",
            "1",
            "--issue",
            "42",
            "--no-default-config-checks",
        ]
    )
    assert code == 0
    doc = json.loads((tmp_path / ".co-dwerker.baseline-localapp.json").read_text())
    assert doc["mode"] == "baseline" and doc["issue_number"] == 42
    app = doc["apps"][0]
    assert app["boot_status"] == "started"
    assert app["ready_signal_detected"] is True
    assert app["pid"]
    assert app["http_probes"][0]["status_code"] == 200
    assert app["idle_watch_seconds_observed"] >= 1
    assert [e["normalized"] for e in app["log_errors"]] == [
        "ERROR:app:Background timer failed (request <uuid>)"
    ]
    assert len(app["log_warnings"]) == 1
    assert (tmp_path / app["log_file"]).exists()
    exclude = (tmp_path / ".git" / "info" / "exclude").read_text()
    assert ".co-dwerker.baseline-localapp.json" in exclude
    # process group was cleaned up
    assert not cap.port_in_use(port)


def test_second_app_merges_into_same_file(tmp_path):
    _init_repo(tmp_path)
    for name in ("a", "b"):
        cap.main(
            [
                "--mode",
                "baseline",
                "--name",
                name,
                "--type",
                "custom",
                "--command",
                "true",
                "--repo-root",
                str(tmp_path),
                "--write-skipped",
            ]
        )
    doc = json.loads((tmp_path / ".co-dwerker.baseline-localapp.json").read_text())
    assert sorted(a["name"] for a in doc["apps"]) == ["a", "b"]
    assert all(a["boot_status"] == "skipped" for a in doc["apps"])


def test_crash_during_boot_is_failed_to_start(tmp_path):
    _init_repo(tmp_path)
    code = cap.main(
        [
            "--mode",
            "verify",
            "--name",
            "web",
            "--type",
            "python_generic",
            "--command",
            f"{sys.executable} crasher.py",
            "--repo-root",
            str(tmp_path),
            "--boot-timeout",
            "10",
            "--idle-seconds",
            "1",
            "--no-default-config-checks",
        ]
    )
    assert code == 2
    doc = json.loads((tmp_path / ".co-dwerker.verify-localapp.json").read_text())
    app = doc["apps"][0]
    assert app["boot_status"] == "failed_to_start"
    assert app["exit_code"] == 1
    assert len(app["log_errors"]) == 1 and app["log_errors"][0]["multiline"]
    assert app["last_output_lines"][-1] == "KeyError: 'DATABASE_URL'"


def test_silent_process_times_out(tmp_path):
    _init_repo(tmp_path)
    code = cap.main(
        [
            "--mode",
            "baseline",
            "--name",
            "quiet",
            "--type",
            "custom",
            "--command",
            f"{sys.executable} -c 'import time; time.sleep(30)'",
            "--repo-root",
            str(tmp_path),
            "--boot-timeout",
            "1",
            "--idle-seconds",
            "1",
            "--no-default-config-checks",
        ]
    )
    assert code == 2
    doc = json.loads((tmp_path / ".co-dwerker.baseline-localapp.json").read_text())
    assert doc["apps"][0]["boot_status"] == "timeout"


def test_port_conflict_is_preflight_failure(tmp_path):
    _init_repo(tmp_path)
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        code = cap.main(
            [
                "--mode",
                "baseline",
                "--name",
                "web",
                "--type",
                "custom",
                "--command",
                "true",
                "--repo-root",
                str(tmp_path),
                "--port",
                str(port),
                "--no-default-config-checks",
            ]
        )
    finally:
        holder.close()
    assert code == 3
    doc = json.loads((tmp_path / ".co-dwerker.baseline-localapp.json").read_text())
    app = doc["apps"][0]
    assert app["boot_status"] == "preflight_failed"
    assert app["preflight"]["port_checks"][0]["available"] is False
    assert app["preflight"]["failure_reasons"][0].startswith(f"port {port} in use")


def test_required_config_missing_is_preflight_failure(tmp_path):
    _init_repo(tmp_path)
    code = cap.main(
        [
            "--mode",
            "baseline",
            "--name",
            "func",
            "--type",
            "azure_functions",
            "--command",
            "true",
            "--repo-root",
            str(tmp_path),
            "--port",
            str(_free_port()),
        ]
    )
    assert code == 3
    doc = json.loads((tmp_path / ".co-dwerker.baseline-localapp.json").read_text())
    reasons = doc["apps"][0]["preflight"]["failure_reasons"]
    assert reasons == ["required config local.settings.json missing"]


def test_env_file_is_passed_to_the_app(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / ".env.local").write_text("GREETING=hello-from-env\n")
    code = cap.main(
        [
            "--mode",
            "baseline",
            "--name",
            "env",
            "--type",
            "custom",
            "--command",
            f"{sys.executable} -c \"import os; print('listening', os.environ['GREETING']); "
            'import time; time.sleep(30)"',
            "--repo-root",
            str(tmp_path),
            "--env-file",
            ".env.local",
            "--boot-timeout",
            "5",
            "--idle-seconds",
            "0.5",
            "--no-default-config-checks",
        ]
    )
    assert code == 0
    log = (tmp_path / ".co-dwerker.localapp-env-baseline.log").read_text()
    assert "hello-from-env" in log


def test_usage_error_for_missing_start_path(tmp_path):
    code = cap.main(
        [
            "--mode",
            "baseline",
            "--name",
            "x",
            "--type",
            "custom",
            "--command",
            "true",
            "--cwd",
            "nope",
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert code == 4


def test_script_is_executable_with_shebang():
    path = os.path.join(os.path.dirname(cap.__file__), "localapp_capture.py")
    assert open(path).readline().startswith("#!/usr/bin/env python3")
    assert os.access(path, os.X_OK)
