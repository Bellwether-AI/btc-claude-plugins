#!/usr/bin/env python3
"""Diff a local-app verification capture against its baseline.

Reads the two JSON files written by ``localapp_capture.py`` and reports, per app:
boot-status regression, new / pre-existing / resolved errors and warnings
(grouped by normalized text with repeat counts), honoring the repo's permanently
dismissed warnings from ``.co-dwerker.json``.

  localapp_diff.py diff                       # defaults shown below
  localapp_diff.py diff --baseline .co-dwerker.baseline-localapp.json \
                        --current  .co-dwerker.verify-localapp.json  \
                        --config   .co-dwerker.json
  localapp_diff.py dismiss --normalized "<exact normalized text from the report>" [--normalized ...]

Per-PR dismissals recorded by the work skill (``progress.context.dismissed_for_pr[].normalized``
in ``.co-dwerker.state.json``, found in the main checkout from any worktree) are honored too, so a
re-run after the user's decisions can reach exit 0.

Exit codes for ``diff``:
  0  clean — nothing new, nothing blocking
  1  needs decisions — new warnings (dismiss-or-fix) or entries with no baseline to compare against
  2  block — new errors or a healthy→failing boot regression
  4  usage error (missing current file, unreadable JSON) — the verify capture did not run

The JSON report is also written next to the inputs as ``.co-dwerker.localapp-diff.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import OrderedDict
from typing import Any, Optional

HEALTHY = {"started", "started_no_signal"}
FAILED = {"failed_to_start", "timeout", "crashed_during_idle", "preflight_failed"}

BASELINE_DEFAULT = ".co-dwerker.baseline-localapp.json"
CURRENT_DEFAULT = ".co-dwerker.verify-localapp.json"
CONFIG_DEFAULT = ".co-dwerker.json"
REPORT_DEFAULT = ".co-dwerker.localapp-diff.json"
STATE_FILE_NAME = ".co-dwerker.state.json"


class UsageError(Exception):
    """Bad or missing input; reported on stderr with exit code 4."""


def _load_json(path: str, required: bool) -> Optional[dict[str, Any]]:
    if not os.path.exists(path):
        if required:
            raise UsageError(f"{path} not found")
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise UsageError(f"{path} must contain a JSON object")
    return data


def default_state_file() -> str:
    """<main checkout>/.co-dwerker.state.json, resolved from the main checkout or a worktree."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
        common = result.stdout.strip()
        if result.returncode == 0 and common:
            return os.path.join(os.path.dirname(common), STATE_FILE_NAME)
    except OSError:
        pass
    return STATE_FILE_NAME


def per_pr_dismissals(state_path: str) -> set[str]:
    state = _load_json(state_path, required=False) or {}
    items = state.get("progress", {}).get("context", {}).get("dismissed_for_pr", [])
    out: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("normalized"):
            out.add(str(item["normalized"]))
        elif isinstance(item, str):
            out.add(item)
    return out


