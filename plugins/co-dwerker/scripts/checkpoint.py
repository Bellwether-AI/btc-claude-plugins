#!/usr/bin/env python3
"""Progress checkpoints for co-dwerker sessions.

Writes a ``progress`` block into ``.co-dwerker.state.json`` so that step
completion survives context compaction, crashes, and harnesses where no
task/todo tool is available. Replaces the v0.3.x ``TaskCreate`` step tracking.

Usage (run from the repo root, or pass --state-file):

  checkpoint.py start-issue 42 --phase 2
  checkpoint.py mark 3.1 in_progress
  checkpoint.py mark 3.1 completed --set baseline_tests=true
  checkpoint.py set --set pr_number=57 --set pr_url=https://... --append local_app_pids=12345
  checkpoint.py gate 3          # exit 0 if every phase-3 step is completed, else 1 + missing
  checkpoint.py show            # dump the progress block
  checkpoint.py finish-issue    # record completion and clear the live progress block

Step ids are ``<phase>.<step>`` and mirror the headings in skills/work/SKILL.md.
Unknown step ids are accepted (with a warning) so SKILL.md edits never break the
script; ``gate`` only checks the steps it knows about for that phase.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from typing import Any

STATE_FILE_DEFAULT = ".co-dwerker.state.json"

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
    "planned_issues",
    "project_number",
    "project_title",
    "project_id",
    "status_field_id",
    "status_options",
    "priority_field_id",
    "priority_options",
    "local_app_pids",
}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


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
        sys.exit(f"checkpoint: {path} is not valid JSON ({exc}); refusing to overwrite it")
    if not isinstance(data, dict):
        sys.exit(f"checkpoint: {path} must contain a JSON object")
    return data


def _save(path: str, data: dict[str, Any]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _warn_if_tracked(path: str) -> None:
    """The state file is per-clone; warn if git would commit it."""
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", path],
            capture_output=True,
            check=False,
        )
    except (OSError, FileNotFoundError):
        return
    if result.returncode == 1:  # 1 == not ignored
        print(
            f"checkpoint: WARNING {path} is not gitignored. Add it to .gitignore "
            "before committing.",
            file=sys.stderr,
        )


def _parse_value(text: str) -> Any:
    """Parse ``key=value`` values as JSON when possible, else keep the string."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _split_kv(item: str) -> tuple[str, Any]:
    if "=" not in item:
        sys.exit(f"checkpoint: expected key=value, got {item!r}")
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
            sys.exit(f"checkpoint: cannot append to non-list context key {key!r}")
    for key in clears:
        ctx.pop(key, None)


def _phase_of(step_id: str) -> str:
    return step_id.split(".", 1)[0]


def cmd_start_issue(args: argparse.Namespace) -> int:
    data = _load(args.state_file)
    prog = _progress(data)
    prog.update(
        {
            "issue": args.issue,
            "phase": args.phase,
            "step": None,
            "status": "in_progress",
            "started_at": _now(),
            "updated_at": _now(),
            "completed_steps": [],
        }
    )
    # Per-issue context resets; session-wide keys survive.
    session_keys = SESSION_KEYS
    prog["context"] = {k: v for k, v in prog["context"].items() if k in session_keys}
    _apply_context(prog, args.set or [], args.append or [], [])
    _save(args.state_file, data)
    _warn_if_tracked(args.state_file)
    print(f"checkpoint: started issue #{args.issue} at phase {args.phase}")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    data = _load(args.state_file)
    prog = _progress(data)
    phase = _phase_of(args.step_id)
    known = PHASES.get(phase, [])
    if phase not in PHASES or args.step_id.split(".", 1)[-1] not in known:
        print(
            f"checkpoint: note — {args.step_id} is not in the built-in step manifest",
            file=sys.stderr,
        )
    prog["phase"] = phase
    prog["step"] = args.step_id
    prog["status"] = args.status
    prog["updated_at"] = _now()
    if args.status == "completed" and args.step_id not in prog["completed_steps"]:
        prog["completed_steps"].append(args.step_id)
    if args.status == "in_progress" and args.step_id in prog["completed_steps"]:
        # Re-running a step (e.g. Step 5a after a fix) reopens it.
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
    prog["updated_at"] = _now()
    _save(args.state_file, data)
    print("checkpoint: context updated")
    return 0


def _missing(prog: dict[str, Any], phase: str) -> list[str]:
    expected = [f"{phase}.{s}" for s in PHASES.get(phase, [])]
    done = set(prog.get("completed_steps", []))
    return [s for s in expected if s not in done]


def cmd_gate(args: argparse.Namespace) -> int:
    data = _load(args.state_file)
    prog = _progress(data)
    if args.phase not in PHASES:
        sys.exit(f"checkpoint: unknown phase {args.phase!r}; known: {', '.join(PHASES)}")
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
    prog = data.get("progress")
    if not prog:
        print("checkpoint: no progress block in state file")
        return 0
    print(json.dumps(prog, indent=2))
    phase = args.phase or prog.get("phase")
    if phase in PHASES:
        missing = _missing(prog, phase)
        print(
            f"\nPhase {phase}: "
            + ("all tracked steps completed" if not missing else "missing " + ", ".join(missing))
        )
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
        {"issue": None, "phase": "6", "step": None, "status": "completed", "updated_at": _now()}
    )
    prog["completed_steps"] = []
    prog["context"] = {k: v for k, v in prog["context"].items() if k in SESSION_KEYS}
    _save(args.state_file, data)
    print(f"checkpoint: issue #{issue} recorded as completed; progress cleared")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--state-file", default=STATE_FILE_DEFAULT, help=f"default: {STATE_FILE_DEFAULT}"
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

    p = sub.add_parser("set", help="update context without changing step status")
    p.add_argument("--phase")
    p.add_argument("--issue", type=int)
    p.add_argument("--set", action="append", metavar="KEY=VALUE")
    p.add_argument("--append", action="append", metavar="KEY=VALUE")
    p.add_argument("--clear", action="append", metavar="KEY")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("gate", help="exit 0 only if every tracked step of the phase is completed")
    p.add_argument("phase")
    p.add_argument(
        "--skip", action="append", metavar="STEP", help="step that legitimately does not apply"
    )
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("show", help="print the progress block")
    p.add_argument("--phase")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("finish-issue", help="record the active issue as done and clear progress")
    p.set_defaults(func=cmd_finish_issue)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
