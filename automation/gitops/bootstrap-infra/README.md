# bootstrap-infra (cluster platform)

Helm chart deployed on **shared lab clusters** via AgnosticV → Argo CD (cluster `ocp4_workload_gitops_bootstrap` → `lightwell-workshop`, this path).

Supports the Lightwell SDLC demo with **shared** GitLab, AAP/EDA, Automation Orchestrator, and TPA. **Nexus and SDLC control plane are per-tenant** — see `../bootstrap-tenant/`.

## Components

| Directory | Service | Namespace |
|-----------|---------|-----------|
| `templates/gitlab/` | GitLab CE | `gitlab` |
| `templates/aap/` | Ansible Automation Platform (Controller + EDA) | `aap` |
| `templates/cnpg/` | CloudNativePG operator (AO Postgres) | `cloudnative-pg` |
| `templates/ao/` | Automation Orchestrator operator + instance | `automation-orchestrator` |
| `templates/rhads/` | RHTPA + RHTAS, Keycloak TPA realm job | `lightwell-tpa`, `lightwell-tas` |
| `templates/quay/` | Red Hat Quay operator/registry | `lightwell-quay` |
| `templates/opencode-image/` | Shared OpenCode BuildConfig → ImageStream → Quay mirror | `lightwell-images` |
| `templates/argocd/` | Argo CD admin password (OpenShift GitOps) | `openshift-gitops` |

**Not included:** Artifactory, Jenkins, SonarQube, Tekton, OpenShift AI, **Nexus** (tenant chart).

## Automation Orchestrator (platform add-on)

AAP channel is **`stable-2.7`**, baseline for
[Automation Orchestrator](https://docs.redhat.com/en/documentation/automation_orchestrator/2026.8/).
AO is the **overall flow controller** for the remediation demo; EDA only filters
Nexus/GitLab events and bridges into AO.

This chart installs (when `orchestrator.enabled=true`, the default):

1. CloudNativePG operator (`certified-operators` / `stable-v1`)
2. AO operator (`redhat-operators` / `stable`), AllNamespaces OperatorGroup
3. Postgres 15 cluster + `orchestrator` / `temporal` / `temporal_visibility` DBs
4. `AutomationOrchestrator` CR with Route host **`ao.<deployer.domain>`**
   (e.g. `ao.apps.cluster-x.dyn.redhatworkshops.io` — not `ao-apps.…`)

Admin password is `admin.password` (same shared lab password as AAP).

Isolation is **per AO project** (AO has no AAP-style organizations — projects
are the equivalent). The tenant chart’s `ao-bootstrap` Job creates
`lightwell-{guid}`, assigns the lab user `project-admin` **only on that
project**, removes them from the built-in `users` group (which would otherwise
expose the shared `default` project), seeds the remediation workflow, and
writes the EDA SA into `automation-orchestrator`. Webhook paths default to
`lightwell-remediation-{start,resume}-{guid}`. Students cannot list other
tenants’ projects or workflows.

Tenant chart defaults derive `AO_BASE_URL` as `https://ao.<deployer.domain>` —
no extra AgnosticV keys beyond the deployer domain you already pass.

```yaml
# bootstrap-tenant — defaults are enough when deployer.domain is set:
sdlc:
  orchestrator:
    enabled: true          # chart default
    # baseUrl: optional override; empty → https://ao.<deployer.domain>
    existingSecret: automation-orchestrator
```

Set `orchestrator.enabled=false` on **infra** to skip AO install; set
`sdlc.orchestrator.enabled=false` on **tenant** for the legacy EDA-owned chain.

## Values

| Key | Purpose |
|-----|---------|
| `deployer.domain` | Ingress domain (`apps.…`) — AO Route = `ao.<domain>` |
| `deployer.storageClass` | PVCs (GitLab, TPA DB, AO Postgres, …) |
| `admin.password` | Shared bootstrap password (AAP, AO admin, AO Postgres, …) |
| `orchestrator.enabled` | Install AO + CNPG (default `true`) |
| `cnpg.*` | CloudNativePG OLM channel/source |

Nexus webhooks and OpenCode Deployments: **`bootstrap-tenant`** chart (no separate SDLC Argo apps).

## Shared OpenCode image (`opencodeImage`)

When `opencodeImage.enabled=true` (default), this chart:

1. Creates namespace `lightwell-images` with ImageStream + BuildConfig (Docker strategy from `rhpds/lw-sdlc-opencode`)
2. After Quay admin init, Sync Job `opencode-image-publish`:
   - ensures public Quay repo `lightwell/sdlc-opencode`
   - `oc start-build` (skipped if ImageStreamTag already exists)
   - `oc image mirror` ImageStream → in-cluster Quay (`:tag` and `:latest`)
3. Grants `system:image-puller` on the ImageStream namespace to `system:serviceaccounts` (lab-wide)

Tenants leave `sdlc.opencodeImage` empty and pull:

`lightwell-quay-lightwell-quay.<deployer.domain>/lightwell/sdlc-opencode:<opencodeImage.tag>`

Bump `opencodeImage.gitRef` + `opencodeImage.tag` together, sync infra (Job re-runs), then align `sdlc.opencodeImageTag` on tenants.

| Key | Purpose |
|-----|---------|
| `opencodeImage.enabled` | Install shared build/publish (default `true`) |
| `opencodeImage.gitRef` / `tag` | Source commit and published tag (keep in sync) |
| `opencodeImage.quayOrg` / `quayRepo` | Quay destination under in-cluster Quay |
| `quay.hostname` | Optional Route host override for publish + docs |

Build needs egress to GitHub, `ghcr.io` (base image), and `mirror.openshift.com` (`oc` client in the Dockerfile).

## Local validation

```bash
helm lint automation/gitops/bootstrap-infra/
helm template lightwell-infra automation/gitops/bootstrap-infra/ \
  --set deployer.domain=apps.example.com \
  --set admin.password=testpass
```

## Expected routes (after sync)

| URL pattern | Component |
|-------------|-----------|
| `https://gitlab-gitlab.<domain>` | GitLab |
| `https://ao.<domain>` | Automation Orchestrator UI |
| `https://sso.<domain>` | Keycloak (cluster) |
| `https://trustify.<domain>` or TPA CR `appDomain` | RHTPA |
| AAP gateway route in `aap` namespace | AAP Controller / EDA |
| Quay registry route in `lightwell-quay` | In-cluster Quay (OpenCode image) |

Per-tenant Nexus: `https://nexus-lightwell-nexus-<guid>.<domain>` (from tenant chart).
