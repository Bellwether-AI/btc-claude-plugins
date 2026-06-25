---
name: azure-appservice-cert-rollout
description: End-to-end workflow for rolling out a Bring-Your-Own-Certificate (BYOC) TLS certificate to Azure App Services across one or more subscriptions in a tenant. Use this skill whenever the user is renewing, replacing, fixing, or rotating an SSL/TLS certificate on Azure App Services. Trigger on any of these intents — even if the user hasn't said "App Service" yet: renewing or replacing a wildcard cert across multiple Azure web apps, getting a new PFX from GoDaddy / DigiCert / Sectigo / Entrust and needing to push it out, fixing a missing intermediate chain on web app TLS, an expiring cert across multiple subscriptions, "the cert is expiring" + Azure context, rebinding SNI on App Services, manual cert rotation in a managed-services / MSP workflow, or anything mentioning "az webapp config ssl". Also trigger for cleanup of stale cert resources in App Service webspaces.
---

# Azure App Service TLS certificate rollout (BYOC)

This skill walks an operator through a careful, manual, multi-step rollout of an uploaded private certificate (PFX) to one or many Azure App Services across one or many subscriptions. It is built around three hard-earned invariants:

1. **Validate the PFX chain BEFORE upload.** App Service silently accepts a leaf-only PFX. Browsers usually mask the missing chain (they cache common intermediates), so the problem only shows up later, in monitoring, mobile apps, or strict-trust-store clients. There is no portal warning. The pre-flight chain check in Step 2 is the only defense.
2. **Confirm tenant + subscription scope BEFORE any write.** At an MSP one operator's CLI session typically has access to many clients' tenants. The wrong default subscription is a common foot-gun. The skill gates execution on an explicit tenant + sub-list confirmation.
3. **Manual one-step-at-a-time execution.** No bash loops, no `&&`-chained commands, no wrapper scripts. Each step of each app is its own tool call. The operator's documented preference and the lesson from past production multi-target work: the cost of a fast-but-wrong rollout to dozens of production App Services is much higher than the cost of doing the work deliberately.

If you find yourself reaching for a `for` loop, a parallel-execution pattern, or chaining bind+delete on one line — **stop and re-read this invariant**. The skill's whole defense rests on per-step visibility.

## Workflow at a glance

0. **Tenant + scope confirmation** — confirm the signed-in Azure CLI tenant matches the operator's intent, and resolve the subscription scope to a concrete list the operator approves.
1. **Gather remaining inputs** — PFX path, password (via env var, never argv), friendly name, optional extra cleanup thumbprints.
2. **PFX validation** — chain check + subject/SAN + validity. Halt unless the script exits 0.
3. **Discovery** — Resource Graph queries across the approved subscription list to enumerate App Services with custom hostnames, current bindings, ASP SKUs, and existing cert clutter.
4. **Plan presentation** — categorize every in-scope App Service (full renewal / cleanup-only / already clean / intentionally untouched). Operator approves before any write.
5. **Pilot** — one carefully chosen app, full sequence end-to-end, pause for operator review.
6. **Bulk execution** — same sequence, one app at a time, separate tool calls per step. Halt on first failure.
7. **Inline cleanup** — delete the prior cert from each webspace AFTER its binding-verification passes; optionally also clean unrelated stale cert resources.
8. **Final verification** — re-run discovery queries, confirm zero stale targets remain.
9. **Work record** — write a redacted markdown summary to the operator's working directory.

## Step 0 — Tenant + scope confirmation (GATE — no writes before this passes)

Before doing anything else, confirm the right Azure context is loaded:

```bash
az account show --query "{tenantId:tenantId, user:user.name, currentSub:name}" -o json
```

Ask the operator: "**Expected tenant ID is what?** And **expected subscription scope** is what — a name prefix, an explicit list, or a single subscription?" Compare their answer against the `tenantId` returned above. If they do not match, halt. Have the operator either `az login --tenant <expected>` or correct their intent.

Resolve the subscription scope to a concrete sub-list:
- If the operator gave a name prefix: `az account list --query "[?starts_with(name,'<prefix>')].{name:name, id:id}" -o table` — present the resolved list back to them and require explicit "yes that's the right set" before proceeding. Name-prefix matching is brittle (a typo or accidentally-shared prefix between clients could pull in the wrong subs) so the human-eyeball approval is non-negotiable.
- If the operator gave an explicit list of names, resolve names to IDs the same way and present back.

