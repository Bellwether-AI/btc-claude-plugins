# Resource Graph queries for App Service cert rollout

These KQL queries are the eyes of this skill — every "what does Azure currently look like" question is best answered by `az graph query` rather than iterating `az webapp` calls per subscription. They run in seconds across hundreds of subs and give consistent results.

All queries take a `<sub-list>` placeholder — a comma-separated list of subscription GUIDs, single-quoted, e.g.:

```
'5690ccb1-dc84-488f-9400-e28c2396c6d9','4cc9fc9a-a368-43a0-b7ea-4f25f6d512b0',...
```

Prerequisite: the `resource-graph` extension (`az extension add --name resource-graph`).

How to resolve subscription scope to a sub-list:
- If the operator gave a name prefix (e.g. "all subs starting with `ROCKETCLAIMS`"), run `az account list --query "[?starts_with(name,'<prefix>')].id" -o tsv` and join with commas+quotes.
- If the operator gave an explicit list of names, look up IDs with `az account list --query "[?name=='<n>'].id" -o tsv`.
- Reuse the same sub-list for every query in this rollout.

---

## Query 1 — App Services with custom hostnames matching the domain suffix

This is the inventory query. It surfaces every web app that has at least one custom hostname ending in `<suffix>` (e.g. `example.com`). Uses `mv-expand` + `endswith` rather than `contains` on the serialized array, so a short suffix can't accidentally substring-match unrelated hostnames.

```kql
Resources
| where type =~ 'microsoft.web/sites'
| where subscriptionId in (<sub-list>)
| mv-expand h = properties.hostNames
| where tostring(h) endswith '<suffix>'
| summarize hostNames = make_set(tostring(h)) by subscriptionId,
                                                 rg = resourceGroup,
                                                 app = name,
                                                 location,
                                                 kind,
                                                 state = tostring(properties.state)
| order by app asc
```

Output for each row: which sub, which RG, app name, location, kind (`app` / `functionapp` / etc.), the matching hostnames as an array, and run state. The state column tells you if any app is `Stopped` so you can plan around it (cert ops still work on Stopped apps, but TLS verification probes won't).

---

## Query 2 — Per-hostname SSL binding state

This flattens the `hostNameSslStates` array so each in-scope hostname becomes its own row with its sslState (`SniEnabled` / `IpBasedEnabled` / `Disabled`) and current thumbprint. This is how you know who's on which cert today.

```kql
Resources
| where type =~ 'microsoft.web/sites'
| where subscriptionId in (<sub-list>)
| mv-expand sslState = properties.hostNameSslStates
| where sslState.name endswith '<suffix>'
| project subscriptionId,
          rg = resourceGroup,
          app = name,
          host = tostring(sslState.name),
          sslState = tostring(sslState.sslState),
          thumbprint = tostring(sslState.thumbprint),
          hostType = tostring(sslState.hostType)
| order by host asc
```

Add a category column to make the table easier to read at a glance — pass the target / known-prior / known-stale thumbprints:

```kql
| extend status = case(
    tostring(sslState.thumbprint) == '<target-thumbprint>', 'NEW',
    tostring(sslState.thumbprint) == '<prior-thumbprint>', 'PRIOR',
    tostring(sslState.thumbprint) == '', 'NO_TLS',
    strcat('OTHER:', substring(tostring(sslState.thumbprint), 0, 8)))
```

---

## Query 3 — App Service Plan SKUs

Every target App Service Plan needs to be **Basic (B1) or higher** for any SSL binding. F1 / D1 / Free / Shared tiers cannot bind certs. Run this query early so you can flag any sub-Basic plans before the rollout starts.

```kql
Resources
| where type =~ 'microsoft.web/serverfarms'
| where subscriptionId in (<sub-list>)
| project subscriptionId,
          rg = resourceGroup,
          plan = name,
          sku = tostring(sku.name),
          tier = tostring(sku.tier)
| order by tier asc, plan asc
```

If any tier is `Free` or `Shared`, that plan needs to be scaled up before the App Services on it can receive a cert binding.

---

## Query 4 — All cert resources in scope (clutter survey)

This reveals every `Microsoft.Web/certificates` resource in the target subs, including the friendly name, thumbprint, expiration, and issuer. It's how you discover stale leftovers (expired certs from previous years, free Managed Certificates, hostname-specific certs) and decide what to clean up.

```kql
Resources
| where type =~ 'microsoft.web/certificates'
| where subscriptionId in (<sub-list>)
| project subscriptionId,
          rg = resourceGroup,
          certName = name,
          friendlyName = tostring(properties.friendlyName),
          thumbprint = tostring(properties.thumbprint),
          expirationDate = tostring(properties.expirationDate),
          issuer = tostring(properties.issuer),
          issueDate = tostring(properties.issueDate),
          canonicalName = tostring(properties.canonicalName)
| order by rg asc, certName asc
```

Adding labels for the target / prior / stale thumbprints makes the operator-facing table immediately scannable:

```kql
| extend label = case(
    thumbprint == '<target-thumbprint>', 'TARGET (new)',
    thumbprint == '<prior-thumbprint>', 'PRIOR (to remove)',
    thumbprint == '<other-stale-thumbprint>', 'STALE (clean up)',
    strcat('OTHER:', substring(thumbprint, 0, 8)))
```

Things to look for in the output:
- **Friendly names that match the new PFX filename pattern but pre-date this rollout** — that's a signal someone already started this work and you may have fewer apps to touch.
- **App Service Managed Certificates** — friendly name is empty, `canonicalName` matches a hostname, `certName` follows the pattern `<hostname>-<appname>`, issuer is often `GeoTrust TLS RSA CA G1` or `DigiCert ...`. These are NOT deletable via `az webapp config ssl delete`. See `managed-certs.md`.
- **Expired certs** — `expirationDate` in the past. These are clutter and safe to delete (nothing should be referencing them).

---

## Final verification queries (Step 8 of the workflow)

### Verification A — every hostname binding is on target

```kql
Resources
| where type =~ 'microsoft.web/sites'
| where subscriptionId in (<sub-list>)
| mv-expand sslState = properties.hostNameSslStates
| where sslState.name endswith '<suffix>'
| extend status = iff(tostring(sslState.thumbprint) == '<target-thumbprint>', 'OK',
                  iff(tostring(sslState.thumbprint) == '', 'NO_TLS', 'WRONG'))
| project status,
          host = tostring(sslState.name),
          app = name,
          sslState = tostring(sslState.sslState),
          thumbprint = tostring(sslState.thumbprint)
| order by status asc, host asc
```

Expected outcome: every row `OK`, except hostnames the operator intentionally left without TLS (those will be `NO_TLS`, sslState `Disabled`).

### Verification B — zero remaining cert resources with the to-remove thumbprints

```kql
Resources
| where type =~ 'microsoft.web/certificates'
| where subscriptionId in (<sub-list>)
| where tostring(properties.thumbprint) in (
    '<prior-thumbprint>',
    '<other-thumbprint-to-clean>'
    /* add more as needed */
  )
| project subscriptionId, rg = resourceGroup, name, thumbprint = tostring(properties.thumbprint)
```

Expected outcome: zero rows. Any row that returns is a cert resource that didn't get cleaned — investigate (commonly: it's a Managed Cert that the standard delete command can't touch).

---

## Tip: how to render in Bash output

`az graph query` returns JSON by default. For human-readable tables in the terminal, append `--query "data" -o table`:

```bash
az graph query --first 1000 -q "<KQL above>" --query "data" -o table
```

For long output you may need `--first 1000` (or higher) to avoid truncation.
