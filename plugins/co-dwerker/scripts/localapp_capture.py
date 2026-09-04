#!/usr/bin/env python3
"""Boot a local app, watch it, and record errors/warnings as JSON.

Used by co-dwerker for both the pre-implementation baseline (Step 3.1b) and the
post-implementation verification run (Step 3.5a). Running the same script for
both guarantees the two captures are normalized identically, which is what
makes the later diff meaningful.

Typical calls (from the repo root):

  localapp_capture.py --mode baseline --name api --type azure_functions --command "func start"
  localapp_capture.py --mode verify   --name api --type azure_functions --command "func start"
  localapp_capture.py --mode baseline --name web --type custom --command "make dev" --port 8080
  localapp_capture.py --mode baseline --name api --type azure_functions --command "func start" \
      --write-skipped          # user opted out at the baseline gate; records boot_status "skipped"

What it does, in order:
  1. Pre-flight: are the ports free (IPv4 and IPv6)? are required config files present?
  2. Start the command in its own process group, tee stdout+stderr to a log file.
  3. Boot detection: framework ready-signal regex, then an HTTP probe as fallback/confirmation.
  4. Idle watch (default 90 s) so slow background timers and lazy init get a chance to fail.
  5. Clean shutdown of the whole process group: SIGTERM, then SIGKILL after 10 s, and a final
     SIGKILL sweep so children outlive neither the launcher nor the capture.
  6. Classify every captured line as error / warning (multi-line tracebacks fold into one
     entry), normalize volatile fields, and write the JSON (merging into an existing file
     by app name so monorepos accumulate one entry per app).

Exit codes: 0 healthy boot · 2 boot failure (failed_to_start / timeout / crashed_during_idle)
            3 preflight_failed · 4 usage error, or the capture itself failed (nothing recorded)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Optional

SCHEMA_VERSION = 3  # bump whenever classification or normalization changes

# --------------------------------------------------------------------------------------
# Framework knowledge. Kept small on purpose — the agent picks the command; the script
# only needs enough to recognise "it's up" and to know which port to poke.
# --------------------------------------------------------------------------------------

APP_TYPES = [
    "azure_functions",
    "dotnet",
    "python_flask",
    "python_django",
    "python_fastapi",
    "python_uvicorn",
    "python_generic",
    "node",
    "docker_compose",
    "custom",
]

_GENERIC_READY = [
    r"listening on",
    r"\blistening\b",
    r"server started",
    r"ready on http",
    r"ready in \d",
    r"running on http",
    r"serving (?:http )?on",
    r"application started",
    r"startup complete",
]

READY_PATTERNS: dict[str, list[str]] = {
    "azure_functions": [
        r"Job host started",
        r"Worker process started",
        r"Host lock lease acquired",
    ],
    "dotnet": [r"Now listening on:", r"Application started"],
    "python_flask": [r"Running on http"],
    "python_django": [r"Starting development server at"],
    "python_fastapi": [
        r"Uvicorn running on",
        r"Application startup complete",
        r"Started server process",
    ],
    "python_uvicorn": [
        r"Uvicorn running on",
        r"Application startup complete",
        r"Started server process",
    ],
    "python_generic": _GENERIC_READY,
    "node": [
        r"\blistening\b",
        r"server started",
        r"ready on http",
        r"ready in \d",
        r"Local:\s+http",
    ],
    "docker_compose": _GENERIC_READY + [r"\bStarted\b", r"\bHealthy\b"],
    "custom": _GENERIC_READY,
}

DEFAULT_PORTS: dict[str, list[int]] = {
    "azure_functions": [7071],
    "python_flask": [5000],
    "python_django": [8000],
    "python_fastapi": [8000],
    "python_uvicorn": [8000],
    "node": [3000],
}

REQUIRED_CONFIG: dict[str, list[str]] = {
    # func start refuses to run without this file, so its absence is a hard preflight failure.
    "azure_functions": ["local.settings.json"],
}

OPTIONAL_CONFIG: dict[str, list[str]] = {
    "dotnet": ["appsettings.Development.json"],
    "python_flask": [".env"],
    "python_django": [".env"],
    "python_fastapi": [".env"],
    "python_uvicorn": [".env"],
    "python_generic": [".env"],
    "node": [".env", ".env.local"],
    "docker_compose": [".env"],
}

DEFAULT_PROBE_PATHS = ["/health", "/healthz", "/"]

# --------------------------------------------------------------------------------------
# Classification and normalization
# --------------------------------------------------------------------------------------

# "error"/"errors"/"err" count only as a level word: preceded by start, space, bracket, paren
# or pipe, and followed by punctuation, space, or end of line. This keeps "ERROR:app", "[error]",
# "npm ERR!" and "compiled with 2 errors" while rejecting "/api/error" and "0 Error(s)".
_LEVEL_WORD = r"(?:^|[\s\[\(|])(?:{words})(?:[:\]!\s.,;)]|$)"
ERROR_RE = re.compile(
    _LEVEL_WORD.format(words=r"errors?|errs?")
    + r"|exceptions?\b|traceback \(most recent call last\)|unhandled exception"
    r"|\bfatal\b|\bpanic:|\[critical\]|\bcritical:|^\s*fail:|^\s*crit:",
    re.IGNORECASE,
)
WARNING_RE = re.compile(
    _LEVEL_WORD.format(words=r"warnings?|warn") + r"|\bdeprecat\w*|\w+Warning\b|^\s*warn:",
    re.IGNORECASE,
)
TRACEBACK_HEADER_RE = re.compile(r"^\s*Traceback \(most recent call last\):")
PY_EXC_LINE_RE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Warning|Exit|Interrupt)\b")
DOTNET_EXC_RE = re.compile(r"^\s*(Unhandled exception|System\.[\w.]*Exception\b|[\w.]+Exception:)")
STACK_FRAME_RE = re.compile(r"^\s+at\s+\S")
PY_FRAME_RE = re.compile(r'^\s+File "')
DOTNET_LEVEL_RE = re.compile(r"^\s*(fail|crit|warn|info|dbug|trce):", re.IGNORECASE)

_STRIP_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\x1b\[[0-9;]*[a-zA-Z]"), ""),  # ANSI escape codes
    (
        re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}([.,]\d+)?(Z|[+-]\d{2}:?\d{2})?\s*"),
        "",
    ),  # ISO 8601 at line start
    (re.compile(r"^\[\d{2}/[A-Za-z]+/\d{4} \d{2}:\d{2}:\d{2}\]\s*"), ""),  # Apache/nginx style
    (re.compile(r"^\[\d{2}:\d{2}:\d{2}(?:\.\d+)?\]\s*"), ""),  # short time
    (
        re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        ),
        "<uuid>",
    ),
    (re.compile(r"\b[0-9a-fA-F]{16,}\b"), "<hex>"),  # long hex ids / hashes
    (re.compile(r"\bPID[: ]?\d+\b"), "PID <pid>"),
    (re.compile(r"\bpid=\d+\b"), "pid=<pid>"),
    (re.compile(r"\[\d+\](?=\s)"), "[<pid>]"),
    (re.compile(r"(?<=[\w\]]):(\d{4,5})\b"), ":<port>"),  # ports after a host or ://host
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (re.compile(r"\s+"), " "),  # whitespace collapse
]


def normalize(text: str) -> str:
    """Strip volatile fields so identical events match across two separate boots."""
    out = text
    for pattern, repl in _STRIP_PATTERNS:
        out = pattern.sub(repl, out)
    return out.strip()


def classify_line(text: str) -> Optional[str]:
    """Return 'error', 'warning', or None for a single line. Errors win ties."""
    if ERROR_RE.search(text):
        return "error"
    if WARNING_RE.search(text):
        return "warning"
    return None


def _indented(line: str) -> bool:
    return line[:1] in (" ", "\t")


def _frame_like(line: str) -> bool:
    return bool(STACK_FRAME_RE.match(line) or PY_FRAME_RE.match(line))


def _block_key(block: list[tuple[float, str]]) -> str:
    """Diff key for an entry: header line plus the final non-frame line.

    Stack frames carry line numbers that shift with unrelated edits, so they are left out of
    the key; the exception type/message at the start and end is what identifies the event.
    """
    first = block[0][1]
    if len(block) == 1:
        return normalize(first)
    last = block[-1][1]
    if last != first and not _frame_like(last) and normalize(last):
        return normalize(first) + " | " + normalize(last)
    return normalize(first)


def classify_lines(
    lines: list[tuple[float, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fold multi-line entries (tracebacks, .NET exceptions, ASP.NET level blocks) and classify.

    ``lines`` is a list of ``(offset_seconds, text)`` in output order.
    Returns ``(errors, warnings)``, each a list of entry dicts.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    n = len(lines)
    i = 0

    def entry(kind: str, block: list[tuple[float, str]]) -> dict[str, Any]:
        rec = {
            "captured_at_offset_seconds": round(block[0][0], 1),
            "raw": "\n".join(t for _, t in block),
            "normalized": _block_key(block),
            "multiline": len(block) > 1,
        }
        if rec["multiline"]:
            rec["line_count"] = len(block)
        (errors if kind == "error" else warnings).append(rec)
        return rec

    open_frames: Optional[dict[str, Any]] = None  # error entry that may still gain "at ..." frames
    while i < n:
        off, text = lines[i]
        if TRACEBACK_HEADER_RE.match(text):
            block = [lines[i]]
            i += 1
            while i < n and _indented(lines[i][1]):
                block.append(lines[i])
                i += 1
            if i < n and PY_EXC_LINE_RE.match(lines[i][1]):
                block.append(lines[i])
                i += 1
            entry("error", block)
            open_frames = None
            continue
        if DOTNET_EXC_RE.match(text):
            block = [lines[i]]
            i += 1
            while i < n and (_indented(lines[i][1]) or lines[i][1].lstrip().startswith("--->")):
                block.append(lines[i])
                i += 1
            entry("error", block)
            open_frames = None
            continue
        level = DOTNET_LEVEL_RE.match(text)
        if level and level.group(1).lower() in ("fail", "crit", "warn"):
            block = [lines[i]]
            i += 1
            while i < n and _indented(lines[i][1]) and not DOTNET_LEVEL_RE.match(lines[i][1]):
                block.append(lines[i])
                i += 1
            entry("error" if level.group(1).lower() != "warn" else "warning", block)
            open_frames = None
            continue
        if STACK_FRAME_RE.match(text) and open_frames is not None:
            open_frames["raw"] += "\n" + text
            open_frames["multiline"] = True
            open_frames["line_count"] = open_frames.get("line_count", 1) + 1
            i += 1
            continue
        kind = classify_line(text)
        if kind:
            rec = entry(kind, [lines[i]])
            open_frames = rec if (kind == "error" and "exception" in text.lower()) else None
        elif text.strip():
            open_frames = None
        i += 1

    return errors, warnings


# --------------------------------------------------------------------------------------
# Environment helpers
# --------------------------------------------------------------------------------------


class UsageError(Exception):
    """Bad arguments or a capture that could not run; exit code 4."""


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _git(args: list[str], cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def ensure_git_exclude(repo_root: str, patterns: list[str]) -> None:
    """Add patterns to the clone-local exclude file so intermediate commits never pick them up.

    Uses ``git rev-parse --git-path``, which resolves to the clone's shared info/exclude
    from the main checkout and from any linked worktree alike. Housekeeping only: any
    failure is reported, never fatal.
    """
    exclude_path = _git(["rev-parse", "--git-path", "info/exclude"], repo_root)
    if not exclude_path:
        return
    if not os.path.isabs(exclude_path):
        exclude_path = os.path.join(repo_root, exclude_path)
    try:
        existing_text = ""
        if os.path.exists(exclude_path):
            with open(exclude_path, encoding="utf-8") as fh:
                existing_text = fh.read()
        existing = {ln.strip() for ln in existing_text.splitlines()}
        missing = [p for p in patterns if p not in existing]
        if not missing:
            return
        os.makedirs(os.path.dirname(exclude_path), exist_ok=True)
        with open(exclude_path, "a", encoding="utf-8") as fh:
            if existing_text and not existing_text.endswith("\n"):
                fh.write("\n")
            for p in missing:
                fh.write(p + "\n")
    except OSError as exc:
        print(f"localapp_capture: note — could not update {exclude_path}: {exc}", file=sys.stderr)


def parse_env_file(path: str) -> dict[str, str]:
    """Minimal KEY=VALUE parser (comments, blanks, optional quotes, optional ``export``)."""
    env: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            env[key.strip()] = value
    return env


def port_in_use(port: int) -> bool:
    """True if anything accepts connections on the port over IPv4 or IPv6 loopback."""
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def port_holder(port: int) -> Optional[dict[str, Any]]:
    """Best-effort: who is listening on the port (macOS/Linux with lsof)."""
    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpcu"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    info: dict[str, Any] = {}
    for token in out.split():
        if token.startswith("p") and "pid" not in info and token[1:].isdigit():
            info["pid"] = int(token[1:])
        elif token.startswith("c") and "command" not in info:
            info["command"] = token[1:]
        elif token.startswith("u") and "user" not in info:
            info["user"] = token[1:]
    if "pid" in info:
        try:
            started = subprocess.run(
                ["ps", "-p", str(info["pid"]), "-o", "lstart="],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            ).stdout.strip()
            if started:
                info["started"] = started
        except (OSError, subprocess.TimeoutExpired):
            pass
    return info or None


def http_probe(port: int, path: str, timeout: float = 3.0) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}{path}"
    started = time.monotonic()
    rec: dict[str, Any] = {"endpoint": path, "port": port, "method": "GET"}
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - local only
            rec["status_code"] = resp.status
    except urllib.error.HTTPError as exc:
        rec["status_code"] = exc.code
    except (urllib.error.URLError, OSError, ValueError) as exc:
        rec["status_code"] = None
        rec["error"] = str(getattr(exc, "reason", exc))[:200]
    rec["duration_ms"] = int((time.monotonic() - started) * 1000)
    return rec


PORT_IN_OUTPUT_RE = re.compile(r"https?://(?:\[[^\]]*\]|[\w.\-]+):(\d{2,5})")


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.-]", "_", name) or "app"


# --------------------------------------------------------------------------------------
# Process runner
# --------------------------------------------------------------------------------------


class ProcessWatcher:
    """Runs the command in its own process group and collects timestamped output lines."""

    def __init__(self, command: str, cwd: str, env: dict[str, str], log_path: str) -> None:
        self.command = command
        self.cwd = cwd
        self.env = env
        self.log_path = log_path
        self.lines: list[tuple[float, str]] = []
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self.proc: Optional[subprocess.Popen[str]] = None
        self.pgid: Optional[int] = None
        self.reader_error: Optional[str] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        popen_kwargs: dict[str, Any] = dict(
            shell=True,
            cwd=self.cwd,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        else:  # pragma: no cover - windows
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self._start = time.monotonic()
        self.proc = subprocess.Popen(
            self.command, **popen_kwargs
        )  # noqa: S602 - agent-chosen command
        # start_new_session makes the child its own group leader, so the pgid is its pid.
        self.pgid = self.proc.pid if os.name == "posix" else None
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        try:
            with open(self.log_path, "w", encoding="utf-8") as log:
                for raw in self.proc.stdout:
                    text = raw.rstrip("\r\n")
                    offset = time.monotonic() - self._start
                    log.write(f"[{offset:8.2f}] {text}\n")
                    log.flush()
                    with self._lock:
                        self.lines.append((offset, text))
        except Exception as exc:  # noqa: BLE001 - surfaced as capture_error, never silent
            self.reader_error = f"{type(exc).__name__}: {exc}"

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def snapshot(self) -> list[tuple[float, str]]:
        with self._lock:
            return list(self.lines)

    def exit_code(self) -> Optional[int]:
        return self.proc.poll() if self.proc else None

    def _signal_group(self, sig: int) -> None:
        if self.pgid is None:
            return
        try:
            os.killpg(self.pgid, sig)
        except OSError:  # group already gone, or not permitted
            pass

    def shutdown(self, grace_seconds: float = 10.0) -> None:
        """Stop the whole process group, then drain the reader.

        Always sweeps the group, even when the direct child has already exited: a launcher
        (``npm start``, a wrapper script) can die and leave the real server running.
        """
        if self.proc is not None:
            if self.proc.poll() is None:
                if os.name == "posix":
                    self._signal_group(signal.SIGTERM)
                else:  # pragma: no cover - windows
                    self.proc.terminate()
                deadline = time.monotonic() + grace_seconds
                while time.monotonic() < deadline and self.proc.poll() is None:
                    time.sleep(0.2)
            if os.name == "posix":
                self._signal_group(signal.SIGKILL)
            elif self.proc.poll() is None:  # pragma: no cover - windows
                self.proc.kill()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if self._thread:
            self._thread.join(timeout=5)
        if self.proc is not None and self.proc.stdout:
            try:
                self.proc.stdout.close()
            except OSError:
                pass


# --------------------------------------------------------------------------------------
# Capture orchestration
# --------------------------------------------------------------------------------------

HEALTHY = {"started", "started_no_signal"}
FAILED = {"failed_to_start", "timeout", "crashed_during_idle", "preflight_failed"}


def run_capture(args: argparse.Namespace) -> dict[str, Any]:
    if args.max_seconds is None:
        args.max_seconds = args.boot_timeout + args.idle_seconds + 30
    repo_root = os.path.abspath(args.repo_root)
    start_path = os.path.abspath(os.path.join(repo_root, args.cwd))
    log_name = f".co-dwerker.localapp-{_safe_name(args.name)}-{args.mode}.log"
    log_path = os.path.join(repo_root, log_name)

    app: dict[str, Any] = {
        "name": args.name,
        "type": args.type,
        "mode": args.mode,
        "captured_at": _now_iso(),
        "issue_number": args.issue,
        "command": args.command,
        "start_path": os.path.relpath(start_path, repo_root),
        "pid": None,
        "pgid": None,
        "boot_status": None,
        "boot_duration_seconds": None,
        "ready_signal_detected": False,
        "ready_signal_match": None,
        "preflight": {"port_checks": [], "config_checks": []},
        "http_probes": [],
        "log_errors": [],
        "log_warnings": [],
        "idle_watch_seconds_observed": 0,
        "exit_code": None,
        "terminated_by_capture": False,
        "log_file": log_name,
    }

    if args.write_skipped:
        app["boot_status"] = "skipped"
        return app

    ports = list(args.port or DEFAULT_PORTS.get(args.type, []))
    required = list(args.required_config or []) + (
        REQUIRED_CONFIG.get(args.type, []) if not args.no_default_config_checks else []
    )
    optional = list(args.config_check or []) + (
        OPTIONAL_CONFIG.get(args.type, []) if not args.no_default_config_checks else []
    )

    # ---- validate inputs that would otherwise fail mid-capture -------------------------
    try:
        ready_patterns = [
            re.compile(p, re.IGNORECASE) for p in (args.ready_pattern or READY_PATTERNS[args.type])
        ]
    except re.error as exc:
        raise UsageError(f"bad --ready-pattern: {exc}") from exc
    env_files = []
    for path in args.env_file or []:
        full = path if os.path.isabs(path) else os.path.join(start_path, path)
        if not os.path.isfile(full):
            raise UsageError(f"--env-file {path} not found (looked in {start_path})")
        env_files.append(full)

    # ---- pre-flight -------------------------------------------------------------------
    preflight_failed_reasons: list[str] = []
    for port in ports:
        busy = port_in_use(port)
        check: dict[str, Any] = {"port": port, "available": not busy}
        if busy:
            holder = port_holder(port)
            if holder:
                check["holder"] = holder
            preflight_failed_reasons.append(
                f"port {port} in use"
                + (f" by PID {holder['pid']} ({holder.get('command')})" if holder else "")
            )
        app["preflight"]["port_checks"].append(check)
    for rel in required:
        present = os.path.exists(os.path.join(start_path, rel))
        app["preflight"]["config_checks"].append(
            {"file": rel, "present": present, "required": True}
        )
        if not present:
            preflight_failed_reasons.append(f"required config {rel} missing")
    for rel in optional:
        present = os.path.exists(os.path.join(start_path, rel))
        app["preflight"]["config_checks"].append(
            {"file": rel, "present": present, "required": False}
        )

    if preflight_failed_reasons:
        app["boot_status"] = "preflight_failed"
        app["preflight"]["failure_reasons"] = preflight_failed_reasons
        return app

    # ---- environment ------------------------------------------------------------------
    env = dict(os.environ)
    # Piped stdout is block-buffered in Python; without this a Flask/uvicorn app's ready line
    # can sit in a buffer past the boot timeout. Harmless for non-Python apps.
    env.setdefault("PYTHONUNBUFFERED", "1")
    for full in env_files:
        env.update(parse_env_file(full))
    for item in args.env or []:
        if "=" in item:
            k, v = item.split("=", 1)
            env[k] = v

    # ---- boot -------------------------------------------------------------------------
    watcher = ProcessWatcher(args.command, start_path, env, log_path)
    watcher.start()
    app["pid"] = watcher.proc.pid if watcher.proc else None
    app["pgid"] = watcher.pgid

    ready_at: Optional[float] = None
    seen = 0
    boot_deadline = time.monotonic() + args.boot_timeout
    hard_deadline = time.monotonic() + args.max_seconds
    while time.monotonic() < boot_deadline:
        snapshot = watcher.snapshot()
        for off, text in snapshot[seen:]:
            for pat in ready_patterns:
                if pat.search(text):
                    ready_at, app["ready_signal_match"] = off, pat.pattern
                    break
            if not args.port:
                for m in PORT_IN_OUTPUT_RE.finditer(text):
                    p = int(m.group(1))
                    if p not in ports:
                        ports.append(p)
            if ready_at is not None:
                break
        seen = len(snapshot)
        if ready_at is not None:
            break
        code = watcher.exit_code()
        if code is not None:
            app["exit_code"] = code
            app["boot_status"] = "failed_to_start"
            break
        time.sleep(0.25)

    if ready_at is not None:
        app["ready_signal_detected"] = True
        app["boot_duration_seconds"] = round(ready_at, 1)
        app["boot_status"] = "started"

    # ---- probe (confirmation after signal, fallback without one) ----------------------
    if app["boot_status"] in (None, "started") and watcher.exit_code() is None:
        probe_paths = list(args.probe or DEFAULT_PROBE_PATHS)
        probe_ok = False
        for port in ports:
            for path in probe_paths:
                rec = http_probe(port, path)
                app["http_probes"].append(rec)
                if rec.get("status_code") is not None and rec["status_code"] < 500:
                    probe_ok = True
                    break
            if probe_ok:
                break
        if app["boot_status"] is None:
            if probe_ok:
                app["boot_status"] = "started_no_signal"
                app["boot_duration_seconds"] = round(watcher.elapsed(), 1)
            else:
                app["boot_status"] = "timeout"
    elif app["boot_status"] is None:
        # Process died between the boot loop and the probe.
        app["exit_code"] = watcher.exit_code()
        app["boot_status"] = "failed_to_start"

    # ---- idle watch -------------------------------------------------------------------
    if app["boot_status"] in HEALTHY:
        idle_start = time.monotonic()
        idle_deadline = min(idle_start + args.idle_seconds, hard_deadline)
        while time.monotonic() < idle_deadline:
            code = watcher.exit_code()
            if code is not None:
                app["exit_code"] = code
                app["boot_status"] = "crashed_during_idle"
                break
            time.sleep(0.5)
        app["idle_watch_seconds_observed"] = round(time.monotonic() - idle_start, 1)
        if app["boot_status"] in HEALTHY and time.monotonic() >= hard_deadline:
            app["note"] = "max_seconds reached before the idle window completed"

    # ---- shutdown + classify ----------------------------------------------------------
    still_running = watcher.exit_code() is None
    watcher.shutdown()
    if still_running:
        app["terminated_by_capture"] = True  # any exit code now is our own signal, not the app's
    elif app["exit_code"] is None:
        app["exit_code"] = watcher.exit_code()
    if watcher.reader_error:
        app["capture_error"] = watcher.reader_error
    all_lines = watcher.snapshot()
    errors, warnings = classify_lines(all_lines)
    app["log_errors"] = errors
    app["log_warnings"] = warnings
    if app["boot_status"] in FAILED:
        app["last_output_lines"] = [t for _, t in all_lines[-50:]]
    return app


def merge_and_write(args: argparse.Namespace, app: dict[str, Any]) -> str:
    repo_root = os.path.abspath(args.repo_root)
    out_name = args.out or (
        ".co-dwerker.baseline-localapp.json"
        if args.mode == "baseline"
        else ".co-dwerker.verify-localapp.json"
    )
    out_path = out_name if os.path.isabs(out_name) else os.path.join(repo_root, out_name)

    doc: dict[str, Any] = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (json.JSONDecodeError, OSError):
            doc = {}
    doc.update(
        {
            "schema_version": SCHEMA_VERSION,
            "mode": args.mode,
            "captured_at": _now_iso(),
            "branch": _git(["branch", "--show-current"], repo_root) or None,
            "commit": _git(["rev-parse", "HEAD"], repo_root) or None,
            "issue_number": args.issue,
            "boot_timeout_seconds": args.boot_timeout,
            "idle_seconds": args.idle_seconds,
        }
    )
    kept: list[dict[str, Any]] = []
    for a in doc.get("apps", []):
        if not isinstance(a, dict) or a.get("name") == app["name"]:
            continue
        # Entries from a different issue are stale leftovers; a fresh issue starts clean.
        if args.issue is not None and a.get("issue_number") not in (None, args.issue):
            continue
        kept.append(a)
    kept.append(app)
    doc["apps"] = kept
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, out_path)
    # Housekeeping after the result is safely on disk.
    ensure_git_exclude(
        repo_root,
        [
            os.path.basename(out_path),
            ".co-dwerker.localapp-*.log",
            ".co-dwerker.localapp-diff.json",
        ],
    )
    return os.path.relpath(out_path, repo_root)


def _unique(entries: list[dict[str, Any]]) -> int:
    return len({e["normalized"] for e in entries})


def print_summary(app: dict[str, Any], out_rel: str) -> None:
    print(f"[co-dwerker localapp] mode={app['mode']} app={app['name']} type={app['type']}")
    print(f"  command: {app['command']}  (cwd {app['start_path']})")
    status = app["boot_status"]
    if app.get("capture_error"):
        print(f"  CAPTURE FAILED: {app['capture_error']} — no output was recorded")
    if status == "skipped":
        print("  boot_status: skipped (user opted out; recorded for the diff step)")
    elif status == "preflight_failed":
        print("  boot_status: preflight_failed")
        for reason in app["preflight"].get("failure_reasons", []):
            print(f"    - {reason}")
    else:
        extra = ""
        if app["boot_duration_seconds"] is not None:
            extra = f" after {app['boot_duration_seconds']}s"
        if app["ready_signal_match"]:
            extra += f", ready signal /{app['ready_signal_match']}/"
        if app["exit_code"] is not None and not app.get("terminated_by_capture"):
            extra += f", exit code {app['exit_code']}"
        print(f"  boot_status: {status}{extra}")
        print(f"  pid: {app['pid']}  pgid: {app['pgid']}")
        for p in app["http_probes"]:
            code = p.get("status_code")
            shown = code if code is not None else f"no response ({p.get('error', '')})"
            print(f"  probe: GET :{p['port']}{p['endpoint']} -> {shown} ({p['duration_ms']}ms)")
        print(f"  idle watch: {app['idle_watch_seconds_observed']}s observed")
        print(
            f"  errors: {len(app['log_errors'])} ({_unique(app['log_errors'])} unique)   "
            f"warnings: {len(app['log_warnings'])} ({_unique(app['log_warnings'])} unique)"
        )
        for e in app["log_errors"][:3]:
            first = e["raw"].splitlines()[0]
            print(f"    error: {first[:160]}")
        if status in FAILED and app.get("last_output_lines"):
            print("  last output lines:")
            for t in app["last_output_lines"][-8:]:
                print(f"    | {t[:160]}")
    print(f"  wrote: {out_rel}  log: {app['log_file']}")
    print(f"RESULT: {'capture_failed' if app.get('capture_error') else status}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mode", required=True, choices=["baseline", "verify"])
    parser.add_argument("--name", required=True, help="app name; monorepos use one name per app")
    parser.add_argument("--type", required=True, choices=APP_TYPES)
    parser.add_argument("--command", required=True, help="shell command that starts the app")
    parser.add_argument(
        "--cwd", default=".", help="directory to run the command in, relative to --repo-root"
    )
    parser.add_argument(
        "--repo-root", default=".", help="repo root where the JSON is written (default: cwd)"
    )
    parser.add_argument("--port", type=int, action="append", help="port(s) to pre-flight and probe")
    parser.add_argument(
        "--ready-pattern", action="append", help="regex that means 'booted' (overrides defaults)"
    )
    parser.add_argument(
        "--probe", action="append", help="HTTP path(s) to probe (default /health, /healthz, /)"
    )
    parser.add_argument(
        "--required-config", action="append", help="file whose absence is a preflight failure"
    )
    parser.add_argument(
        "--config-check", action="append", help="file whose presence is recorded only"
    )
    parser.add_argument("--no-default-config-checks", action="store_true")
    parser.add_argument("--env", action="append", metavar="KEY=VALUE")
    parser.add_argument(
        "--env-file", action="append", help="KEY=VALUE file to load into the app's environment"
    )
    parser.add_argument("--boot-timeout", type=float, default=60.0)
    parser.add_argument("--idle-seconds", type=float, default=90.0)
    parser.add_argument(
        "--max-seconds", type=float, default=None, help="hard cap (default boot+idle+30)"
    )
    parser.add_argument("--issue", type=int, default=None)
    parser.add_argument("--out", help="output JSON path (default depends on --mode)")
    parser.add_argument(
        "--write-skipped", action="store_true", help="record boot_status 'skipped' without running"
    )
    parser.add_argument(
        "--json", action="store_true", help="print the app entry as JSON instead of the summary"
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    try:
        if not shlex.split(args.command):
            raise UsageError("--command is empty")
    except ValueError as exc:
        raise UsageError(f"--command is not valid shell syntax: {exc}") from exc
    start_path = os.path.abspath(os.path.join(args.repo_root, args.cwd))
    if not os.path.isdir(start_path):
        raise UsageError(f"start path {start_path} does not exist")
    app = run_capture(args)
    out_rel = merge_and_write(args, app)
    if args.json:
        print(json.dumps(app, indent=2))
    else:
        print_summary(app, out_rel)
    if app.get("capture_error"):
        return 4
    status = app["boot_status"]
    if status in HEALTHY or status == "skipped":
        return 0
    if status == "preflight_failed":
        return 3
    return 2


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except UsageError as exc:
        print(f"localapp_capture: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:  # noqa: BLE001 - a crash must never look like a boot verdict
        print(f"localapp_capture: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