Save the approved list of subscription GUIDs — every subsequent Resource Graph query and write operation must be scoped to this set.

## Step 1 — Gather remaining inputs

Ask only those not already obvious from context:

- **PFX file path** (absolute) on the operator's workstation.
- **PFX password** — ask for it, then immediately set it to the `PFX_PWD` environment variable for the current session: `export PFX_PWD='<password>'`. **Do not pass the password as a positional argument to scripts, do not put it on a command line where `ps` or shell history will capture it, do not write it to disk, and do not echo it back.**
- **Custom hostname domain suffix** to filter on (e.g. `example.com`, `acme.io`). This scopes discovery.
- **Friendly name** for the cert resource in App Service (e.g. `acme-wildcard-2026-27`). Useful to derive from the PFX filename. Avoid reusing a name that's already in some target webspaces unless an in-place overwrite is the intent.
- **Optional: extra stale thumbprints to clean** beyond the cert being replaced — discovery may surface these and the operator decides what to remove.

## Step 2 — PFX validation (GATE — no upload before this passes)

Run the chain validation script:

```bash
PFX_PWD='<password from env, not from operator paste each time>' \
  bash /path/to/skill/references/check_pfx.sh '<pfx-path>' '<hostname-suffix>'
echo "exit code: $?"
```

The script reads the password from `PFX_PWD` to keep it off the command line. Check the exit code:

