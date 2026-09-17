# bootstrap-tenant (per lab user)

Deployed once per tenant order via AgnosticV → Argo CD (`ocp4_workload_gitops_bootstrap` path `automation/gitops/bootstrap-tenant`).

Chart **v0.4.0** provisions T1–T4 plus the **SDLC control plane** (OpenCode, EDA bootstrap, Nexus webhooks) in one release. T0 AgnosticV wiring is outside the chart.

## What this chart creates

| Layer | Resources |
|-------|-----------|
| **OpenShift** | `{{ username }}-app`, `lightwell-tenant-<guid>`, `lightwell-nexus-<guid>`, `sdlc-<guid>`; user `edit` on app + nexus NS, `view` on job NS |
| **GitLab** | User, `lightwell` group membership (Maintainer), demo project `lightwell/lw-demo-help-app-<guid>` |
| **AAP** | Org `user-<guid>`, tenant user, org membership (best-effort gateway API) |
| **Nexus** | Dedicated instance, Maven repos + EDA webhooks (`nexus-reconcile` Job) |
| **TPA seed** | `trustify-ui` client (direct access + SBOM scopes), per-tenant uploader, demo SBOM upload (`deploy-tpa.yml` parity) |
| **EDA** | `eda-bootstrap` Job — project, decision env, activation `sdlc-remediation-<guid>`, Controller JTs |
| **OpenCode** | Deployment + Service in `sdlc-<guid>`; secrets from tenant password / optional `gitlab.pat` and `sdlc.llm.apiKey` |

Integration URLs (`EDA_WEBHOOK_URL`, `OPENCODE_BASE_URL`, Nexus route, and so on) are rendered into ConfigMap `tenant-integration` in `lightwell-tenant-<guid>` — no separate `cluster-config` overlay.

## Nexus URL

| Use | URL |
|-----|-----|
| Learner / Maven | `https://nexus-lightwell-nexus-<guid>.<ingress-domain>/` (use `oc get route -n lightwell-nexus-<guid>` if host differs) |
| In-cluster reconcile Job | `http://nexus:8081` |

EDA webhook defaults to in-cluster `http://sdlc-remediation-<guid>.<aap-namespace>.svc:5000/`. External GitLab/Nexus use `EDA_WEBHOOK_ROUTE_URL` / `GITLAB_WEBHOOK_TARGET_URL` (defaults: `https://sdlc-remediation-<guid>-<aap-ns>.<ingress>/`).

## Values (from AgnosticV)

```yaml
guid: "{{ guid }}"
username: "user-{{ guid }}"
password: "{{ common_password }}"
deployer:
  domain: "{{ openshift_cluster_ingress_domain }}"
  storageClass: <cluster default or injected>
nexus:
  lightwellNetwork:
    username: ...
    password: ...
sdlc:
  enabled: true
  opencodeImage: quay.io/sshaaf/sdlc-opencode:sha-<tag>
  # namespace: sdlc-control-plane   # only for legacy single-tenant labs
```

## SCM vs GitOps

| Repo | Role |
|------|------|
| [`lw-sdlc-opencode`](../../../../lw-sdlc-opencode) | Rulebooks, playbooks, OpenCode container source (`github.com/sshaaf/lw-sdlc-opencode`) |
| **This chart** | All tenant + SDLC Kubernetes/GitOps (Helm only under `automation/gitops/bootstrap-*`) |

EDA bootstrap script: `files/bootstrap-aap-eda.py`. After SCM changes, re-sync the tenant Argo app or re-run the `eda-bootstrap` Job.

## Validate

```bash
./automation/gitops/bootstrap-tenant/scripts/verify-bootstrap-tenant.sh <guid>
./automation/gitops/bootstrap-tenant/scripts/verify-sdlc-flow.sh <guid>
./automation/gitops/bootstrap-tenant/scripts/verify-sdlc-flow.sh <guid> --smoke --smoke-rules --cleanup
```

```bash
helm lint automation/gitops/bootstrap-tenant/
helm template tenant-test automation/gitops/bootstrap-tenant/ \
  --set guid=demo1 --set username=user-demo1 --set password=test \
  --set deployer.domain=apps.example.com \
  --set nexus.lightwellNetwork.username=x --set nexus.lightwellNetwork.password=y
```

## Reset one tenant

```bash
LIGHTWELL_RESET_GUID=demo1 ./automation/gitops/bootstrap-infra/scripts/reset-lightwell-platform.sh
```

Provisioning plan: [`../TENANT-PROVISIONING.md`](../TENANT-PROVISIONING.md).