def _apps(doc: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not doc:
        return {}
    return {a["name"]: a for a in doc.get("apps", []) if isinstance(a, dict) and "name" in a}


def group_entries(entries: list[dict[str, Any]]) -> OrderedDict[str, dict[str, Any]]:
    """Group by normalized text, preserving first-seen order, with a repeat count."""
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for e in entries:
        key = e.get("normalized") or e.get("raw", "")
        if key in groups:
            groups[key]["count"] += 1
        else:
            groups[key] = {
                "normalized": key,
                "raw": e.get("raw", ""),
                "multiline": bool(e.get("multiline")),
                "line_count": e.get("line_count", 1),
                "first_offset_seconds": e.get("captured_at_offset_seconds"),
                "count": 1,
            }
    return groups


def boot_outcome(base: Optional[dict[str, Any]], cur: dict[str, Any]) -> dict[str, Any]:
    cur_status = cur.get("boot_status")
    cur_healthy = cur_status in HEALTHY
    if base is None or base.get("boot_status") == "skipped":
        return {
            "baseline": None if base is None else "skipped",
            "current": cur_status,
            "outcome": "no_baseline",
            "blocking": False,
        }
    base_status = base.get("boot_status")
    base_healthy = base_status in HEALTHY
    if base_healthy and cur_healthy:
        outcome = "ok"
    elif base_healthy and not cur_healthy:
        outcome = "regression"
    elif not base_healthy and cur_healthy:
        outcome = "fixed"
    else:
        outcome = "still_failing"
    rec = {
        "baseline": base_status,
        "current": cur_status,
        "outcome": outcome,
        "blocking": outcome == "regression",
    }
    if outcome == "still_failing" and base_status != cur_status:
        rec["note"] = f"failure mode changed: {base_status} -> {cur_status}"
    return rec


def diff_entries(
    base_entries: list[dict[str, Any]],
    cur_entries: list[dict[str, Any]],
    dismissed: set[str],
    has_baseline: bool,
    dismissed_for_pr: Optional[set[str]] = None,
) -> dict[str, list[dict[str, Any]]]:
    base_groups = group_entries(base_entries)
    cur_groups = group_entries(cur_entries)
    dismissed_for_pr = dismissed_for_pr or set()
    result: dict[str, list[dict[str, Any]]] = {
        "new": [],
        "pre_existing": [],
        "resolved": [],
        "dismissed": [],
        "dismissed_for_pr": [],
        "unbaselined": [],
    }
    for key, grp in cur_groups.items():
        if key in dismissed:
            result["dismissed"].append(grp)
        elif key in dismissed_for_pr:
            result["dismissed_for_pr"].append(grp)
        elif not has_baseline:
            result["unbaselined"].append(grp)
        elif key in base_groups:
            grp = dict(grp, baseline_count=base_groups[key]["count"])
            result["pre_existing"].append(grp)
        else:
            result["new"].append(grp)
    if has_baseline:
        for key, grp in base_groups.items():
            if key not in cur_groups and key not in dismissed:
                result["resolved"].append(grp)
    return result


def run_diff(args: argparse.Namespace) -> int:
    config = _load_json(args.config, required=False) or {}
    if config.get("local_app_skip"):
        print("localapp_diff: .co-dwerker.json has local_app_skip: true — nothing to diff")
        return 0
    baseline_doc = _load_json(args.baseline, required=False)
    current_doc = _load_json(args.current, required=True)
    dismissed = {str(x) for x in config.get("dismissed_warnings", []) if isinstance(x, (str, int))}
    for_pr = per_pr_dismissals(args.state_file or default_state_file())

    base_apps = _apps(baseline_doc)
    cur_apps = _apps(current_doc)
    if not cur_apps:
        raise UsageError(f"{args.current} has no apps[] entries")

    report: dict[str, Any] = {
        "baseline_file": args.baseline if baseline_doc else None,
        "current_file": args.current,
        "baseline_commit": (baseline_doc or {}).get("commit"),
        "current_commit": current_doc.get("commit"),
        "dismissed_warnings_applied": sorted(dismissed),
        "dismissed_for_pr_applied": sorted(for_pr),
        "apps": [],
    }
    hard_block = False
    needs_decision = False

    for name, cur in cur_apps.items():
        base = base_apps.get(name)
        has_baseline = base is not None and base.get("boot_status") != "skipped"
        boot = boot_outcome(base, cur)
        errors = diff_entries(
            (base or {}).get("log_errors", []) if has_baseline else [],
            cur.get("log_errors", []),
            set(),  # dismissals apply to warnings only
            has_baseline,
        )
        warnings = diff_entries(
            (base or {}).get("log_warnings", []) if has_baseline else [],
            cur.get("log_warnings", []),
            dismissed,
            has_baseline,
            for_pr,
        )
        app_block = boot["blocking"] or bool(errors["new"])
        app_decide = (
            bool(warnings["new"]) or bool(errors["unbaselined"]) or bool(warnings["unbaselined"])
        )
        hard_block |= app_block
        needs_decision |= app_decide
        report["apps"].append(
            {
                "name": name,
                "type": cur.get("type"),
                "boot": boot,
                "errors": errors,
                "warnings": warnings,
                "blocking": app_block,
                "needs_decision": app_decide,
            }
        )
    for base_name in base_apps:
        if base_name not in cur_apps:
            report.setdefault("apps_missing_from_current", []).append(base_name)
            needs_decision = True

    report["result"] = "block" if hard_block else ("needs_decision" if needs_decision else "clean")
    if (
        report["baseline_commit"]
        and report["current_commit"]
        and report["baseline_commit"] != report["current_commit"]
    ):
        report["note"] = (
            f"baseline captured on {report['baseline_commit'][:10]}, current is "
            f"{report['current_commit'][:10]} (expected when the branch has new commits)"
        )

    report_path = args.report or os.path.join(
        os.path.dirname(os.path.abspath(args.current)), REPORT_DEFAULT
    )
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report, report_path)
    return {"block": 2, "needs_decision": 1, "clean": 0}[report["result"]]


def _fmt_group(grp: dict[str, Any], show_normalized: bool) -> list[str]:
    first = grp["raw"].splitlines()[0] if grp["raw"] else grp["normalized"]
    suffix = ""
    if grp["count"] > 1:
        suffix += f"  (x{grp['count']})"
    if grp["multiline"]:
        suffix += f"  [{grp['line_count']} lines]"
    lines = [f"    {first[:300]}{suffix}"]
    if show_normalized:
        lines.append(f"      normalized: {grp['normalized'][:300]}")
    return lines


