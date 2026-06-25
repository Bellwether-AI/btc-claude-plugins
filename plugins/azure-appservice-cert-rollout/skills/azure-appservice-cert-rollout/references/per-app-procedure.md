# Per-App Procedure — full CLI command reference

The core renewal sequence. Each section is **one tool call** when executing — never bundle them with `&&` or wrap them in a shell loop. Watch the output of each step before continuing to the next. If any step fails or returns unexpected output, halt the entire rollout — don't move to the next step or the next app.

## Pre-flight: PFX password in env, NOT in argv

The PFX password must already be in the `PFX_PWD` environment variable from Step 1 of the workflow. Every command below references it via the shell's env-var expansion (`"$PFX_PWD"` in bash, `$env:PFX_PWD` in PowerShell) so the literal password never appears on the command line. Reasons:

- `ps` / `ps aux` (macOS/Linux) and `Get-Process -IncludeUserName -Verbose` (Windows) show full command lines to other users on the workstation.
- Shell history (zsh's `~/.zsh_history`, bash's `~/.bash_history`, PowerShell's `(Get-PSReadLineOption).HistorySavePath`) captures executed commands.
- Some terminal multiplexers persist scrollback to disk.

If you didn't set `PFX_PWD` in Step 1, do that now in a separate command (NOT inline-prefixed to the cert command, which would still leak via `ps`):

| Shell | Set | Confirm (without echoing) |
|---|---|---|
| bash / zsh | `export PFX_PWD='<password>'` | `echo "${PFX_PWD:+set}"` → `set` |
| PowerShell | `$env:PFX_PWD = '<password>'` | `if ($env:PFX_PWD) { 'set' } else { 'unset' }` |
| cmd.exe | `set PFX_PWD=<password>` (no quotes) | `if defined PFX_PWD echo set` |

In the command examples below, `"$PFX_PWD"` is bash syntax. In PowerShell, the equivalent is `"$env:PFX_PWD"` or `$env:PFX_PWD` depending on quoting context. `az` CLI does not care which shell expanded the variable — it just sees the resolved password string at argv time, exactly as if you had typed it.

## Variables to substitute

Per app:

- `<sub-guid>` — subscription GUID
- `<rg>` — resource group of the web app
- `<app>` — web app name
- `<pfx-path>` — absolute path to the PFX file on the operator's workstation
- `<cert-name>` — friendly name to assign in App Service (e.g. `acme-wildcard-2026-27`)
- `<new-thumbprint>` — expected SHA-1 thumbprint (validated in Step 2 of the workflow)
- `<hostname>` — the custom hostname being bound (e.g. `app.example.com`)
- `<old-thumbprint>` — the cert being replaced (the "old" / soon-to-be-removed thumbprint)

The `PFX_PWD` env var holds the password — referenced as `"$PFX_PWD"` not interpolated literally.

## Step A — Switch subscription

```bash
az account set --subscription "<sub-guid>"
```

For the first app of each new subscription, verify with `az account show --query "{name:name,id:id,tenantId:tenantId}" -o table`. Confirm the tenantId still matches what was approved in Step 0 of the workflow — if a token has expired and the operator re-logged-in, this is where context drift would show up.

## Step B — Upload new PFX

```bash
az webapp config ssl upload \
  --resource-group "<rg>" --name "<app>" \
  --certificate-file "<pfx-path>" \
  --certificate-password "$PFX_PWD" \
  --certificate-name "<cert-name>" \
  --query "{thumbprint:thumbprint, subjectName:subjectName, expirationDate:expirationDate, issuer:issuer}" -o json
```

Note `--certificate-password "$PFX_PWD"` — shell expands the env var before az sees it; the literal password isn't in argv, isn't logged by az, and doesn't land in shell history.

What to confirm in the output:
- `thumbprint` matches `<new-thumbprint>` exactly. If it doesn't match, **HALT** — something's wrong (different PFX than expected, password decrypted a different cert payload, etc.).
- `expirationDate` is in the future and matches the cert validity window from Step 2.
- `subjectName` matches what was expected from Step 2.

Common benign warning: `CryptographyDeprecationWarning: Parsed a serial number which wasn't positive...` — about a chain cert's encoding quirk, not the upload itself. Ignore unless the upload also fails.

## Step C — Update SNI binding to new thumbprint

```bash
az webapp config ssl bind \
  --resource-group "<rg>" --name "<app>" \
  --certificate-thumbprint "<new-thumbprint>" \
  --ssl-type SNI \
  --hostname "<hostname>" \
  --query "hostNameSslStates[?name=='<hostname>']" -o json
```

`--hostname` causes the existing binding to be **re-pointed** at the new thumbprint without dropping it (this matches the Portal's "Update binding" action — zero-downtime renewal path). Do not use `ssl unbind` + `ssl bind` for renewals — that drops the binding briefly and can shuffle IPs on IP-based SSL.

What to confirm in the output:
- `sslState`: should be `SniEnabled`.
- `thumbprint`: should match `<new-thumbprint>`.
- `name`: should match `<hostname>`.

If the App Service has multiple in-scope hostnames, run Step C once per hostname (Step B's upload only needs to happen once per webspace, but each hostname's binding is a separate operation).

## Step D — Verify chain over the wire (skip for Stopped apps)

Wait 15-30 seconds for edge propagation, then probe the App Service directly via SNI. **Don't probe the public hostname** if there's a CDN or Application Gateway in front — that probe hits the front-door, not the App Service.

```bash
sleep 20
echo | openssl s_client -servername <hostname> -connect <app>.azurewebsites.net:443 -showcerts 2>/dev/null \
  | grep -E '^Certificate chain|^\s*[0-9] s:|^\s*i:' | head -20
```

Expected output: at least 3 certs (leaf, one or more intermediates, root). The leaf's issuer line should match an intermediate's subject. Example healthy output:

```
Certificate chain
 0 s:CN=*.example.com
   i:C=US, O=Example CA, CN=Example TLS Intermediate
 1 s:C=US, O=Example CA, CN=Example TLS Intermediate
   i:C=US, O=Example CA, CN=Example Root CA
 2 s:C=US, O=Example CA, CN=Example Root CA
   i:C=US, O=Example CA, CN=Example Root CA
```

### If Step D shows only the leaf cert (chain-less)

The binding has committed but the App Service is serving a chain-less cert. The Step 2 PFX check should have caught this — if it didn't, the script's chain logic has a gap that needs investigating. **Rollback procedure:**

```bash
# Re-bind to the OLD thumbprint (it's still in the webspace — Step E hasn't run yet)
az webapp config ssl bind \
  --resource-group "<rg>" --name "<app>" \
  --certificate-thumbprint "<old-thumbprint>" \
  --ssl-type SNI \
  --hostname "<hostname>"
```

Confirm the rollback via Resource Graph readback (Query 2). Then **halt the entire rollout** — do not proceed to Step E for this app or to the next app. Investigate why the PFX check passed but the served chain is incomplete (could be a same-thumbprint upload that overwrote a chain-bundled cert with a chain-less one, or could be an artifact of the chain-fix-vs-renew confusion). The operator decides next steps.

### If Step D shows the OLD cert's chain (edge cache lag)

Wait another 30 seconds and re-probe. Edge propagation can take longer than the empirical 15-30s estimate. The Resource Graph readback from Step C is authoritative — if it shows the new thumbprint, the binding is correct and the cache just hasn't refreshed yet.

### For Stopped App Services

Skip Step D entirely. The HTTP listener isn't running so the TLS probe will fail to connect regardless of cert state. Rely on Step C's Resource Graph readback as your only verification.

### For App Services behind an Application Gateway / Front Door / CDN

A public hostname probe sees the front-door's cert, not the App Service's. The `<app>.azurewebsites.net:443` direct probe with the custom hostname as SNI is the only reliable way to verify the App Service is serving the right cert. This is what the command above does.

## Step E — Delete the old cert resource from this webspace

**Pre-delete safety check.** Before running the delete, confirm no OTHER hostname in this webspace is still bound to `<old-thumbprint>`. Webspaces (sub + RG + region + OS) can host multiple App Services from the same App Service Plan, and they share cert resources. Deleting a cert resource that another app's binding still references will break that app's TLS handshake.

Query the Resource Graph to confirm zero remaining bindings reference the old thumbprint anywhere in the webspace:

```kql
Resources
| where type =~ 'microsoft.web/sites'
| where subscriptionId == '<sub-guid>' and resourceGroup =~ '<rg>'
| mv-expand sslState = properties.hostNameSslStates
| where tostring(sslState.thumbprint) == '<old-thumbprint>'
| project app = name, host = tostring(sslState.name)
```

If this returns zero rows, you're safe to delete. If it returns any rows, those are sibling apps still bound to the old cert — migrate them first (run their Step A→D), then come back to this delete.

When the pre-check passes:

```bash
az webapp config ssl delete \
  --resource-group "<rg>" \
  --certificate-thumbprint "<old-thumbprint>"
```

Note `az webapp config ssl delete` does NOT take `--name` — it's webspace-scoped, identified by `--resource-group` and `--certificate-thumbprint` only. Adding `--name` will error.

Possible errors:
- **`Certificate for thumbprint '<old>' not found`** — the cert is either already gone from this webspace (someone cleaned it earlier), or it's an App Service Managed Certificate which uses a different deletion path. Check with Resource Graph Query 4 to see what's actually present. See `managed-certs.md` for handling.
- **Permission denied** — operator's principal lacks `Microsoft.Web/certificates/delete` on the RG. Check role assignments.

After Step E, this app is fully done. Move to the next.

## Optional: same-webspace optimization

When multiple App Services share a webspace (same sub + RG + region + OS combo) — e.g. several apps under one App Service Plan — they share uploaded certs at the webspace level. A single upload to one of them creates a cert resource that all the others can bind to. In that case:

- Upload **once** for the webspace (one of the apps in it).
- Bind **per app/hostname** (each one is a separate binding operation).
- Delete the old cert **once** for the webspace, only after ALL siblings have been migrated (the Step E pre-check enforces this).

The skill does NOT require this optimization — running the full sequence per app still works (subsequent uploads against the same webspace+thumbprint behave benignly). Keeping it simple ("same exact sequence per app") is the safer pattern for first-time rollouts; the optimization is for operators who've seen this work before.

## When something fails mid-rollout

The bind→delete pattern is designed to be safe to halt at any boundary:
- If upload fails, nothing changed.
- If bind fails after a successful upload, the new cert is in the webspace but no bindings reference it yet. Rollback is "do nothing" (old cert still bound). The new cert resource can be deleted later if not needed.
- If verification (Step D) fails after a successful bind, the app is on the new cert. Rollback: re-bind to the old thumbprint (still in webspace because Step E hasn't run yet). Then halt and investigate.
- If the post-bind delete (Step E) fails, the new cert is bound and serving — that's the desired end state. The old cert is just clutter. Investigate the delete failure separately; do not halt the rollout for this.

The critical invariant: **never run Step E for app N before Step C has verified app N's binding is on the new cert AND the Step E pre-check confirms no siblings still need the old cert**. Otherwise you'll delete the cert the binding still references and TLS will break.
