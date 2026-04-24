"""Filter pre-fix artifacts from a CosmosDB eval JSON.

The BTC agent eval workflow pulls all human-rated items via query_evals.py.
When a prior round's fix PR merged close to (or during) the eval window,
some items were evaluated AFTER the merge but were PROCESSED BY THE AGENT
BEFORE the fix actually deployed. Counting those as new failures leads to
inventing failure patterns that don't exist.

This script removes pre-fix artifacts by comparing each item's `_ts`
(when the agent ran) against the latest prior-fix PR merge time.

Usage:
    python filter_prefix_artifacts.py \\
        --input eval_data/ticket_reviewer_evals_20260417_093131.json \\
        --prior-fixes 70,16 \\
        --repo-map "70=BTC-Python-Agents,16=BTCAgentPrompts" \\
        --output eval_data/ticket_reviewer_post_fix_20260417.json

Prints a summary:
    Pre-fix artifacts excluded: 5 (ran before <timestamp>)
    Post-fix items retained:     4
      Rating distribution: 1★=1  2★=1  3★=0  4★=1  5★=1

Requires `gh` CLI authenticated (for `gh pr view --json mergedAt`).
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def fetch_merged_at(repo: str, pr_number: int) -> datetime | None:
    """Fetch mergedAt for a PR via gh CLI. Returns None if not merged."""
    full_repo = f"Bellwether-AI/{repo}"
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", full_repo, "--json", "mergedAt,state"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"  ERROR: gh pr view #{pr_number} in {full_repo}: {e.stderr.strip()}", file=sys.stderr)
        return None

    data = json.loads(result.stdout)
    merged_at = data.get("mergedAt")
    if not merged_at:
        print(f"  WARN: PR #{pr_number} in {full_repo} is {data.get('state', 'unknown')}, not merged; skipping", file=sys.stderr)
        return None
    return datetime.fromisoformat(merged_at.replace("Z", "+00:00"))


def parse_repo_map(raw: str) -> dict[int, str]:
    """Parse "70=BTC-Python-Agents,16=BTCAgentPrompts" into {70: "BTC-Python-Agents", ...}."""
    out = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        pr_str, repo = entry.split("=", 1)
        out[int(pr_str.strip())] = repo.strip()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="Path to query_evals.py output JSON")
    parser.add_argument("--prior-fixes", required=True, help="Comma-separated PR numbers to use as the cutoff fixes")
    parser.add_argument("--repo-map", required=True, help='Map PR->repo, e.g. "70=BTC-Python-Agents,16=BTCAgentPrompts"')
    parser.add_argument("--output", required=True, type=Path, help="Path to write filtered JSON")
    parser.add_argument("--deploy-lag-minutes", type=int, default=0,
                        help="Extra minutes to add past mergedAt to account for deploy lag (default 0; "
                             "CI/CD on these repos typically lands within a minute or two of merge)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        return 1

    with args.input.open() as f:
        data = json.load(f)

    items = data.get("items", [])
    if not items:
        print("WARN: no items in input", file=sys.stderr)

    repo_map = parse_repo_map(args.repo_map)
    pr_numbers = [int(p.strip()) for p in args.prior_fixes.split(",") if p.strip()]

    missing = [pr for pr in pr_numbers if pr not in repo_map]
    if missing:
        print(f"ERROR: repo not mapped for PRs: {missing}. Add them to --repo-map.", file=sys.stderr)
        return 1

    # Fetch merge times
    print("Fetching merge times:")
    merge_times: list[datetime] = []
    for pr in pr_numbers:
        t = fetch_merged_at(repo_map[pr], pr)
        if t is not None:
            print(f"  #{pr} ({repo_map[pr]}): {t.isoformat()}")
            merge_times.append(t)
        else:
            print(f"  #{pr} ({repo_map[pr]}): unavailable; will not use as cutoff")

    if not merge_times:
        print("ERROR: no usable merge times; cannot filter", file=sys.stderr)
        return 1

    cutoff = max(merge_times)
    if args.deploy_lag_minutes:
        cutoff = cutoff.replace(minute=cutoff.minute + args.deploy_lag_minutes)  # rough; for precise use timedelta
    cutoff_ts = int(cutoff.timestamp())

    print(f"\nEffective cutoff (latest fix merge + {args.deploy_lag_minutes}min lag): "
          f"{datetime.fromtimestamp(cutoff_ts, tz=timezone.utc).isoformat()}  (unix {cutoff_ts})")

    # Partition items
    kept: list[dict] = []
    excluded: list[dict] = []
    for item in items:
        ts = item.get("_ts")
        if ts is None:
            kept.append(item)  # no _ts — can't filter, keep
            continue
        if ts < cutoff_ts:
            excluded.append(item)
        else:
            kept.append(item)

    # Rating distribution on kept
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for item in kept:
        r = item.get("content", {}).get("rating")
        if isinstance(r, (int, float)) and 1 <= int(r) <= 5:
            dist[int(r)] += 1

    # Compose output
    meta = dict(data.get("metadata", {}))
    meta["post_fix_filter"] = {
        "cutoff_unix_ts": cutoff_ts,
        "cutoff_iso": datetime.fromtimestamp(cutoff_ts, tz=timezone.utc).isoformat(),
        "prior_fix_prs": [{"pr": pr, "repo": repo_map[pr]} for pr in pr_numbers],
        "pre_fix_artifacts_excluded": len(excluded),
        "post_fix_items_retained": len(kept),
    }
    out = {"metadata": meta, "items": kept, "_excluded_prefix_items": excluded}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(out, f, indent=2, default=str)

    # Summary
    print(f"\nPre-fix artifacts excluded: {len(excluded)} (ran before {cutoff.isoformat()})")
    print(f"Post-fix items retained:     {len(kept)}")
    print(f"  Rating distribution: 1★={dist[1]}  2★={dist[2]}  3★={dist[3]}  4★={dist[4]}  5★={dist[5]}")
    if len(items):
        pct = 100.0 * len(excluded) / len(items)
        if pct > 30:
            print(f"\n  NOTE: {pct:.0f}% of the sample was pre-fix artifacts. Flag this in the Phase 3 proposal — "
                  f"Round N-1's fix may have landed most of the apparent failures.")
    print(f"\nWrote filtered JSON to: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