def print_report(report: dict[str, Any], report_path: str) -> None:
    print("[co-dwerker localapp diff]")
    if report["baseline_file"] is None:
        print(
            "  no baseline file — every current entry is reported as unbaselined (decide per entry)"
        )
    if report.get("note"):
        print(f"  note: {report['note']}")
    if report["dismissed_warnings_applied"]:
        print(
            f"  permanently dismissed warnings applied: {len(report['dismissed_warnings_applied'])}"
        )
    if report.get("dismissed_for_pr_applied"):
        print(
            f"  dismissed-for-this-PR warnings applied: {len(report['dismissed_for_pr_applied'])}"
        )
    for app in report["apps"]:
        b = app["boot"]
        print(f"\n  app: {app['name']} ({app['type']})")
        print(f"  boot: baseline={b['baseline']} current={b['current']} -> {b['outcome'].upper()}")
        if b.get("note"):
            print(f"        {b['note']}")
        e, w = app["errors"], app["warnings"]
        if e["new"]:
            print(f"  NEW ERRORS ({len(e['new'])} unique) — BLOCK, fix and re-run Step 5a:")
            for grp in e["new"]:
                print("\n".join(_fmt_group(grp, show_normalized=False)))
        if w["new"]:
            print(
                f"  NEW WARNINGS ({len(w['new'])} unique) — each needs a decision "
                "(fix / dismiss for this PR / dismiss permanently):"
            )
            for idx, grp in enumerate(w["new"], 1):
                lines = _fmt_group(grp, show_normalized=True)
                lines[0] = f"   {idx}. " + lines[0][4:]
                print("\n".join(lines))
        if e["unbaselined"] or w["unbaselined"]:
            print(
                f"  UNBASELINED entries (no baseline to compare): {len(e['unbaselined'])} errors, "
                f"{len(w['unbaselined'])} warnings — decide per entry"
            )
            for grp in e["unbaselined"]:
                print("\n".join(_fmt_group(grp, show_normalized=False)))
            for grp in w["unbaselined"]:
                print("\n".join(_fmt_group(grp, show_normalized=True)))
        if e["resolved"] or w["resolved"]:
            print(
                f"  resolved since baseline: {len(e['resolved'])} errors, "
                f"{len(w['resolved'])} warnings"
            )
        print(
            f"  pre-existing (informational): {len(e['pre_existing'])} errors, "
            f"{len(w['pre_existing'])} warnings; dismissed: {len(w['dismissed'])} permanent, "
            f"{len(w.get('dismissed_for_pr', []))} for this PR"
        )
    if report.get("apps_missing_from_current"):
        print(
            "\n  apps in baseline but not verified now: "
            + ", ".join(report["apps_missing_from_current"])
        )
    print(f"\n  report: {report_path}")
    print(f"RESULT: {report['result']}")


def run_dismiss(args: argparse.Namespace) -> int:
    config: dict[str, Any] = _load_json(args.config, required=False) or {}
    dismissed = config.get("dismissed_warnings")
    if not isinstance(dismissed, list):
        dismissed = []
    added = 0
    for text in args.normalized:
        if text not in dismissed:
            dismissed.append(text)
            added += 1
    config["dismissed_warnings"] = dismissed
    tmp = args.config + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, args.config)
    print(
        f"localapp_diff: {added} warning(s) added to dismissed_warnings in {args.config} "
        f"({len(dismissed)} total)"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("diff", help="compare verify capture against baseline")
    p.add_argument("--baseline", default=BASELINE_DEFAULT)
    p.add_argument("--current", default=CURRENT_DEFAULT)
    p.add_argument("--config", default=CONFIG_DEFAULT)
    p.add_argument(
        "--state-file",
        default=None,
        help="state file holding progress.context.dismissed_for_pr (default: main checkout's)",
    )
    p.add_argument(
        "--report",
        help=f"where to write the JSON report (default {REPORT_DEFAULT} beside --current)",
    )
    p.add_argument(
        "--json", action="store_true", help="print the JSON report instead of the text summary"
    )
    p.set_defaults(func=run_diff)

    p = sub.add_parser("dismiss", help="permanently dismiss warning(s) for this repo")
    p.add_argument("--config", default=CONFIG_DEFAULT)
    p.add_argument(
        "--normalized", action="append", required=True, help="exact normalized text (repeatable)"
    )
    p.set_defaults(func=run_dismiss)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except UsageError as exc:
        print(f"localapp_diff: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
