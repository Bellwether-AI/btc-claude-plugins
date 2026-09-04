# App Service Managed Certificates — detection and handling

App Service Managed Certificates (ASMC) are free TLS certs that Azure provisions and auto-renews for custom hostnames bound to App Services. They look similar to uploaded BYOC certs in Resource Graph, but they're managed differently — and they don't respond to the standard `az webapp config ssl delete` command.

This file exists because a previous cert-rollout session discovered a leftover Managed Cert during cleanup and couldn't remove it with the obvious command. The fix is to recognize them on sight and treat them differently.

## How to recognize a Managed Certificate

In the Resource Graph cert resource output, an ASMC has these tells:

| Field | What you'll see |
|---|---|
| `friendlyName` | empty string (uploaded BYOC certs usually have a friendly name set) |
| `name` (the cert resource name) | follows the pattern `<hostname>-<appservice-name>`, e.g. `app.example.com-myappservice` |
| `canonicalName` | matches the custom hostname (e.g. `app.example.com`) |
| `issuer` | typically `GeoTrust TLS RSA CA G1`, `DigiCert ...`, or similar — depends on era and Microsoft's current cert vendor |
| `subjectName` | the specific hostname (not a wildcard) |
| `expirationDate` | typically ~6 months out from issue date (ASMCs are short-lived and auto-renewed) |

If any of those match, treat it as a Managed Cert.

## Why `az webapp config ssl delete` fails on them

The `az webapp config ssl delete --certificate-thumbprint <tp>` command operates against the App Service-managed cert store API path. Managed Certs live in a slightly different code path — they're tied to the hostname binding lifecycle rather than to free-standing cert resources. The CLI returns:

```
ERROR: Certificate for thumbprint 'XXXX' not found
```

…even though Resource Graph clearly shows the cert resource exists with that thumbprint.

## How to actually delete a Managed Cert

Three options, in order of preference:

### Option 1 — Leave it alone

If the Managed Cert isn't bound to any active hostname (the operator already moved the binding to a different cert), it's harmless unbound clutter. Document it in the work record and move on. Managed Certs that aren't actively in use don't auto-renew further and will eventually expire naturally.

This is the default choice in prior rollouts: an old Managed Cert was found bound to nothing, left in place, and documented in the work record — no further action needed.

### Option 2 — Delete via ARM resource ID (REQUIRES pre-check)

If cleanup is required (hygiene or compliance), delete by full ARM resource ID using `az resource delete`. This bypasses the BYOC-specific path that `az webapp config ssl delete` uses.

**Pre-delete safety check is REQUIRED — Managed Cert deletion is destructive.** Before running `az resource delete` against a Managed Cert, confirm zero current hostname bindings reference its thumbprint anywhere in the webspace. Use Query 2 from `resource-graph-queries.md`:

```kql
Resources
| where type =~ 'microsoft.web/sites'
| where subscriptionId == '<sub-guid>' and resourceGroup =~ '<rg>'
| mv-expand sslState = properties.hostNameSslStates
| where tostring(sslState.thumbprint) == '<managed-cert-thumbprint>'
| project app = name, host = tostring(sslState.name)
```

If this returns ANY rows, the Managed Cert is in use — do NOT delete. Either rebind those hostnames to a different cert first (e.g. the new BYOC wildcard) and re-verify zero references, or leave the Managed Cert alone.

When the pre-check passes (zero rows):

```bash
az resource delete --ids \
  "/subscriptions/<sub-guid>/resourceGroups/<rg>/providers/Microsoft.Web/certificates/<cert-name>"
```

Where `<cert-name>` is the value of the `name` field from Resource Graph Query 4 (e.g. `app.example.com-myappservice`).

### Option 3 — Portal

Azure Portal → App Service → TLS/SSL settings (or Certificates) → Managed certificates tab → select the cert → Delete. The Portal handles the API quirk for you. Useful for one-offs but not scriptable.

## When to clean Managed Certs proactively

You usually don't have to. They're harmless if unbound, and they expire on their own. Reasons to clean anyway:

- **Compliance / audit hygiene** — the org wants every webspace's cert inventory to be predictable and minimal.
- **Avoiding confusion** — a leftover ASMC with the same canonical hostname as an active BYOC cert can confuse later operators looking at "which cert is this app using?". Resource Graph Query 2 (binding state) is always authoritative, but if your team will be poking around the Portal, fewer ghost entries is better.

In all other cases: document and move on.

## Detecting Managed Certs in the discovery phase

Add an explicit categorization in your discovery output. After running Query 4, post-process each row:

- If `friendlyName` is empty AND `name` matches the `<hostname>-<app>` pattern → label it "Managed Cert (ASMC)".
- Otherwise it's an uploaded BYOC cert.

This way the operator's plan-presentation table is honest about what each row is and which deletion command to use.