- **0** — PFX is good. Continue.
- **1** — Chain is missing (leaf-only PFX). **Halt.** Tell the operator they need the certificate authority to re-issue the PFX with the full chain bundled, or to merge the chain themselves with `openssl pkcs12 -export -out new.pfx -inkey key.pem -in leaf.pem -certfile chain.pem`.
- **2** — Couldn't parse PFX (wrong password, corrupted file). Halt and surface the openssl error.
- **3** — Other validation failure (expired, SAN doesn't cover the hostname suffix). Halt and surface the specific issue.

The script also reports the cert's subject, SAN, issuer, validity dates, SHA-1 thumbprint, and per-cert chain walk. Capture the SHA-1 thumbprint — every subsequent verification uses it.

Also confirm with the operator that the cert's SAN actually covers every hostname surfaced by discovery in Step 3. For wildcard certs (`CN=*.example.com`), confirm every in-scope hostname is one label deep under that wildcard (e.g. `app.example.com` is OK, `app.sub.example.com` is not covered by `*.example.com`).

## Step 3 — Discovery via Resource Graph

Read `references/resource-graph-queries.md` and run the four discovery queries, scoping each to the approved sub-list from Step 0. They yield:

1. **App Services with matching custom hostnames** — the inventory.
2. **Per-hostname SSL binding state** — current sslState and current thumbprint per hostname.
3. **App Service Plan SKUs** — confirm every target plan is Basic (B1) or higher (Standard / Premium / Isolated). F1 / D1 / Shared cannot bind certs.
4. **All cert resources in scope** — the full clutter picture (stale leftovers, Managed Certs, multi-thumbprint webspaces).

Present results to the operator as a categorized table. Look for:
- Apps already on the new thumbprint (no binding change needed, may need cleanup).
- Apps on a prior thumbprint (needs full upload + bind).
- Hostnames currently `Disabled` (intentional no-TLS — usually leave alone).
- Cert resources with the new thumbprint already present in some webspaces (someone may have started this work earlier — surface this).
- Stale cert resources from previous rollouts.
- Plans below Basic tier (will block binding — surface and ask the operator to scale them up before continuing).

## Step 4 — Plan presentation (GATE — operator approval required)

Lay out the planned actions and get explicit approval. Categorize every in-scope App Service into:

- **A. Full renewal needed** — needs upload + bind + delete-old.
- **B. Cleanup only** — binding is already on the target thumbprint; just needs the prior cert resource removed.
- **C. Already clean** — already on target cert, no stale resources in webspace, no action.
- **D. Intentionally untouched** — disabled hostnames, hostnames not covered by the new cert SAN, etc.

List unique **webspaces** (sub + RG + region + OS combo) since cert resources are scoped to a webspace and an App Service Plan can host multiple App Services from one upload. Multiple apps in the same webspace share the cert resource.

Get explicit approval before continuing.

## Step 5 — Pilot

Pick **one** target for the first execution. Pilot should exercise the full sequence (upload + bind + verify chain + delete old) so any failure mode shows up before going wide. Good pilot candidates:

- An explicitly named non-prod environment (sandbox / demo / staging).
- One of the apps that needs the full upload+bind treatment — not a cleanup-only candidate (the latter doesn't exercise upload+bind).

**"All targets are production"** is real at MSP clients. If there is no non-prod target: pick the least critical app, agree with the operator on the change window, and proceed knowing the pilot is itself on a prod system.

If the operator wants two pilots — one for the upload+bind pattern, one for the cleanup-only pattern — that's reasonable for first-of-its-kind rollouts.

**Pause after the pilot for operator review.** Do not proceed to bulk without explicit approval.

## Step 6 — Bulk execution (one app at a time — HARD RULE)

**Each step of each app gets its own tool call.** Not a loop, not chained with `&&`, not a wrapper script. The rule is prescriptive, not advisory. If you (the AI) start drafting a `for app in ...` loop or a script that handles "all 20 apps", **stop and surface to the operator that you're about to violate the skill's invariant**. The operator's documented standing preference, and the lesson encoded into this skill, is that untested loops introduce a new failure surface (shell quoting, set-e behavior, error swallowing) on top of whether the per-resource operation itself works. Manual is slower but visible.

The per-app sequence is documented in detail in `references/per-app-procedure.md` (read it before starting bulk). At a glance, it's five separate tool calls per app:

| Step | Command | Validate |
|---|---|---|
| A | `az account set --subscription "<sub>"` | (no failure mode) |
| B | `az webapp config ssl upload ...` (reads `PFX_PWD` env var) | Returned thumbprint matches expected |
| C | `az webapp config ssl bind ...` | hostNameSslStates entry shows new thumbprint, SniEnabled |
| D | `sleep 20`, then `openssl s_client` direct-to-App-Service chain probe | Full chain served (leaf + intermediates + root) |
| E | `az webapp config ssl delete ...` (old thumbprint) | Clean exit (or known "not found" for Managed Certs) |

**Stop-on-first-failure invariant.** If any step on any app fails or returns unexpected output, halt the entire rollout and surface to the operator. Do not continue to step N+1 or app N+1. The operator decides whether to investigate, retry, or roll back.

**Post-bind rollback path for Step D failure.** If the chain probe in Step D shows the wrong chain after a successful bind, the app is now live on the wrong cert. Rollback procedure: re-run Step C with the **prior** thumbprint (it's still in the webspace because Step E hasn't run), confirm the rebind via Resource Graph readback, and halt. Investigate before doing anything else. Do not run Step E for this app — that would delete the only cert you can roll back to.

**Edge propagation delay.** App Service edge takes ~15-30 seconds (empirical, not vendor-documented) between bind and serving the new cert. The 20-second sleep in Step D handles this. If a probe still shows the old cert after 30s, wait another 30s before assuming the bind failed.

**Stopped App Services.** Step D's openssl probe is impossible against a Stopped app. Skip it for those and rely on Step C's Resource Graph readback as the only verification. Control-plane operations (upload, bind, delete) work fine against Stopped apps.

## Step 7 — Inline old-cert cleanup (with webspace-safety pre-check)

Step E is the per-app delete of the prior cert thumbprint from that app's webspace. **Before each delete**, confirm that no other App Service in that webspace still has a binding referencing the prior thumbprint. Query 2 from `resource-graph-queries.md` will tell you. If any sibling app in the same webspace is still bound to the old thumbprint, you must rebind it first (or skip the delete until all siblings have been migrated). Deleting a cert resource that's still in use by some hostname will break that hostname's TLS handshake.

For additional stale cert resources the operator wants cleaned beyond the immediate predecessor — expired certs from previous rollouts, free Managed Certificates, hostname-specific certs no longer in use — run the same `az webapp config ssl delete` pattern, **one webspace at a time**, with the same sibling-binding pre-check.

App Service Managed Certificates need a different deletion path — `az webapp config ssl delete --certificate-thumbprint` returns "Certificate not found" even though they exist. See `references/managed-certs.md`.

## Step 8 — Final verification

After all writes are done, re-run the discovery queries and confirm:

- **Every in-scope hostname's binding** is on the new thumbprint, `sslState=SniEnabled` (or whatever the prior state was), except hostnames the operator explicitly chose to leave Disabled / untouched.
- **Zero cert resources** remain anywhere in scope with any of the thumbprints the operator chose to clean up.
- For one or two sample apps, repeat the direct-App-Service openssl chain probe to confirm the full chain is being served.

If anything fails verification, surface it loudly. Don't claim "done" until the verification matches the plan.

## Step 9 — Work record (with explicit redaction)

Write a markdown summary to the operator's explicit working directory (where they ran the skill from). **Never write to the directory containing the PFX** — that's often a Downloads or sync folder and audit records don't belong alongside private keys. **Never include the PFX password** anywhere in the work record. If you echo any executed command into the record, redact `--certificate-password '...'` to `--certificate-password '<REDACTED>'`. The same applies to environment variable dumps.

Use `references/work-record-template.md` as the structure. Standard naming convention: `certupdate_<descriptor>.md` (matches how prior rollouts were documented).

## Notes and gotchas worth carrying between rollouts

- **`az webapp config ssl upload` accepts a chain-less PFX silently.** The Step 2 chain check is the only defense.
- **Edge propagation delay** of ~15-30 seconds between bind and the new cert being served. Empirical from prior rollouts, not in vendor docs. Sleep 20-30s before the verification probe.
- **App Service Managed Certificates** are stored differently than uploaded BYOC certs; the standard delete command doesn't touch them. See `references/managed-certs.md`.
- **`az webapp config ssl bind --hostname <h>` re-points the existing binding** without dropping it — Microsoft's zero-downtime renewal path. Avoid `ssl unbind` + `ssl bind` for renewals.
- **App Service Plan SKU minimum is Basic (B1)** for SSL bindings. F1 (Free), D1 (Shared) cannot bind certs. Standard, Premium (v2/v3), Isolated all work.
- **Cert resources are webspace-scoped** (sub + RG + region + OS combo). Multiple App Services in the same webspace share uploaded certs — one upload serves all of them.
- **Application Gateway / Front Door / CDN in front of App Services** masks App Service TLS issues from the public internet. A public probe sees the front-door's cert. To probe the App Service directly: `openssl s_client -servername <hostname> -connect <app>.azurewebsites.net:443` (SNI trick).
- **Stopped App Services** still accept control-plane cert operations. Resource Graph readback is the only available verification for those.
- **`az webapp config ssl delete` does not require `--name`** — it's webspace-scoped, identified by `--resource-group` + `--certificate-thumbprint`. Don't add `--name` thinking it's required.
- **Token expiry mid-run** is realistic for 30+ minute rollouts. If you see `InvalidAuthenticationToken`, the operator needs to `az login` again — and you MUST re-confirm tenant context (Step 0) before resuming writes.
- **State drift** between discovery and execution is rare but possible (a new App Service appears in a sub, RBAC changes, a sub gets moved tenants). If significant time elapses between discovery and bulk (~30+ min) re-run Query 2 to confirm current bindings before proceeding.
- **The cryptography deprecation warning** ("Parsed a serial number which wasn't positive...") that `az webapp config ssl upload` sometimes emits is benign — it's a chain cert encoding quirk, not an operation failure. Mentioned in `per-app-procedure.md` so it's not surprising mid-rollout.

## Related references

- `references/check_pfx.sh` — full PFX chain-validation script (Step 2). Pass password via `PFX_PWD` env var.
- `references/resource-graph-queries.md` — all KQL queries used in discovery and verification (Steps 3, 8).
- `references/per-app-procedure.md` — full CLI command reference for the per-app sequence (Step 6), including rollback procedures.
- `references/managed-certs.md` — detecting and handling App Service Managed Certificates.
- `references/work-record-template.md` — structure for the Step 9 markdown work record.
