# azure-appservice-cert-rollout

End-to-end workflow for rolling out a Bring-Your-Own-Certificate (BYOC) TLS certificate to Azure App Services across one or more subscriptions in a tenant.

Designed for the MSP / multi-client case: one operator with access to many tenants and subscriptions, rolling out a renewed wildcard or hostname cert across an arbitrary set of App Services, with the production-safety bias dialed all the way up.

## Why this exists

The straightforward Azure CLI sequence for renewing an uploaded cert (`az webapp config ssl upload` → `bind` → `delete`) has three failure modes that have all caused real downstream pain in prior rollouts:

1. **Silent chain-less PFX.** `az webapp config ssl upload` accepts a leaf-only PFX without warning. Browsers cache common intermediates so the missing chain isn't visible from the operator's laptop, but mobile apps, headless clients, and minimal-trust-store environments fail TLS validation. No portal warning. Catching this post-rollout means doing the rollout again.
2. **Wrong tenant / subscription scope.** MSP operators routinely have CLI access to many clients' tenants. The currently-selected subscription is whichever one was last touched. One mis-targeted command can rebind certs in the wrong client's environment.
3. **Untested batch loops.** Writing a shell loop to "do all 20 apps at once" introduces a new failure surface (shell quoting, set-e behavior, error swallowing) separate from whether the per-resource Azure operation works. The cost of a fast-but-wrong rollout to dozens of production App Services is far higher than the cost of running the same commands 20 times manually.

This skill encodes defenses against all three.

## What the skill does

A 9-step workflow with three operator gates:

1. **Tenant + scope confirmation** (gate) — confirm signed-in tenant matches operator intent, resolve subscription scope to a concrete list and get explicit approval before any write.
2. **Gather remaining inputs** — PFX path, password via `PFX_PWD` env var (never argv), friendly name, optional cleanup thumbprints.
3. **PFX validation** (gate) — chain check + subject/SAN coverage + validity dates via portable openssl script. Halt unless the script exits 0.
4. **Discovery** — Resource Graph queries enumerate hostnames, bindings, ASP SKUs, cert clutter across the approved sub-list.
5. **Plan presentation** (gate) — categorized table (full renewal / cleanup-only / already clean / intentionally untouched), explicit approval before any write.
6. **Pilot** — one app, full sequence end-to-end, pause for review.
7. **Bulk execution** — same sequence per app, separate tool calls per step (no loops), stop-on-first-failure invariant, explicit post-bind rollback path.
8. **Inline cleanup** — delete prior cert from each webspace with a sibling-binding safety pre-check before each delete.
9. **Final verification** — re-run Resource Graph queries, confirm zero stale targets, repeat chain probe on a sample.

Plus a redacted markdown work record at the end.

## The three gates

| Gate | Step | Question |
|------|------|----------|
| G1   | 0    | Tenant + sub list confirmed? |
| G2   | 2    | PFX chain check passed? |
| G3   | 4    | Operator approves the plan? |

The pilot pause (Step 5) is a soft checkpoint, not a hard gate — operator decides whether to continue after seeing pilot results.

## What's in the skill

- `skills/azure-appservice-cert-rollout/SKILL.md` — main workflow, 9 steps, hard invariants up front.
- `skills/azure-appservice-cert-rollout/references/check_pfx.sh` — PFX chain validation for **macOS / Linux / WSL / Git Bash**. Reads password from `PFX_PWD` env var, uses awk for per-cert splitting (no GNU-only csplit flags), shells out to openssl.
- `skills/azure-appservice-cert-rollout/references/check_pfx.ps1` — PFX chain validation for **Windows PowerShell 5.1+ / cross-platform PowerShell 7+**. Same exit codes, native .NET `X509Certificate2Collection` so no openssl dependency. SAN parser handles both Windows-style (`DNS Name=...`) and macOS-style (`DNS:...`) SAN formats.
- `skills/azure-appservice-cert-rollout/references/resource-graph-queries.md` — all KQL queries for discovery and verification, with subscription-list resolution guidance and `--first 1000` on every query (avoids silent truncation on large tenants).
- `skills/azure-appservice-cert-rollout/references/per-app-procedure.md` — full per-app CLI sequence with explicit rollback paths, the sibling-binding pre-delete check, and PFX_PWD env-var setup for bash / PowerShell / cmd.exe.
- `skills/azure-appservice-cert-rollout/references/managed-certs.md` — recognizing and (carefully) cleaning up App Service Managed Certificates.
- `skills/azure-appservice-cert-rollout/references/work-record-template.md` — structure for the Step 9 markdown work record, including required redaction guidance and a paste-friendly plain-text summary block.

## Platform support

Tested on:

- **macOS** (Sequoia / Apple Silicon): bash + PowerShell 7 both pass smoke tests against known-good and known-chain-less PFXes.
- Linux (Ubuntu): bash script tested. PowerShell 7 expected to work identically to macOS.
- Windows: PowerShell 5.1+ and 7+ expected to work; not yet smoke-tested.

Operator picks whichever shell they're comfortable in. Both scripts exit with the same codes and produce equivalent diagnostic output.

## Prerequisites

On the operator's workstation:

- Azure CLI (`az`) signed in to the right tenant
- `resource-graph` extension installed: `az extension add --name resource-graph`
- One of:
  - **bash + openssl + standard POSIX tools** (`awk`, `find`, `sed`, `grep`, `date`) for the `.sh` chain-check, OR
  - **PowerShell 5.1+ or PowerShell 7+** for the `.ps1` chain-check (no openssl needed — uses .NET's native cert handling)

Operator RBAC needs the following on each target App Service Plan's resource group:
- `Microsoft.Web/sites/read` (for discovery)
- `Microsoft.Web/serverfarms/read` (for SKU check)
- `Microsoft.Web/certificates/read` + `write` + `delete` (for cert resources)
- `Microsoft.Web/sites/hostNameBindings/write` (for SNI bindings)

Roughly `Website Contributor` or higher at the subscription / RG level covers all of these.

## Triggers

The skill auto-triggers on phrases like:

- "Renew the wildcard cert across all our Azure web apps"
- "Push the new PFX to the App Services"
- "Fix the cert chain on the App Service"
- "The GoDaddy / DigiCert / Sectigo cert is expiring"
- "Rebind SSL on the web apps"
- Mentions of `az webapp config ssl`
- Multi-tenant or multi-subscription cert rotation in MSP context

## Versioning

Semantic versioning per repo convention. See the root [CHANGELOG.md](../../CHANGELOG.md) for release history.

Initial release: `v0.1.0` (2026-06-25).
