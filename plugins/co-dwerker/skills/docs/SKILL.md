---
name: docs
description: Use when the user wants to write or update companion documentation for a change — documenting a PR or issue, updating a docs repo, or opening a docs PR. Also use for "document this", "update the docs for issue 42", or "write the docs PR". Invoked by /co-dwerker:work Phase 4 after code-PR approval.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py *)
---

# Co-Dwerker: Docs

Create or update documentation in a project's companion docs repo for a PR, an issue, or a
described change. Works standalone at any time and is called by `/co-dwerker:work` at Phase 4.

Scope: the **companion docs repo** only. `CHANGELOG.md` and `RELEASE_NOTES.md` in the code repo
belong to the work skill's Step 3.6.

Conventions §1 (environment, running the scripts, never `cd` out of the code repo), §6 (`gh`
errors), §9 (`.co-dwerker.json` schema): `${CLAUDE_PLUGIN_ROOT}/references/conventions.md`. If
`REPO_OWNER_NAME` is empty, fall back to `repo_owner_name` in `.co-dwerker.state.json`, and
failing that ask for `owner/repo`.

## 1. Identify the subject

**From the work skill.** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint.py show` gives
`progress.context.pr_number` and `progress.issue`. Say "Documenting PR #N (issue #M)" and go to
step 2.

**Standalone.** Ask what to document. Options: **A PR number**, **An issue number**,
**A description of the change**. Then:

- PR: `gh pr view $PR_NUMBER --repo "$REPO_OWNER_NAME" --json title,body,files,commits,headRefName`;
  take `$ISSUE_NUMBER` from a `Closes #N` if present.
- Issue: `gh issue view $ISSUE_NUMBER --repo "$REPO_OWNER_NAME" --json title,body,comments,labels`,
  and the most recent merged PR from
  `gh pr list --repo "$REPO_OWNER_NAME" --state merged --search "closes #$ISSUE_NUMBER" --json number,title`.
- Description: use it as-is; PR and issue numbers are null.

## 2. Docs config

Read `docs_repo` and `docs_path` from `.co-dwerker.json`. If missing, ask: **Configure a docs repo
now** (take `org/repo` and the path within it; merge into `.co-dwerker.json`) or **Skip
documentation** (end with a note that `.co-dwerker.json` can be edited later).

## 3. Locate or clone the docs repo

Look for an existing clone beside the main checkout (`$MAIN_CHECKOUT/../<name>`,
`$MAIN_CHECKOUT/../../<name>`; `MAIN_CHECKOUT` is `progress.context.main_checkout` or conventions
§1). Otherwise `gh repo clone "$DOCS_REPO" "$MAIN_CHECKOUT/../<name>"` and remember that this
session created it. Keep the session's CWD in the code repo and address the docs repo with
`git -C "$DOCS_REPO_PATH"` throughout:

```bash
git -C "$DOCS_REPO_PATH" checkout main
git -C "$DOCS_REPO_PATH" pull origin main
git -C "$DOCS_REPO_PATH" checkout -b "docs/$ISSUE_NUMBER-<short-description>"   # or docs/$TODAY-<slug> with no issue
```

Inside the work skill: `checkpoint.py set --set docs_repo_path=<path> --set docs_repo_cloned=<true|false>`.

## 4. Assess the documentation impact

Read the PR diff (`gh pr diff $PR_NUMBER --repo "$REPO_OWNER_NAME"`) or the issue. Then:

- New feature → a new doc page under `$DOCS_PATH`.
- Changed behavior → update the pages that describe the component.
- Bug fix → update a known-issues or troubleshooting section if one exists.
- No user-facing impact → say so and ask: **Skip docs (Recommended)** (delete the branch) or
  **Write something anyway**.

## 5. Write

Read a few existing pages in `$DOCS_PATH` first and match their structure, tone, and front matter.
Then create or update the files identified above.

## 6. Open the docs PR

Fill in every `<placeholder>` and `$VAR` with literal text before running; the quoted heredoc does
not expand variables.

```bash
git -C "$DOCS_REPO_PATH" add <the specific files you changed>
git -C "$DOCS_REPO_PATH" commit -m "docs: update documentation for $REPO_OWNER_NAME#$ISSUE_NUMBER"
git -C "$DOCS_REPO_PATH" push -u origin "<branch>"
gh pr create --repo "$DOCS_REPO" --head "<branch>" --title "docs: <description>" --body "$(cat <<'EOF'
## Summary
Documentation update for $REPO_OWNER_NAME#$ISSUE_NUMBER

<what changed in the docs, as bullets>

## Related
- Code PR: $REPO_OWNER_NAME#$PR_NUMBER
- Issue: $REPO_OWNER_NAME#$ISSUE_NUMBER
EOF
)"
```

Inside the work skill: `checkpoint.py set --set docs_pr_number=<n> --set docs_pr_url=<url>`.

## 7. Cross-reference (work skill only)

Back in the code repo, add a line to `CHANGELOG.md` referencing the docs PR. Standalone
invocations skip this.

## 8. Confirm

Tell the user the docs PR URL, what changed in the docs, and the related code PR and issue.
Inside the work skill, Phase 4 treats this confirmation as its gate. Standalone, you are done.
