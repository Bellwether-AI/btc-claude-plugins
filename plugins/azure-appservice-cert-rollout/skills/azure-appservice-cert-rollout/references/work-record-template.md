# Work record template

Use this structure for the markdown summary written in Step 9 of the workflow. Convention: name it `certupdate_<descriptor>.md` (e.g. `certupdate_acme_2026-12.md` or `certupdate_chain_fix.md`).

**Where to save it.** Write to the operator's explicit working directory — the one they invoked the skill from. **Do not** write to the directory containing the PFX (often a Downloads or sync folder; audit records don't belong alongside private keys).

**Redaction.** Never include the PFX password in the work record. If you echo any executed command into the record, redact `--certificate-password '...'` to `--certificate-password '<REDACTED>'`. Same for any environment variable dumps that might contain `PFX_PWD`. Subscription GUIDs, hostnames, thumbprints, and friendly names are all fine to include — they're not secrets.

---

## Template

```markdown
# <Client / domain> certificate rollout — <Month YYYY>

**Date executed:** <YYYY-MM-DD>
**Operator:** <name> (<email>)
**Tenant:** <tenant-name> (<tenant-id>)
**Azure CLI:** <`az version` output>
**PFX file:** <path or filename only — do not include password>

## 1. Why this round

Brief reason — renewal of an expiring cert, fix for a chain issue, rekey, etc. One or two sentences.

## 2. Certificate reference

| Thumbprint | Label | Disposition |
|---|---|---|
| `<new-thumbprint>` | NEW (target) | Issuer, validity window, friendly name in App Service, source PFX filename |
| `<old-thumbprint>` | OLD (to remove) | Issuer, validity window, friendly name |
| `<other-thumbprint>` | STALE (cleaned) | (if applicable) |

## 3. Pre-rollout state

Summary of the discovery findings from Step 3: how many in-scope hostnames, how many on target, how many on old, intentional Disabled, ASP SKU summary, stale clutter found.

## 4. Procedure executed

The exact sequence applied per App Service, with `--certificate-password '<REDACTED>'` substituted in any shown command. Reference `references/per-app-procedure.md` for the full template — no need to re-quote it here.

## 5. Per-app execution log

| # | Subscription | App Service | Resource Group | Hostname | Pre-state | Action | Post-state |
|---|---|---|---|---|---|---|---|
| 1 | <sub> | <app> | <rg> | <hostname> | <old tp> | Upload+Bind+Verify+Delete | ✅ new tp |
| 2 | ... | ... | ... | ... | ... | Delete old only | ✅ |

Or split into categorized sub-tables (full renewal / cleanup-only / no-action) if that's clearer.

## 6. Pre-rollout binding state (from Resource Graph)

```
<paste raw -o table output from discovery Query 2 here>
```

## 7. Final verification (from Resource Graph)

### 7.1 All in-scope bindings on the new thumbprint?

```
<paste raw -o table output from verification Query A here>
```

Expected: every row labeled `OK` or `NO_TLS` (intentional). Any `WRONG` row needs investigation.

### 7.2 Zero stale cert resources remain?

```
<paste raw -o table output from verification Query B here>
```

Expected: zero rows, OR only intentional remainders explicitly noted in §8 below.

## 8. Items intentionally left as-is

- `<hostname>` — left `Disabled` per operator decision (no TLS binding).
- `<cert resource name>` — Managed Cert left in place (harmless, unbound, see managed-certs.md).
- (etc.)

## 9. Operator notes / context

Anything worth carrying forward. Examples:
- Reason a specific app was treated differently.
- Pre-existing state that affected the plan (e.g. some apps had already been pre-migrated).
- Edge cases hit during execution (propagation delays, transient errors, etc.).

## 10. Plain-text summary (paste-friendly)

```
NEW CERT UPLOADED + BOUND + OLD CERT DELETED (N apps):
  <app>
  <app>
  ...

OLD CERT DELETED ONLY (N webspaces):
  <webspace>
  <webspace>
  ...

NO ACTION NEEDED (already clean, N apps):
  <app>
  ...

INTENTIONALLY UNTOUCHED:
  <reason 1>
  <reason 2>

FINAL STATE:
  N/N in-scope hostnames bound to <new-thumbprint>, SniEnabled, valid through <expiration>
  Zero remaining cert resources with thumbprint <old-thumbprint>
  (Any intentional exceptions listed in §8)
```
```
