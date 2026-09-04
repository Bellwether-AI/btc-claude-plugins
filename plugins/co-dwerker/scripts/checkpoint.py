#!/usr/bin/env python3
"""Progress checkpoints for co-dwerker sessions.

Writes a ``progress`` block into ``.co-dwerker.state.json`` so that step
completion survives context compaction, crashes, and harnesses where no
task/todo tool is available. Replaces the v0.3.x ``TaskCreate`` step tracking.

The state file always lives in the MAIN checkout of the repository. When run
from a linked worktree the script resolves that location itself (via
``git rev-parse --git-common-dir``), so the same file is updated no matter
which worktree the session is in. Pass ``--state-file`` only to override.
The file is added to the clone's ``.git/info/exclude`` automatically, so it
never needs a ``.gitignore`` entry and never shows up in ``git status``.

Usage (invoke as ``python3 <plugin>/scripts/checkpoint.py ...``):

  checkpoint.py start-issue 42 --phase 2 --set work_mode=repo
  checkpoint.py mark 3.1 in_progress
  checkpoint.py mark 3.1 completed --set baseline_tests_file=.co-dwerker.baseline-tests.json
  checkpoint.py set --set pr_number=57 --append local_app_pids=12345
  checkpoint.py set --top repo_owner_name=owner/repo        # top-level key, not progress.context
  checkpoint.py gate 3          # exit 0 if every phase-3 step is completed, else 1 + missing
  checkpoint.py show            # progress block + last_session summary
  checkpoint.py finish-issue    # record completion and clear the per-issue progress
  checkpoint.py end-session --repo-owner-name owner/repo --prs-created 57 --prs-merged 57

``progress.status`` is the ISSUE status: ``in_progress`` from ``start-issue``
until ``finish-issue`` sets ``completed``. ``progress.step_status`` is the
status of the most recent ``mark``.

Step ids are ``<phase>.<step>`` and mirror the headings in skills/work/SKILL.md.
Unknown step ids are accepted (with a note) so SKILL.md edits never break the
script; ``gate`` only checks the steps it knows about for that phase.

Exit codes: 0 ok · 1 gate blocked · 2 usage or state-file error
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from typing import Any

STATE_FILE_NAME = ".co-dwerker.state.json"
GLOBAL_STATE_FILE = os.path.join(os.path.expanduser("~"), ".claude", "co-dwerker-last-repo.json")
GLOBAL_STATE_FILE_LEGACY = os.path.join(os.path.expanduser("~"), ".co-dwerker-last-repo.json")

# Phase -> ordered step ids. Keep in sync with skills/work/SKILL.md headings.
PHASES: dict[str, list[str]] = {
    "0a": ["mode"],
    "0b": ["project", "fields"],
    "1": ["fetch", "report", "recommend"],
    "2": ["load", "brainstorm", "board", "discovered"],
    "3": ["1", "1b", "2", "3", "4", "5", "5a", "6", "7", "8"],
    "4": ["docs"],
    "5": ["merge", "ci", "docs-merge", "close-issue", "board", "cleanup"],
    "6": ["progress", "queue"],
}

# Session-level context keys (not per-issue); they survive start-issue and finish-issue.
SESSION_KEYS = {
    "work_mode",
    "main_checkout",
    "planned_issues",
    "issues_created",
    "labels_verified",
    "project_number",
    "project_title",
    "project_id",
    "status_field_id",
    "status_options",
    "priority_field_id",
    "priority_options",
    "local_app_pids",
}


class CheckpointError(Exception):
    """Usage or state-file problem; reported on stderr with exit code 2."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _today() -> str:
    return _dt.date.today().isoformat()


