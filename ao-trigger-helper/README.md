# AO trigger helper

Operator tools and notes for **Automation Orchestrator (AO) Path 2** —
EDA → AO canvas → AAP / OpenCode / ServiceNow / TPA on a provisioned tenant.

Scripts fire a Nexus-shaped webhook into EDA (bypassing Nexus upload when
Lightwell Network webhooks are missing) and reset the Acme GitLab apps between
runs. Docs under [`docs/`](docs/) explain the AO flow, tenant architecture, and
live investigation snapshots.

This directory is **not** Showroom student content. Path 1 (Renovate) stays on
the Showroom inject path; only the shared post-merge CI/CD spine overlaps.

## Docs (AO context)

| Doc | Purpose | Read it to… |
|-----|---------|-------------|
| [docs/DEMO-FLOW.md](docs/DEMO-FLOW.md) | Intended **demo narrative** for Path 2 (and how Path 1 shares CI/CD) | Understand component I/O, the current AO canvas (SNOW → TPA → classify → for-each → finalize), policies, and operator gotchas before a run |
| [docs/architecture.md](docs/architecture.md) | **Per-tenant architecture** for an AO-enabled lab | See namespaces, shared vs tenant boxes, Mermaid wiring / sequence, resource names, and where to watch each stage |
| [docs/DEMO-FLOW-INVESTIGATION.md](docs/DEMO-FLOW-INVESTIGATION.md) | Dated **live cluster investigation** vs charts | Check readiness on a real guid (jobs, routes, Nexus webhooks, SCM drift, path blockers) and compare gaps to the intended flow |

Index: [docs/README.md](docs/README.md). Decisions: [ADR-031](../ADR.md#adr-031--showcase-nexus-webhook-trigger-script), [HANDOFF](../HANDOFF.md).

**How they relate:** `architecture.md` is the static wiring picture;
`DEMO-FLOW.md` is the story operators walk; `DEMO-FLOW-INVESTIGATION.md` is
evidence from a specific cluster/date — update the investigation when you
re-probe, and keep DEMO-FLOW / architecture aligned when the canvas changes.

## Prerequisites

- `oc`, `curl`, `git`, `python3` on `PATH`
- Kube context with access to `lightwell-tenant-<guid>` / GitLab root PAT
- Tenant already bootstrapped (`eda-bootstrap` / AO path enabled)

## Trigger AO

```bash
cd ao-trigger-helper

# Human-gated app (wire-transfer-svc → needs_approval)
./trigger-nexus-webhook.sh <guid> needs-approval

# Auto-merge app (benefits-mgmt-app → auto_approve)
./trigger-nexus-webhook.sh <guid> auto-approve

# Both, sequentially (~90s pause between)
./trigger-nexus-webhook.sh <guid> both --watch
```

| Case | Default GAV | Expected app / policy |
|------|-------------|------------------------|
| `needs-approval` | `com.h2database:h2:2.2.224` | `acme-<guid>/wire-transfer-svc` / `needs_approval` |
| `auto-approve` | `org.flywaydb:flyway-core:4.1.2` | `acme-<guid>/benefits-mgmt-app` / `auto_approve` |

Useful flags: `--dry-run`, `--watch`, `--version <full.rhlw-…>`.

Overrides: `EDA_WEBHOOK_ROUTE_URL`, `NEEDS_APPROVAL_GAV`, `AUTO_APPROVE_GAV`
(`group:artifact:baseVersion`).

## Signal CI/CD lifecycle (after merge)

After the student merges in GitLab, POST build/deploy events to EDA so AO
runs the short **build** / **deploy** webhook paths (SNOW bookkeeping). Does
**not** Start a second Nexus remediation:

```bash
./trigger-cicd-signal.sh <guid> build  succeeded acme-<guid>/wire-transfer-svc
./trigger-cicd-signal.sh <guid> deploy healthy   acme-<guid>/wire-transfer-svc
# failures:
./trigger-cicd-signal.sh <guid> build  failed    acme-<guid>/wire-transfer-svc
./trigger-cicd-signal.sh <guid> deploy degraded  acme-<guid>/wire-transfer-svc
```

Requires AAP sync with `ao-lifecycle-webhook.yml` + rulebook rules, and the
webhook-driven AO canvas (ADR-035). Merge itself is only via GitLab UI.

## Reset apps (after a demo)

Re-seeds `acme-<guid>/{wire-transfer-svc,benefits-mgmt-app,report-generator-app}`
from the upstream GitHub sources (same as tenant bootstrap), re-injects
`.lightwell/policy.json`, force-pushes `main`, closes open MRs, and deletes
`update-artifact-*` branches. Does **not** modify GitHub.

```bash
./reset-demo-repos.sh <guid>
./reset-demo-repos.sh <guid> --dry-run
./reset-demo-repos.sh <guid> --app wire-transfer-svc
```

## Notes

- Each trigger stamps a unique `.rhlw-HHMMSS` so Impact does not treat the fix
  as `already_current` after a prior merge — still reset repos between demos
  so students see a real pom bump.
- Do not fire within ~1 minute of a tenant Argo sync (EDA activation restart).
- Auto-approve only loops benefits if TPA’s SBOM lists that GAV; otherwise
  override `AUTO_APPROVE_GAV` or seed the SBOM.
- Trigger bypasses Nexus upload; production path is artifact → Nexus webhook → EDA.
