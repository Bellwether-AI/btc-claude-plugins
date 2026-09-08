# Repo Detection

How `/co-dwerker:work` decides which repository a session is about. The working directory is
often not the target repo: people launch co-dwerker from a workspace folder holding several
clones, from a plugin marketplace checkout, or from their home directory. Detect and confirm
before doing anything else, and re-derive the environment variables from
`${CLAUDE_PLUGIN_ROOT}/references/conventions.md` §1 once the repo is settled.

## 1. Look at the working directory

```bash
DETECTED_REMOTE=$(git remote get-url origin 2>/dev/null)
DETECTED_REPO=$(echo "$DETECTED_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
```

- `git remote` fails: the CWD is not a git repo (or has no remote). Continue to step 2 and 3.
- It succeeds but the URL is not on `github.com`: treat `DETECTED_REPO` as empty and go straight
  to the hosting guard in step 5. Do not scan for sub-repos; the user is clearly inside some
  other repo and a wrong guess here would be confusing.

## 2. Look for a saved repo

Check, in order: `$STATE_FILE` in the CWD, then `$GLOBAL_STATE_FILE`
(`~/.claude/co-dwerker-last-repo.json`), then the legacy `~/.co-dwerker-last-repo.json`. From
whichever exists, read `repo_owner_name` and `repo_local_path` into `SAVED_REPO` and
`SAVED_REPO_PATH`.

## 3. Scan immediate subdirectories (only when the CWD is not a git repo)

```bash
for dir in */; do
  if [ -d "$dir/.git" ]; then
    SUB_REMOTE=$(git -C "$dir" remote get-url origin 2>/dev/null)
    SUB_REPO=$(echo "$SUB_REMOTE" | sed -E 's|.*github\.com[:/]||;s|\.git$||')
    [ -n "$SUB_REPO" ] && case "$SUB_REMOTE" in *github.com*) echo "$SUB_REPO|$(cd "$dir" && pwd)";; esac
  fi
done
```

Collect the `repo|absolute_path` pairs as `DISCOVERED_REPOS`. Immediate children only; never
recurse. Only GitHub remotes count.

## 4. Decide

Use `AskUserQuestion` whenever more than one answer is plausible. Options are the repos; put the
one matching `SAVED_REPO` first and label it "(last session)". When a chosen path is a discovered
one, prefer the freshly scanned path over the saved path, because repos move.

| Situation | Action |
|-----------|--------|
| **A.** CWD is a GitHub repo and matches `SAVED_REPO`, or there is no saved repo | Use `DETECTED_REPO` silently. |
| **B.** CWD is a GitHub repo but differs from `SAVED_REPO` | Ask: "The current directory is **$DETECTED_REPO**, but your last session was on **$SAVED_REPO**. Which one today?" Options: the two repos. |
| **C.** CWD is not a repo; sub-repos found; one matches `SAVED_REPO` | If it is the only sub-repo, use it and say so ("Found **$REPO** at `$PATH`, matching your last session."). Otherwise ask with the matching repo first. |
| **D.** CWD is not a repo; sub-repos found; none matches (or no saved repo) | If exactly one sub-repo and no saved repo, use it and say so. Otherwise ask, listing discovered repos and, if it exists, `SAVED_REPO` at `SAVED_REPO_PATH` labelled "(last session, not in this directory)". |
| **E.** CWD is not a repo; no sub-repos; `SAVED_REPO_PATH` exists on disk | Tell the user you are navigating to `$SAVED_REPO` at `$SAVED_REPO_PATH`, then `cd` there. |
| **F.** Nothing found and nothing saved | Ask for the path to the repo, or for the user to `cd` there and re-run. |

After any `cd`, re-derive the environment variables. If a `cd` fails because the path is gone,
say so and fall through to F.

## 5. Guards

- If `REPO_REMOTE` does not contain `github.com`: stop with the hosting-guard message from
  conventions §6.
- If `REPO_OWNER_NAME` is still empty: stop and ask the user to `cd` to a repo with a GitHub
  remote or provide its path.

Return to `skills/work/SKILL.md` at **Resume Check**.