def _git(args: list[str], cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def main_checkout(start: str = ".") -> str:
    """Absolute path of the main checkout, from the main checkout or any linked worktree."""
    common = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"], start)
    if not common:
        # Older git without --path-format: plain --git-common-dir may be relative.
        common = _git(["rev-parse", "--git-common-dir"], start)
        if not common:
            return os.path.abspath(start)
        common = os.path.abspath(os.path.join(start, common))
    return os.path.dirname(common)


def default_state_file() -> str:
    return os.path.join(main_checkout(), STATE_FILE_NAME)


def ensure_excluded(path: str) -> None:
    """Add the state file to the clone's shared info/exclude (best effort, never fatal)."""
    repo_dir = os.path.dirname(os.path.abspath(path)) or "."
    exclude = _git(["rev-parse", "--git-path", "info/exclude"], repo_dir)
    if not exclude:
        return
    if not os.path.isabs(exclude):
        exclude = os.path.join(repo_dir, exclude)
    name = os.path.basename(path)
    try:
        text = ""
        if os.path.exists(exclude):
            with open(exclude, encoding="utf-8") as fh:
                text = fh.read()
        if name in (ln.strip() for ln in text.splitlines()):
            return
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as fh:
            if text and not text.endswith("\n"):
                fh.write("\n")  # never glue our line onto an existing rule
            fh.write(name + "\n")
    except OSError as exc:
        print(f"checkpoint: note — could not update {exclude}: {exc}", file=sys.stderr)


def _load(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = fh.read().strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CheckpointError(
            f"{path} is not valid JSON ({exc}); refusing to overwrite it"
        ) from exc
    if not isinstance(data, dict):
        raise CheckpointError(f"{path} must contain a JSON object")
    return data


def _save(path: str, data: dict[str, Any]) -> None:
    creating = not os.path.exists(path)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, allow_nan=False)
        fh.write("\n")
    os.replace(tmp, path)
    if creating:
        ensure_excluded(path)


def _parse_value(text: str) -> Any:
    """Parse ``key=value`` values as JSON when possible, else keep the string."""

    def _reject(_: str) -> Any:
        raise ValueError("NaN/Infinity are not valid JSON")

    try:
        return json.loads(text, parse_constant=_reject)
    except ValueError:
        return text


def _split_kv(item: str) -> tuple[str, Any]:
    if "=" not in item:
        raise CheckpointError(f"expected key=value, got {item!r}")
    key, value = item.split("=", 1)
    return key.strip(), _parse_value(value)


def _progress(data: dict[str, Any]) -> dict[str, Any]:
    prog = data.get("progress")
    if not isinstance(prog, dict):
        prog = {}
        data["progress"] = prog
    prog.setdefault("issue", None)
    prog.setdefault("phase", None)
    prog.setdefault("step", None)
    prog.setdefault("status", None)
    prog.setdefault("step_status", None)
    prog.setdefault("completed_steps", [])
    prog.setdefault("context", {})
    return prog


def _apply_context(
    prog: dict[str, Any], sets: list[str], appends: list[str], clears: list[str]
) -> None:
    ctx = prog["context"]
    for item in sets:
        key, value = _split_kv(item)
        ctx[key] = value
    for item in appends:
        key, value = _split_kv(item)
        current = ctx.get(key)
        if current is None:
            ctx[key] = [value]
        elif isinstance(current, list):
            if value not in current:
                current.append(value)
        else:
            raise CheckpointError(f"cannot append to non-list context key {key!r}")
    for key in clears:
        ctx.pop(key, None)


def _apply_top(data: dict[str, Any], tops: list[str]) -> None:
    for item in tops:
        key, value = _split_kv(item)
        if key == "progress":
            raise CheckpointError("use mark/set to change progress, not --top")
        data[key] = value


def _split_step(step_id: str) -> tuple[str, str]:
    if "." not in step_id:
        raise CheckpointError(f"step id must look like <phase>.<step> (got {step_id!r})")
    phase, step = step_id.split(".", 1)
    if not phase or not step:
        raise CheckpointError(f"step id must look like <phase>.<step> (got {step_id!r})")
    return phase, step


def _keep_session_context(prog: dict[str, Any]) -> None:
    prog["context"] = {k: v for k, v in prog["context"].items() if k in SESSION_KEYS}


def cmd_start_issue(args: argparse.Namespace) -> int:
    data = _load(args.state_file)
    prog = _progress(data)
    prog.update(
        {
            "issue": args.issue,
            "phase": args.phase,
            "step": None,
            "status": "in_progress",
            "step_status": None,
            "started_at": _now(),
            "updated_at": _now(),
            "completed_steps": [],
        }
    )
    _keep_session_context(prog)
    prog["context"].setdefault("main_checkout", os.path.dirname(os.path.abspath(args.state_file)))
    _apply_context(prog, args.set or [], args.append or [], [])
    _save(args.state_file, data)
    ensure_excluded(args.state_file)
    print(f"checkpoint: started issue #{args.issue} at phase {args.phase}")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    data = _load(args.state_file)
    prog = _progress(data)
    phase, step = _split_step(args.step_id)
    if step not in PHASES.get(phase, []):
        print(
            f"checkpoint: note — {args.step_id} is not in the built-in step manifest",
            file=sys.stderr,
        )
    prog["phase"] = phase
    prog["step"] = args.step_id
    prog["step_status"] = args.status
    if prog.get("issue") is not None and prog.get("status") != "in_progress":
        prog["status"] = "in_progress"
    prog["updated_at"] = _now()
    if args.status == "completed" and args.step_id not in prog["completed_steps"]:
        prog["completed_steps"].append(args.step_id)
    if args.status == "in_progress" and args.step_id in prog["completed_steps"]:
        # Re-running a step (e.g. Step 3.5a after a fix) reopens it.
        prog["completed_steps"].remove(args.step_id)
    _apply_context(prog, args.set or [], args.append or [], args.clear or [])
    _save(args.state_file, data)
    print(f"checkpoint: {args.step_id} -> {args.status}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    data = _load(args.state_file)
    prog = _progress(data)
    if args.phase:
        prog["phase"] = args.phase
    if args.issue is not None:
        prog["issue"] = args.issue
    _apply_context(prog, args.set or [], args.append or [], args.clear or [])
    _apply_top(data, args.top or [])
    prog["updated_at"] = _now()
    _save(args.state_file, data)
    print("checkpoint: state updated")
    return 0


def _missing(prog: dict[str, Any], phase: str) -> list[str]:
    expected = [f"{phase}.{s}" for s in PHASES.get(phase, [])]
    done = set(prog.get("completed_steps", []))
    return [s for s in expected if s not in done]


def cmd_gate(args: argparse.Namespace) -> int:
    data = _load(args.state_file)
    prog = _progress(data)
    if args.phase not in PHASES:
        raise CheckpointError(f"unknown phase {args.phase!r}; known: {', '.join(PHASES)}")
    missing = _missing(prog, args.phase)
    skipped = set(args.skip or [])
    missing = [m for m in missing if m not in skipped and m.split(".", 1)[1] not in skipped]
    if missing:
        print(f"GATE BLOCKED for phase {args.phase}. Steps not completed: {', '.join(missing)}")
        print("Go back and finish them (or pass --skip <step> for steps that do not apply).")
        return 1
    print(f"GATE OPEN for phase {args.phase}: all tracked steps completed.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    data = _load(args.state_file)
    print(f"state file: {args.state_file}")
    prog = data.get("progress")
    if not prog:
        print("progress: none")
    else:
        print("progress:")
        print(json.dumps(prog, indent=2))
        phase = args.phase or prog.get("phase")
        if phase in PHASES:
            missing = _missing(prog, phase)
            print(
                f"phase {phase}: "
                + (
                    "all tracked steps completed"
                    if not missing
                    else "missing " + ", ".join(missing)
                )
            )
    if data.get("completed_this_session"):
        print(f"completed_this_session: {data['completed_this_session']}")
    last = data.get("last_session")
    if isinstance(last, dict):
        print("last_session:")
        print(json.dumps(last, indent=2))
    for key in ("work_mode", "repo_owner_name", "repo_local_path", "github_project_number"):
        if key in data:
            print(f"{key}: {data[key]}")
    return 0


def cmd_finish_issue(args: argparse.Namespace) -> int:
    data = _load(args.state_file)
    prog = _progress(data)
    issue = prog.get("issue")
    history = data.setdefault("completed_this_session", [])
    if issue is not None and issue not in history:
        history.append(issue)
    planned = prog["context"].get("planned_issues")
    if isinstance(planned, list) and issue in planned:
        planned.remove(issue)
    prog.update(
        {
            "issue": None,
            "phase": "6",
            "step": None,
            "status": "completed",
            "step_status": None,
            "updated_at": _now(),
        }
    )
    prog["completed_steps"] = []
    _keep_session_context(prog)
    _save(args.state_file, data)
    print(f"checkpoint: issue #{issue} recorded as completed; progress cleared")
    return 0


def _int_list(text: str | None) -> list[int]:
    if not text:
        return []
    out: list[int] = []
    for part in text.split(","):
        part = part.strip().lstrip("#")
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError as exc:
            raise CheckpointError(
                f"expected a comma-separated list of numbers, got {text!r}"
            ) from exc
    return out


def cmd_end_session(args: argparse.Namespace) -> int:
    """Write last_session + top-level keys from progress, and the global last-repo file."""
    data = _load(args.state_file)
    prog = _progress(data)
    ctx = prog["context"]
    repo_root = os.path.dirname(os.path.abspath(args.state_file))
    completed = list(data.get("completed_this_session", []))
    for n in _int_list(args.completed):
        if n not in completed:
            completed.append(n)
    active = prog.get("issue") is not None
    data["last_session"] = {
        "date": args.date or _today(),
        "completed_issues": completed,
        "current_issue": prog.get("issue"),
        "current_phase": prog.get("phase") if active else None,
        "current_step": prog.get("step") if active else None,
        "branch": ctx.get("branch"),
        "worktree": ctx.get("worktree"),
        "prs_created": _int_list(args.prs_created),
        "prs_merged": _int_list(args.prs_merged),
        "issues_created": list(ctx.get("issues_created", [])),
        "local_app_pids": list(ctx.get("local_app_pids", [])),
        "local_app_skip_reason": ctx.get("local_app_skip_reason"),
    }
    data["work_mode"] = ctx.get("work_mode", data.get("work_mode"))
    data["repo_local_path"] = ctx.get("main_checkout", repo_root)
    if args.repo_owner_name:
        data["repo_owner_name"] = args.repo_owner_name
    data["github_project_number"] = ctx.get("project_number", data.get("github_project_number"))
    data["github_project_title"] = ctx.get("project_title", data.get("github_project_title"))
    data["planned_issues"] = list(ctx.get("planned_issues", []))
    data.pop("completed_this_session", None)
    _save(args.state_file, data)

    if args.repo_owner_name:
        os.makedirs(os.path.dirname(args.global_state_file), exist_ok=True)
        _save(
            args.global_state_file,
            {"repo_owner_name": args.repo_owner_name, "repo_local_path": data["repo_local_path"]},
        )
        try:
            os.remove(args.legacy_state_file)
        except OSError:
            pass
    print(f"checkpoint: last_session written for {data['last_session']['date']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="default: <main checkout>/.co-dwerker.state.json, resolved from any worktree",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start-issue", help="begin tracking a new active issue")
    p.add_argument("issue", type=int)
    p.add_argument("--phase", default="2")
    p.add_argument("--set", action="append", metavar="KEY=VALUE")
    p.add_argument("--append", action="append", metavar="KEY=VALUE")
    p.set_defaults(func=cmd_start_issue)

    p = sub.add_parser("mark", help="mark a step in_progress or completed")
    p.add_argument("step_id", help="e.g. 3.5a")
    p.add_argument("status", choices=["in_progress", "completed"])
    p.add_argument("--set", action="append", metavar="KEY=VALUE")
    p.add_argument("--append", action="append", metavar="KEY=VALUE")
    p.add_argument("--clear", action="append", metavar="KEY")
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("set", help="update context (or --top keys) without changing step status")
    p.add_argument("--phase")
    p.add_argument("--issue", type=int)
    p.add_argument("--set", action="append", metavar="KEY=VALUE", help="progress.context key")
    p.add_argument("--append", action="append", metavar="KEY=VALUE")
    p.add_argument("--clear", action="append", metavar="KEY")
    p.add_argument("--top", action="append", metavar="KEY=VALUE", help="top-level state key")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("gate", help="exit 0 only if every tracked step of the phase is completed")
    p.add_argument("phase")
    p.add_argument(
        "--skip", action="append", metavar="STEP", help="step that legitimately does not apply"
    )
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("show", help="print progress, last_session, and top-level keys")
    p.add_argument("--phase")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("finish-issue", help="record the active issue as done and clear progress")
    p.set_defaults(func=cmd_finish_issue)

    p = sub.add_parser("end-session", help="write last_session and the global last-repo file")
    p.add_argument("--repo-owner-name", help="owner/repo; also writes the global last-repo file")
    p.add_argument("--date", help="YYYY-MM-DD (default today)")
    p.add_argument("--completed", help="comma-separated issue numbers completed this session")
    p.add_argument("--prs-created", help="comma-separated PR numbers")
    p.add_argument("--prs-merged", help="comma-separated PR numbers")
    p.add_argument("--global-state-file", default=GLOBAL_STATE_FILE, help=argparse.SUPPRESS)
    p.add_argument("--legacy-state-file", default=GLOBAL_STATE_FILE_LEGACY, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_end_session)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.state_file is None:
        args.state_file = default_state_file()
    try:
        return args.func(args)
    except CheckpointError as exc:
        print(f"checkpoint: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - any other failure is still a usage/state error
        print(f"checkpoint: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
