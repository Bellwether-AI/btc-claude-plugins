# co-dwerker v1.2.0 Issue Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make co-dwerker close every issue a PR resolves, track fixes that await verification, and surface issues left behind by earlier sessions, on any project board.

**Architecture:** Skill-text changes in `work`, `pr-review`, `new-issue`, and `exit`, backed by three new per-issue context keys (`resolves_issues`, `refs_issues`, `verify_later`) and three new session-level keys (`pending_verification`, `reconcile_dismissed`, `status_role_map`) in the existing `checkpoint.py` state file. A new tracked standup step `1.reconcile` and a rewritten exit step 3 do the catching; Phase 5 closes what the PR declared. Board transitions go through a role map built once in Phase 0b instead of hard-coded option names.

**Tech Stack:** Markdown skills (Claude Code plugin), Python 3.9+ `checkpoint.py` with pytest, `gh` CLI, `jq`.

**Spec:** `docs/superpowers/specs/2026-09-24-co-dwerker-issue-closure-design.md` (same branch)

## Global Constraints

- Python target is 3.9 (`pyproject.toml`: `target-version = "py39"`); no `match`, no `X | Y` unions at runtime.
- Line length 100 for ruff and black; ruff selects `E, F, W, I, B, UP` and ignores `UP007, UP045`.
- Skill text refers to the scripts as `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py …` (shorthand `checkpoint.py …` is defined in each skill's header); never `$CK` aliases.
- `gh issue`/`gh pr` take `--repo "$REPO_OWNER_NAME"`; `gh project` takes `--owner "$REPO_OWNER"` (login only).
- Every new `gh` call inherits conventions §6: failure stops with the error and a question.
- Nothing closes an issue without either the PR's own `Closes` declaration (Phase 5) or an explicit user answer (standup, exit).
- Test commands, run from `plugins/co-dwerker`: `uv run --with pytest pytest -q`, `uvx ruff check .`, `uvx black --check .`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Version bump 1.1.0 → 1.2.0 in both `plugins/co-dwerker/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. CHANGELOG and RELEASE_NOTES live at the repo root and are the last commit before the PR.

## Review Focus

1. **A PR body with `Closes #16` inside a code fence or URL** (`.../issues/16`): the orphan scan must not count `/issues/16` as a reference. The pattern excludes `/` before `#`, but a URL has no `#`; a fenced `Closes #16` is a real reference. Task 9 runs the scan against the real repo and checks PR #22's output has no false numbers.
2. **`verify_later` with a missing `check_after`:** Step 3.7 must ask for the date rather than store `null`; a null date never triggers at standup. Covered by skill text in Task 4 (explicit "ask for one" sentence) and by Task 2's test that `show` prints the date.
3. **A board with two options matching the same role** (e.g. "Done" and "Closed"): the map takes the first match in option order and says which one it chose. Task 4 states this in Phase 0b.
4. **An issue in `resolves_issues` that belongs to another repo** (someone types `Org/Repo#12`): the keys hold integers only; Task 3's conventions §10 says cross-repo issues stay hand-written in the body and are not tracked.
5. **`pending_verification` present in the top-level copy but not in `progress.context`** (state written by v1.1.0 `end-session`, or a session that never ran `set`): Task 2 makes `show` fall back to the top-level copy, and Task 4's 1.reconcile reads context first, then top level.

---

### Task 1: `checkpoint.py` tracks `1.reconcile` and the new session keys

**Files:**
- Modify: `plugins/co-dwerker/scripts/checkpoint.py:56` (`PHASES["1"]`) and `:65-79` (`SESSION_KEYS`)
- Test: `plugins/co-dwerker/scripts/tests/test_checkpoint.py`

**Interfaces:**
- Produces: `PHASES["1"] == ["fetch", "report", "reconcile", "recommend"]`; `SESSION_KEYS` contains `"pending_verification"`, `"reconcile_dismissed"`, `"status_role_map"`. Task 4's skill text marks `1.reconcile`; Tasks 4–7 read and write the three keys.

- [ ] **Step 1: Write the failing tests** (append to `test_checkpoint.py`)

```python
def test_gate_1_requires_reconcile(tmp_path):
    _run(tmp_path, "start-issue", "7")
    for step in ("fetch", "report", "recommend"):
        _run(tmp_path, "mark", f"1.{step}", "completed")
    code, _ = _run(tmp_path, "gate", "1")
    assert code == 1
    _run(tmp_path, "mark", "1.reconcile", "completed")
    code, _ = _run(tmp_path, "gate", "1")
    assert code == 0


def test_reconciliation_keys_survive_issue_boundaries(tmp_path):
    _run(tmp_path, "start-issue", "7")
    _run(
        tmp_path,
        "set",
        "--append",
        'pending_verification={"issue": 16, "pr": 22, "condition": "nightly run succeeds",'
        ' "check_after": "2026-09-09", "recorded": "2026-09-08"}',
    )
    _run(
        tmp_path,
        "set",
        "--append",
        'reconcile_dismissed={"issue": 19, "pr": 22}',
        "--set",
        'status_role_map={"in_progress": "opt-a", "in_review": null, "done": "opt-c"}',
    )
    _run(tmp_path, "finish-issue")
    _, state = _run(tmp_path, "start-issue", "8")
    ctx = _read(state)["progress"]["context"]
    assert ctx["pending_verification"][0]["issue"] == 16
    assert ctx["reconcile_dismissed"] == [{"issue": 19, "pr": 22}]
    assert ctx["status_role_map"]["in_review"] is None
    assert ctx["status_role_map"]["done"] == "opt-c"


def test_append_dict_deduplicates(tmp_path):
    _run(tmp_path, "start-issue", "7")
    for _ in range(2):
        _run(tmp_path, "set", "--append", 'reconcile_dismissed={"issue": 19, "pr": 22}')
    _, state = _run(tmp_path, "show")
    assert _read(state)["progress"]["context"]["reconcile_dismissed"] == [{"issue": 19, "pr": 22}]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd plugins/co-dwerker && uv run --with pytest pytest -q scripts/tests/test_checkpoint.py -k "reconcile or append_dict"`
Expected: `test_gate_1_requires_reconcile` FAILS (`gate 1` returns 0 before `1.reconcile` is known); `test_reconciliation_keys_survive_issue_boundaries` FAILS with `KeyError: 'pending_verification'` (finish-issue dropped it); `test_append_dict_deduplicates` may already PASS (existing `--append` de-duplicates any JSON value). That is fine; it pins the behavior.

- [ ] **Step 3: Implement**

In `checkpoint.py`, change the phase 1 entry:

```python
    "1": ["fetch", "report", "reconcile", "recommend"],
```

and extend `SESSION_KEYS` (keep alphabetical-ish grouping; add after `"local_app_pids"`):

```python
    "local_app_pids",
    "pending_verification",
    "reconcile_dismissed",
    "status_role_map",
}
```

Add to the module docstring's comment on session keys nothing (the set is self-documenting), but update the comment above `SESSION_KEYS`:

```python
# Session-level context keys (not per-issue); they survive start-issue and finish-issue.
# pending_verification / reconcile_dismissed / status_role_map back the v1.2.0 issue
# reconciliation (conventions §10).
```

- [ ] **Step 4: Run the whole suite, ruff, black**

Run: `cd plugins/co-dwerker && uv run --with pytest pytest -q && uvx ruff check . && uvx black --check .`
Expected: all pass, `All checks passed!`, `would be left unchanged`.

- [ ] **Step 5: Commit**

```bash
git add plugins/co-dwerker/scripts/checkpoint.py plugins/co-dwerker/scripts/tests/test_checkpoint.py
git commit -m "feat(co-dwerker): checkpoint tracks 1.reconcile and reconciliation session keys

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `finish-issue` records the whole resolution set; `end-session` and `show` carry `pending_verification`

**Files:**
- Modify: `plugins/co-dwerker/scripts/checkpoint.py` — `cmd_finish_issue` (~line 368), `cmd_show` (~line 357, after `completed_this_session`), `cmd_end_session` (~line 444, before `data.pop("completed_this_session", None)`), and the usage docstring (lines 16–25).
- Test: `plugins/co-dwerker/scripts/tests/test_checkpoint.py`

**Interfaces:**
- Consumes: `progress.context.resolves_issues` (list of int, written by Task 4's Step 3.2/3.7 text), `progress.context.pending_verification` (list of dict, written by Task 4's Step 5.close-issue text and Task 7's exit text).
- Produces: `completed_this_session` includes every resolved issue; top-level `pending_verification` list after `end-session`; `show` prints `pending_verification:` followed by the JSON when non-empty.

- [ ] **Step 1: Write the failing tests**

```python
def test_finish_issue_records_every_resolved_issue(tmp_path):
    _run(tmp_path, "start-issue", "16", "--set", "planned_issues=[16, 17, 18, 30]")
    _run(tmp_path, "set", "--set", "resolves_issues=[16, 17, 18]")
    _, state = _run(tmp_path, "finish-issue")
    data = _read(state)
    assert data["completed_this_session"] == [16, 17, 18]
    assert data["progress"]["context"]["planned_issues"] == [30]
    assert "resolves_issues" not in data["progress"]["context"]  # per-issue key is cleared


def test_end_session_writes_pending_verification_top_level(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _run(tmp_path, "start-issue", "16")
    _run(
        tmp_path,
        "set",
        "--append",
        'pending_verification={"issue": 16, "pr": 22, "condition": "c",'
        ' "check_after": "2026-09-09", "recorded": "2026-09-08"}',
    )
    _, state = _run(
        tmp_path,
        "end-session",
        "--date",
        "2026-09-08",
        "--global-state-file",
        str(tmp_path / "g.json"),
        "--legacy-state-file",
        str(tmp_path / "l.json"),
    )
    data = _read(state)
    assert data["pending_verification"][0]["issue"] == 16
    assert data["progress"]["context"]["pending_verification"][0]["issue"] == 16


def test_end_session_writes_empty_pending_verification_when_none(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _run(tmp_path, "start-issue", "16")
    _, state = _run(
        tmp_path,
        "end-session",
        "--global-state-file",
        str(tmp_path / "g.json"),
        "--legacy-state-file",
        str(tmp_path / "l.json"),
    )
    assert _read(state)["pending_verification"] == []


def test_show_prints_pending_verification_from_context(tmp_path, capsys):
    _run(tmp_path, "start-issue", "16")
    _run(
        tmp_path,
        "set",
        "--append",
        'pending_verification={"issue": 16, "pr": 22, "condition": "c",'
        ' "check_after": "2026-09-09", "recorded": "2026-09-08"}',
    )
    _run(tmp_path, "show")
    out = capsys.readouterr().out
    assert "pending_verification:" in out
    assert '"check_after": "2026-09-09"' in out


def test_show_falls_back_to_top_level_pending_verification(tmp_path, capsys):
    state = tmp_path / ".co-dwerker.state.json"
    state.write_text(
        json.dumps(
            {
                "work_mode": "project",
                "pending_verification": [
                    {"issue": 16, "pr": 22, "condition": "c", "check_after": "2026-09-09"}
                ],
            }
        )
    )
    checkpoint.main(["--state-file", str(state), "show"])
    assert '"issue": 16' in capsys.readouterr().out
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd plugins/co-dwerker && uv run --with pytest pytest -q scripts/tests/test_checkpoint.py -k "resolved_issue or pending_verification"`
Expected: `test_finish_issue_records_every_resolved_issue` FAILS (`completed_this_session == [16]`); both `end-session` tests FAIL with `KeyError: 'pending_verification'`; both `show` tests FAIL (`pending_verification:` not in output).

- [ ] **Step 3: Implement**

`cmd_finish_issue`: replace the block from `history = data.setdefault(...)` through `planned.remove(issue)` with:

```python
    history = data.setdefault("completed_this_session", [])
    resolved: list[int] = [issue] if issue is not None else []
    for n in prog["context"].get("resolves_issues") or []:
        if isinstance(n, int) and n not in resolved:
            resolved.append(n)
    for n in resolved:
        if n not in history:
            history.append(n)
    planned = prog["context"].get("planned_issues")
    if isinstance(planned, list):
        for n in resolved:
            if n in planned:
                planned.remove(n)
```

and change the final print to `print(f"checkpoint: issues {resolved} recorded as completed; progress cleared")`.

`cmd_show`: after the `completed_this_session` print add:

```python
    pending = (data.get("progress") or {}).get("context", {}).get("pending_verification")
    if not pending:
        pending = data.get("pending_verification")
    if pending:
        print("pending_verification:")
        print(json.dumps(pending, indent=2))
```

`cmd_end_session`: before `data.pop("completed_this_session", None)` add:

```python
    data["pending_verification"] = list(ctx.get("pending_verification") or [])
```

Docstring usage block: add two lines after the `set --top` example:

```
  checkpoint.py set --set resolves_issues='[16, 17]'          # every issue the PR closes (Phase 3)
  checkpoint.py set --append pending_verification='{"issue": 16, "pr": 22, "condition": "…", "check_after": "2026-09-09", "recorded": "2026-09-08"}'
```

- [ ] **Step 4: Run the whole suite, ruff, black**

Run: `cd plugins/co-dwerker && uv run --with pytest pytest -q && uvx ruff check . && uvx black --check .`
Expected: all pass. If black reflows the long docstring line, that is inside a string and black leaves it; ruff `E501` applies to code lines only when configured — if it flags the docstring line, wrap the JSON example across two lines.

- [ ] **Step 5: Commit**

```bash
git add plugins/co-dwerker/scripts/checkpoint.py plugins/co-dwerker/scripts/tests/test_checkpoint.py
git commit -m "feat(co-dwerker): finish-issue records the resolution set; pending_verification persists

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Conventions §3/§9/§10 and the board setup reference

**Files:**
- Modify: `plugins/co-dwerker/references/conventions.md` (Contents list, §3 context table and the "Session-level keys" sentence, §9 state schema, new §10 at the end)
- Modify: `plugins/co-dwerker/references/setup-project-board.md` (after the Required Fields table)

**Interfaces:**
- Produces: the §10 text that Tasks 4–7 point to as "conventions §10".

- [ ] **Step 1: Contents list** — append `10. Closing issues and reconciliation` after item 9.

- [ ] **Step 2: §3 context table** — add these rows before the `issues_created` row, and change the `item_id` row's "Read by" to `pr-review, Phase 5, exit`:

```markdown
| `status_role_map` | Phase 0b | 2.board, pr-review §3, 5.board, new-issue §4, exit |
| `resolves_issues`, `refs_issues`, `verify_later` | Step 3.2, revised at 3.7 | Step 3.7 (PR body), Step 5.close-issue, `finish-issue` |
| `pending_verification` | Step 5.close-issue, exit §3 | Step 1.reconcile, exit §3, `show` |
| `reconcile_dismissed` | Step 1.reconcile, exit §3 | Step 1.reconcile |
```

Replace the sentence beginning "Session-level keys (`work_mode`, …" with:

```markdown
Session-level keys (`work_mode`, `main_checkout`, `planned_issues`, `issues_created`,
`labels_verified`, the project/board ids and `status_role_map`, `local_app_pids`,
`pending_verification`, `reconcile_dismissed`) survive `start-issue` and `finish-issue`;
everything else is per issue and is cleared. `finish-issue` records the active issue and every
entry of `resolves_issues` in `completed_this_session` and drops them from `planned_issues`.
```

- [ ] **Step 3: §9 schema** — in the JSON example add, after `"planned_issues": [43],`:

```json
  "pending_verification": [
    { "issue": 16, "pr": 22, "condition": "the 2026-09-09 05:00 UTC RefreshBbssamToken run succeeds", "check_after": "2026-09-09", "recorded": "2026-09-08" }
  ],
```

and add a bullet after the `last_session` bullet:

```markdown
- `pending_verification` is the top-level copy `end-session` makes of the session key of the
  same name, so the next standup (and `checkpoint.py show`) can read it even if `progress` was
  reset. `progress.context.pending_verification` is authoritative when both exist.
```

- [ ] **Step 4: New §10** — append at the end of the file:

````markdown
---

## 10. Closing issues and reconciliation

GitHub closes an issue on merge only when the PR body contains one of the keywords `close`,
`closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`, `resolved` immediately followed
by `#N` (or `Owner/Repo#N` for another repo), one issue per keyword. A bare `#N`, a number in the
title, or "(#17 #18 #16)" closes nothing. co-dwerker therefore tracks what a PR resolves
explicitly instead of hoping the body says so.

**The resolution set** (per-issue context, integers in the current repo only):

| Key | Meaning | PR body line |
|-----|---------|--------------|
| `resolves_issues` | issues the PR fully resolves; starts as `[ISSUE_NUMBER]` | `Closes #N` |
| `refs_issues` | issues the PR touches but does not finish | `Refs #N — <what remains>` |
| `verify_later` | entries `{"issue": N, "condition": "<observable>", "check_after": "YYYY-MM-DD"}` for issues in `resolves_issues` whose closure should be confirmed by a later observation | still `Closes #N` |

Never put a partially addressed issue under `Closes`; never hold a fully fixed issue out of
`Closes` because it "needs verification first" — that is what `verify_later` records. Issues in
other repos are written into the body by hand (`Closes Org/Repo#N`) and are not tracked.

**Phase 5** closes every open issue in `resolves_issues` that is not in `verify_later`, with a
comment naming the PR. For each `verify_later` entry it appends to the session-level
`pending_verification` list (`{"issue", "pr", "condition", "check_after", "recorded"}`) and
comments on the issue with the condition and the date co-dwerker will ask about it.

**Reconciliation** (standup Step 1.reconcile, exit §3) looks for issues left behind:

1. `pending_verification` entries whose `check_after` is today or earlier.
2. Open issues referenced by PRs merged in the last 30 days. Same-repo references are extracted
   with the `jq` regex `(?:^|[^A-Za-z0-9_/-])#([0-9]+)` (no lookbehind, so it runs in both `jq`
   and `gh --jq`). These are candidates, not proof: bodies also cite follow-ups they filed and
   numbers from other repos.
3. `planned_issues` entries whose issue is already closed (dropped silently, with a note).

Present the candidates and ask once with `AskUserQuestion`: **Close all listed as completed
(Recommended)** / **Close some (say which)** / **Leave all open**. Closing is
`gh issue close N --repo "$REPO_OWNER_NAME" --reason completed --comment "<why, naming the PR
and, for orphans, that the PR carried no closing keyword>"`. Kept-open orphans go into the
session-level `reconcile_dismissed` list as `{"issue": N, "pr": P}` so the same pair is not
asked again; kept-open pending entries either leave the list or get a new `check_after`.

**Board status roles.** Boards name their statuses differently, so Phase 0b maps the Status
field's options to three roles and stores `status_role_map` = `{"in_progress": <option id or
null>, "in_review": <option id or null>, "done": <option id or null>}`. Steps that move an item
use the role's id and, when it is `null`, say the board has no such status and continue. A board
with its built-in "Item closed" workflow enabled moves closed issues to Done on its own, which is
why reconciliation fixes issues first and only then looks for board items that disagree with
issue state.
````

- [ ] **Step 5: setup-project-board.md** — after the Required Fields table (before `### Optional Fields`) add:

```markdown
These are the values a **new** board gets. An existing board keeps its own names: Phase 0b maps
whatever Status options it has onto the three roles co-dwerker moves items through
(`in_progress`, `in_review`, `done`; conventions §10) and asks once about any role it cannot
match. Do not rename a working board's options to fit this table.
```

- [ ] **Step 6: Commit**

```bash
git add plugins/co-dwerker/references/conventions.md plugins/co-dwerker/references/setup-project-board.md
git commit -m "docs(co-dwerker): conventions §10 closing issues and reconciliation; board role mapping

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Work skill — Phase 0b role map, `1.reconcile`, resolution set in 3.2/3.7, Phase 5 close and board

**Files:**
- Modify: `plugins/co-dwerker/skills/work/SKILL.md` — Workflow line, Phase 0b item 2, new `### 1.reconcile`, `### 2.board`, `### 3.2`, `### 3.7`, `### 5.close-issue`, `### 5.board`

**Interfaces:**
- Consumes: Task 1's `1.reconcile` step id and session keys; Task 3's conventions §10.
- Produces: `resolves_issues`, `refs_issues`, `verify_later`, `pending_verification`, `reconcile_dismissed`, `status_role_map`, `item_id` values that Tasks 5–7 read.

- [ ] **Step 1: Workflow line** — change `1 Standup → 2 Brainstorm` to `1 Standup (incl. Left behind) → 2 Brainstorm`.

- [ ] **Step 2: Phase 0b item 2** — replace from `Expect **Status** (Backlog, …` through `Mark \`0b.project\` and \`0b.fields\` completed.` with:

```markdown
   Expect **Priority** (P0-Critical, P1-High, P2-Medium, P3-Low) and a single-select **Status**.
   If either field is missing, offer to create it using
   `${CLAUDE_PLUGIN_ROOT}/references/setup-project-board.md`. Boards differ in what they call
   their statuses, so map the Status options onto the three roles co-dwerker moves items through
   (conventions §10). Match names case-insensitively, first match in option order wins, and say
   which option each role got: `in_progress` ← In Progress, Doing, Active, Working;
   `in_review` ← In Review, Review, Reviewing, PR Open; `done` ← Done, Complete, Completed,
   Closed, Shipped. For a role with no match, ask once: "This board has no `<role>` status.
   Which option should co-dwerker use for it?" with up to three of the board's real option
   names and **Skip this transition**; skip stores `null`. If the state file already has
   `status_role_map` and every id in it is still among the field's options, keep it without
   asking. Record `project_number`, `project_title`, `project_id`, `status_field_id`,
   `status_options` (name → option id), `status_role_map` (role → option id or null),
   `priority_field_id`, `priority_options` with `checkpoint.py set` so later phases, the
   pr-review and new-issue skills, and the exit skill have them. Mark `0b.project` and
   `0b.fields` completed.
```

- [ ] **Step 3: New `### 1.reconcile`** — insert between `### 1.report` and `### 1.recommend`:

````markdown
### `1.reconcile`

Issues get left behind when a PR fixed them without a closing keyword, or when a fix was waiting
on a later observation nobody came back to (conventions §10). Three sources, one question, both
modes.

**a. Pending verification.** Entries in `progress.context.pending_verification` (falling back to
the top-level `pending_verification`) whose `check_after` is `$TODAY` or earlier.

**b. Orphan scan.** Open issues referenced by PRs merged in the last 30 days (newest 50):

```bash
SINCE=$(date -v-30d +%Y-%m-%d 2>/dev/null || date -d '30 days ago' +%Y-%m-%d)
gh pr list --repo "$REPO_OWNER_NAME" --state merged --search "merged:>=$SINCE" \
  --json number,title,body,mergedAt --limit 50 > /tmp/co-dwerker-merged.json
gh issue list --repo "$REPO_OWNER_NAME" --state open --json number,title --limit 200 \
  > /tmp/co-dwerker-open.json
jq -c -n --slurpfile prs /tmp/co-dwerker-merged.json --slurpfile open /tmp/co-dwerker-open.json '
  ($open[0] | map({key: (.number|tostring), value: .title}) | from_entries) as $open
  | $prs[0][] | . as $pr
  | [ ($pr.body // "") | scan("(?:^|[^A-Za-z0-9_/-])#([0-9]+)") | .[0] ] | unique[]
  | select($open[.] != null)
  | {pr: $pr.number, pr_title: $pr.title, merged: $pr.mergedAt[0:10],
     issue: (.|tonumber), issue_title: $open[.]}'
```

Drop any `{issue, pr}` pair that is in `progress.context.reconcile_dismissed`. Bare `#N`
references are candidates, not proof: PR bodies also cite follow-ups they filed and issue
numbers from other repos, so read the PR title before recommending a close. If `jq` is not
installed, say so and skip the scan rather than joining the two lists by hand.

**c. Planned-queue hygiene.** For each number in `planned_issues`, `gh issue view N --json state
--jq .state`; drop the closed ones with a one-line note and `checkpoint.py set --set
planned_issues='[...]'`. No question.

**Report and ask.** Add a **Left behind** section to the standup, one line per candidate:
`#N <title> — referenced by PR #P "<title>" (merged <date>)` or `#N <title> — pending
verification since <recorded>: <condition>`. Nothing listed → say "Nothing left behind" and mark
`1.reconcile` completed. Otherwise one `AskUserQuestion`: **Close all listed as completed
(Recommended)** / **Close some (say which)** / **Leave all open**.

For each issue the user closes:

```bash
gh issue close $N --repo "$REPO_OWNER_NAME" --reason completed \
  --comment "Latent close (co-dwerker standup $TODAY): resolved by PR #$P, merged $MERGED_DATE, which carried no closing keyword for this issue."
```

(for a pending-verification entry: `--comment "Verified (co-dwerker standup $TODAY): <condition>. Fix shipped in PR #$P."`).
For each orphan the user keeps open: `checkpoint.py set --append reconcile_dismissed='{"issue": N, "pr": P}'`.
For each pending entry: remove it from `pending_verification` (`checkpoint.py set --set
pending_verification='[<remaining entries>]'`); if the user says it is still waiting, keep it with
the new `check_after` they give. If the user reports the fix did not work, invoke
`co-dwerker:new-issue` or reopen (`gh issue reopen N`) as they prefer. Then
`checkpoint.py mark 1.reconcile completed`.
````

- [ ] **Step 4: `### 2.board`** — replace the block with:

````markdown
### `2.board` (project mode; otherwise `gate 2 --skip board`)

```bash
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json \
  | jq -r '.items[] | select(.content.number? == '$ISSUE_NUMBER') | .id'        # ITEM_ID
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID \
  --single-select-option-id $STATUS_ROLE_IN_PROGRESS_ID
checkpoint.py set --set item_id=$ITEM_ID
```

`$STATUS_ROLE_IN_PROGRESS_ID` is `status_role_map.in_progress`. When it is `null`, still record
`item_id` and say "board has no in-progress status; skipping the move".
````

- [ ] **Step 5: `### 3.2 Plan`** — replace with:

```markdown
### `3.2` Plan

Invoke `superpowers:writing-plans`; it turns the design doc into an implementation plan. Then set
the resolution set (conventions §10): start from `[$ISSUE_NUMBER]`; if the plan also fully covers
other open issues, add them to `resolves_issues`; if it covers part of one, put that number in
`refs_issues` instead.

`checkpoint.py mark 3.2 completed --set plan_doc=<absolute path> --set resolves_issues='[...]' --set refs_issues='[...]'`
```

- [ ] **Step 6: `### 3.7 Create PR`** — replace the paragraph and the heredoc with:

````markdown
### `3.7` Create PR

Re-read `resolves_issues` and `refs_issues` against what was actually implemented and correct them
(`checkpoint.py set --set …`). If any resolved issue should only be closed for good after a later
observation (tomorrow's scheduled run, a deploy, a customer confirming), record it with the
condition and the date to ask on, and ask the user for the date if the design did not give one:
`checkpoint.py set --set verify_later='[{"issue": N, "condition": "<observable>", "check_after": "YYYY-MM-DD"}]'`.
Those issues still get a `Closes` line; Phase 5 writes the verification record.

Compose the test plan from `progress.context` (local-app.md §6 lists the local-app lines). Fill in
every `<placeholder>` and every `$VAR` below with literal text before running; the quoted heredoc
does not expand variables. One `Closes #N` line per entry of `resolves_issues` and one `Refs`
line per entry of `refs_issues`; GitHub honours one issue per keyword, so never write
`Closes #16 #17`.

```bash
gh pr create --title "<concise title>" --body "$(cat <<'EOF'
## Summary
<what changed and why, as bullets>

Closes #$ISSUE_NUMBER
Closes #<each further number in resolves_issues, one per line>
Refs #<each number in refs_issues> — <what this PR did and what remains>

## Test plan
- [x] Existing tests pass; new tests cover the change
- [x] Linting passes
<local app verification line(s) when applicable>

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
checkpoint.py set --set pr_number=<number> --set pr_url=<url>
```

Delete the `Refs` line when `refs_issues` is empty.
````

- [ ] **Step 7: `### 5.close-issue`** — replace with:

````markdown
### `5.close-issue`

Close every issue the PR declared it resolves (conventions §10), not only `$ISSUE_NUMBER`. For
each `N` in `resolves_issues`:

```bash
gh issue view $N --repo "$REPO_OWNER_NAME" --json state --jq .state
```

- `OPEN` and not in `verify_later` → the merge did not auto-close it (a missing keyword, or the
  PR merged into a non-default branch):
  `gh issue close $N --repo "$REPO_OWNER_NAME" --reason completed --comment "Resolved by PR #$PR_NUMBER (merged $TODAY). Closed by co-dwerker Phase 5."`
- In `verify_later` (open or closed) → record it and say so on the issue:
  ```bash
  checkpoint.py set --append pending_verification='{"issue": N, "pr": $PR_NUMBER, "condition": "<condition>", "check_after": "<check_after>", "recorded": "$TODAY"}'
  gh issue comment $N --repo "$REPO_OWNER_NAME" --body "Fix merged in PR #$PR_NUMBER. Pending verification: <condition>. co-dwerker will ask about this at the first standup on or after <check_after>."
  ```
  If GitHub already closed it on merge, leave it closed; the record is what brings it back.
- `CLOSED` otherwise → nothing to do.

Mark `5.close-issue` completed (and `5.docs-merge` / `5.board` when they ran).
````

- [ ] **Step 8: `### 5.board`** — replace with:

```markdown
### `5.board` (project mode; otherwise `--skip board`)

`gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_ROLE_DONE_ID`

`$STATUS_ROLE_DONE_ID` is `status_role_map.done`. When it is `null`, say that only the board's own
"Item closed" workflow will move the item and continue.
```

- [ ] **Step 9: Sanity-read the file** — `grep -n "In Review\|Backlog\|Ready\b\|STATUS_IN_PROGRESS_ID\|STATUS_DONE_ID\|STATUS_IN_REVIEW_ID" plugins/co-dwerker/skills/work/SKILL.md` must return nothing. `grep -c "^### " plugins/co-dwerker/skills/work/SKILL.md` grows by exactly one (the new `1.reconcile`).

- [ ] **Step 10: Commit**

```bash
git add plugins/co-dwerker/skills/work/SKILL.md
git commit -m "feat(co-dwerker): work skill closes the whole resolution set, adds 1.reconcile, maps board roles

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: pr-review skill — resolution set standalone, role-mapped board step

**Files:**
- Modify: `plugins/co-dwerker/skills/pr-review/SKILL.md` §0 (Standalone paragraph) and §3

**Interfaces:**
- Consumes: `status_role_map.in_review`, `item_id` from state; `Closes` lines from the PR body.

- [ ] **Step 1: §0 Standalone** — replace `Keep \`url\` as \`$PR_URL\`. Derive \`$ISSUE_NUMBER\` from a \`Closes #N\` in the body, else from …` sentence with:

```markdown
Keep `url` as `$PR_URL`. Collect every same-repo `Closes|Fixes|Resolves #N` in the body as the
resolution set (conventions §10); the first is `$ISSUE_NUMBER` for the board lookup. If the body
has none, fall back to `progress.issue` in the state file if it exists, else null. Confirm in one
line — "Reviewing PR #N for issues #A, #B" — and if the body resolves issues without a closing
keyword (a bare `#N` in the title or body), say so; the PR author should fix the body before
merge or those issues will be left open.
```

- [ ] **Step 2: §3 Board** — replace the section with:

````markdown
## 3. Board (project mode only)

Move the item to the board's `in_review` role (conventions §10). Inside the work skill the ids are
in `progress.context` (`project_id`, `item_id`, `status_field_id`, `status_role_map`). Standalone,
fetch them and build the role map the same way Phase 0b does:

```bash
gh project view $PROJECT_NUMBER --owner "$REPO_OWNER" --format json --jq '.id'                 # PROJECT_ID
gh project field-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json \
  --jq '.fields[] | select(.name=="Status") | {id, options}'                                   # STATUS_FIELD_ID + options → role map
gh project item-list $PROJECT_NUMBER --owner "$REPO_OWNER" --format json \
  | jq -r '.items[] | select(.content.number? == '$ISSUE_NUMBER') | .id'                        # ITEM_ID
gh project item-edit --project-id $PROJECT_ID --id $ITEM_ID --field-id $STATUS_FIELD_ID \
  --single-select-option-id $STATUS_ROLE_IN_REVIEW_ID
```

`in_review` is `null` (the board has no review status) → say "This board has no in-review
status; leaving the item where it is" and move on. No linked issue → say "No linked issue found
for this PR; skipping the board update" and move on.
````

- [ ] **Step 3: Commit**

```bash
git add plugins/co-dwerker/skills/pr-review/SKILL.md
git commit -m "feat(co-dwerker): pr-review reads the full resolution set and the board role map

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: new-issue skill — offer the board's real statuses

**Files:**
- Modify: `plugins/co-dwerker/skills/new-issue/SKILL.md` §4 (the "Ask for a board status" sentence and the two `item-edit` lines)

- [ ] **Step 1: Replace** `Ask for a board status: **Backlog (Recommended)**, **Ready**, **In Progress**. Then:` with:

```markdown
Offer the board's own statuses: read `status_options` and `status_role_map` from the state file
(fetch with `gh project field-list` if absent) and list up to three options that are not the
`done` role, first one marked "(Recommended)". Then:
```

Leave the commands as they are; `$SELECTED_STATUS_OPTION_ID` is the id of the option the user
picked.

- [ ] **Step 2: Commit**

```bash
git add plugins/co-dwerker/skills/new-issue/SKILL.md
git commit -m "feat(co-dwerker): new-issue offers the board's real status options

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Exit skill — reconcile issues, then the board; carry pending verification

**Files:**
- Modify: `plugins/co-dwerker/skills/exit/SKILL.md` — intro list item 2, §2 note, §3 rewrite, §8 summary

**Interfaces:**
- Consumes: `last_session`/`--prs-merged`, `progress.context.pr_number`, `pending_verification`, `reconcile_dismissed`, `status_role_map`.

- [ ] **Step 1: Intro list item 2** — change `2. The GitHub Projects board (project mode) — shared, human-visible status` to `2. GitHub issues and, in project mode, the Projects board — what is actually closed and where it sits`.

- [ ] **Step 2: §2** — after "Omit any list flag that has nothing to report." add:

```markdown
`completed_this_session` already holds every issue `finish-issue` recorded, including the extra
entries of each PR's `resolves_issues`; pass `--completed` only for issues finished outside the
work skill.
```

- [ ] **Step 3: §3 rewrite** — replace the whole section with:

````markdown
## 3. Reconcile issues, then the board

Issues first, because a project board with its built-in "Item closed" workflow follows issue
state on its own, and the failure that actually happens is a fixed issue that never closed
(conventions §10).

**Issues.** For every PR merged this session (`--prs-merged`, plus `progress.context.pr_number`
if `gh pr view $N --json state --jq .state` says `MERGED`):

```bash
gh pr view $P --repo "$REPO_OWNER_NAME" --json number,title,body,mergedAt > /tmp/co-dwerker-pr.json
gh issue list --repo "$REPO_OWNER_NAME" --state open --json number,title --limit 200 > /tmp/co-dwerker-open.json
jq -c -n --slurpfile pr /tmp/co-dwerker-pr.json --slurpfile open /tmp/co-dwerker-open.json '
  ($open[0] | map({key: (.number|tostring), value: .title}) | from_entries) as $open
  | $pr[0] as $pr
  | [ ($pr.body // "") | scan("(?:^|[^A-Za-z0-9_/-])#([0-9]+)") | .[0] ] | unique[]
  | select($open[.] != null)
  | {pr: $pr.number, pr_title: $pr.title, merged: $pr.mergedAt[0:10], issue: (.|tonumber), issue_title: $open[.]}'
```

Skip pairs already in `reconcile_dismissed`. List what is left and ask once: **Close all listed
as completed (Recommended)** / **Close some (say which)** / **Leave all open**. Close with
`gh issue close $N --repo "$REPO_OWNER_NAME" --reason completed --comment "Latent close
(co-dwerker exit $TODAY): resolved by PR #$P, merged $MERGED_DATE, which carried no closing
keyword for this issue."`; record kept-open pairs with `checkpoint.py set --append
reconcile_dismissed='{"issue": N, "pr": P}'`. Then read `pending_verification` and repeat it in
the exit summary so tomorrow's reader sees what is waiting.

**Board (project mode).** Only items whose Status disagrees with the issue's state:

```bash
gh api graphql -f org="$REPO_OWNER" -F num=$PROJECT_NUMBER -f query='
query($org:String!,$num:Int!,$after:String){
  organization(login:$org){projectV2(number:$num){items(first:100,after:$after){
    pageInfo{hasNextPage endCursor}
    nodes{id fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name optionId}}
      content{__typename ... on Issue{number state repository{nameWithOwner}}}}}}}}' \
  --jq '.data.organization.projectV2.items | {more: .pageInfo, rows: [.nodes[] | select(.content.__typename=="Issue") | {id, option: .fieldValueByName.optionId, status: .fieldValueByName.name, repo: .content.repository.nameWithOwner, issue: .content.number, state: .content.state}]}'
```

Repeat with `-f after=<endCursor>` while `more.hasNextPage`. For a user-owned project replace
`organization(login:$org)` with `user(login:$org)`. A row is a discrepancy when `state == CLOSED`
and `option != status_role_map.done`, or `state == OPEN` and `option == status_role_map.done`.
Move the first kind to `done` with `gh project item-edit --project-id $PROJECT_ID --id <id>
--field-id $STATUS_FIELD_ID --single-select-option-id $STATUS_ROLE_DONE_ID` (when `done` is not
`null`); ask about the second kind, since an open issue in Done usually means someone closed the
wrong thing. Report "board agrees with issue state" when there are none.
````

- [ ] **Step 4: §8** — change the summary sentence to end `…the recommended starting point for the next session, any open items, and the pending-verification list with its check-after dates.`

- [ ] **Step 5: Commit**

```bash
git add plugins/co-dwerker/skills/exit/SKILL.md
git commit -m "feat(co-dwerker): exit reconciles issues against merged PRs before touching the board

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: README and version bump

**Files:**
- Modify: `plugins/co-dwerker/README.md` (Workflow section paragraph, board section table caption), `plugins/co-dwerker/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1: README Workflow** — after the `**Execute** runs autonomously …` paragraph add:

```markdown
**Standup** ends with a **Left behind** check: open issues that merged PRs reference, fixes whose
verification date has arrived, and closed issues still in the planned queue. **Close** closes
every issue the PR declared it resolves, not just the one the session started on, and records
fixes that await a later observation so the next standup asks about them.
```

- [ ] **Step 2: README board section** — replace `Expected fields, created on first run if missing:` with `Fields a new board gets on first run. An existing board keeps its own Status names; co-dwerker maps them onto in-progress / in-review / done roles (see \`references/conventions.md\` §10):`.

- [ ] **Step 3: Version** — `plugin.json` `"version": "1.1.0"` → `"1.2.0"`; in `marketplace.json` the co-dwerker entry's `"version": "1.1.0"` → `"1.2.0"`. Run `python3 -c "import json;json.load(open('.claude-plugin/marketplace.json'));json.load(open('plugins/co-dwerker/.claude-plugin/plugin.json'));print('ok')"` from the repo root.

- [ ] **Step 4: Commit**

```bash
git add plugins/co-dwerker/README.md plugins/co-dwerker/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "chore(co-dwerker): README for Left behind and role mapping; version 1.2.0

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Verify the new `gh`/`jq` pipelines against the real repo and board

**Files:** none changed unless a pipeline is wrong; then fix the skill text it came from and amend that task's commit message style with a `fix(co-dwerker):` commit.

- [ ] **Step 1: Orphan scan** — run the Task 4 Step 3(b) pipeline verbatim with `REPO_OWNER_NAME=Bellwether-Technology/PolicyConductor-Functions-Python`.
Expected rows (as of 2026-09-24): PR 22 → issues 19, 23; PR 49 → 19, 39; PR 40 → 38, 39; PR 52 → 53, 54, 55. No row may name an issue number that is not open, and PR 22 must not produce 16, 17, 18, 20, 21 (closed today).

- [ ] **Step 2: Exit single-PR variant** — run the Task 7 pipeline with `P=22`. Expected: the same PR-22 rows.

- [ ] **Step 3: Board discrepancy query** — run the Task 7 GraphQL with `REPO_OWNER=Bellwether-Technology`, `PROJECT_NUMBER=11`. Expected: two pages, zero discrepancies against `done` option id `98236657` (the frontend #43 item was fixed on 2026-09-24).

- [ ] **Step 4: Role mapping dry run** — `gh project field-list 11 --owner Bellwether-Technology --format json --jq '.fields[] | select(.name=="Status") | .options[].name'` and apply the Task 4 Step 2 rules by hand. Expected: `in_progress` → "In progress", `done` → "Done", `in_review` → no match (the skill would ask once).

- [ ] **Step 5: Regression run** — `cd plugins/co-dwerker && uv run --with pytest pytest -q && uvx ruff check . && uvx black --check .`. Expected: all pass.

- [ ] **Step 6:** If anything in Steps 1–4 differed from expected, fix the skill text and commit `fix(co-dwerker): <what>`.

---

### Task 10: Reviews, changelog, release notes, PR

- [ ] **Step 1: Skill-quality review** — invoke `skill-creator:skill-creator` on the four changed skills and conventions §10, and `pr-review-toolkit:code-reviewer` on the `checkpoint.py` diff (two agents at most in flight; no `model` override). Address Important findings with `fix(co-dwerker):` commits and re-run Task 9 Step 5.

- [ ] **Step 2: CHANGELOG.md** — add a `## [co-dwerker v1.2.0] - 2026-09-24` section at the top (below the title lines) with `### Added`, `### Changed`, `### Fixed` line items, one per change made in Tasks 1–8, each with its reason in one or two sentences.

- [ ] **Step 3: RELEASE_NOTES.md** — add `## co-dwerker v1.2.0` above `## co-dwerker v1.1.0` with `### What's New` (Left behind check, whole-resolution-set closing, pending verification, board role mapping), `### Behavior Changes` (standup gains a tracked step and a question; Phase 5 may close several issues; exit asks about orphans; new-issue offers the board's own statuses), `### Fixed Issues` (the PR-22 class of latent-open issues), `### Known Issues` (bare-reference scan yields candidates that include follow-up issues; 30-day/50-PR window; cross-repo issues untracked).

- [ ] **Step 4: Commit** — `git commit -m "docs(co-dwerker): CHANGELOG and RELEASE_NOTES for v1.2.0 …"`.

- [ ] **Step 5: Push and open the PR** against `main` in `Bellwether-AI/btc-claude-plugins`, body per the work skill's own template (Summary, `Closes #<tracking issue>` once the marketplace repo has Issues enabled and the tracker exists; otherwise a `Refs` line naming the design spec), test plan, `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
