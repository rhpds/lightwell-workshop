# bootstrap-infra (cluster platform)

Helm chart deployed on **shared lab clusters** via AgnosticV → Argo CD (cluster `ocp4_workload_gitops_bootstrap` → `lightwell-workshop`, this path).

Supports the **lw-demo-test-agents** remediation loop with **shared** GitLab, AAP/EDA, and TPA. **Nexus is per-tenant** — see `../bootstrap-tenant/`.

## Components

| Directory | Service | Namespace |
|-----------|---------|-----------|
| `templates/gitlab/` | GitLab CE | `gitlab` |
| `templates/aap/` | Ansible Automation Platform (Controller + EDA) | `aap` |
| `templates/rhads/` | RHTPA + RHTAS, Keycloak TPA realm job | `lightwell-tpa`, `lightwell-tas` |
| `templates/quay/` | Red Hat Quay operator/registry | `lightwell-quay` |
| `templates/argocd/` | Argo CD admin password (OpenShift GitOps) | `openshift-gitops` |

**Not included:** Artifactory, Jenkins, SonarQube, Tekton, OpenShift AI, **Nexus** (tenant chart).

## Values

| Key | Purpose |
|-----|---------|
| `deployer.domain` | Ingress domain |
| `deployer.storageClass` | PVCs (GitLab, TPA DB, …) |
| `admin.password` | Shared bootstrap password (AAP admin, TPA DB, Keycloak walker secret) |

Nexus repo/webhook reconcile: `lw-demo-test-agents/gitops/nexus/` **per tenant** after `bootstrap-tenant` sync.

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
| `https://sso.<domain>` | Keycloak (cluster) |
| `https://trustify.<domain>` or TPA CR `appDomain` | RHTPA |
| AAP gateway route in `aap` namespace | AAP Controller / EDA |

Per-tenant Nexus: `https://nexus-lightwell-nexus-<guid>.<domain>` (from tenant chart).
