# bootstrap-tenant (per lab user)

Deployed once per tenant order via AgnosticV → Argo CD (`ocp4_workload_gitops_bootstrap` path `automation/gitops/bootstrap-tenant`).

Chart **v0.3.0** provisions T1–T4 in one release (T0 AgnosticV wiring is outside the chart).

## What this chart creates

| Layer | Resources |
|-------|-----------|
| **OpenShift** | `{{ username }}-app`, `lightwell-tenant-<guid>`, `lightwell-nexus-<guid>`; user `edit` on app + nexus NS, `view` on job NS |
| **GitLab** | User, `lightwell` group membership (Maintainer), demo project `lightwell/lw-demo-help-app-<guid>` |
| **AAP** | Org `user-<guid>`, tenant user, org membership (best-effort gateway API) |
| **Nexus** | Dedicated instance, Maven repos + optional EDA webhooks (`nexus-reconcile` Job) |
| **TPA seed** | `trustify-ui` client (direct access + SBOM scopes), per-tenant uploader, demo SBOM upload (`deploy-tpa.yml` parity) |
| **EDA** | `eda-bootstrap` Job — project, decision env, activation `sdlc-remediation-<guid>` in tenant org |

## Nexus URL

| Use | URL |
|-----|-----|
| Learner / Maven | `https://nexus-lightwell-nexus-<guid>.<ingress-domain>/` (OpenShift route host may differ; use `oc get route -n lightwell-nexus-<guid>`) |
| In-cluster reconcile Job | `http://nexus:8081` |

Set `sdlc.edaWebhookUrl` when you know the tenant EDA listener URL (in-cluster Service DNS or Route). Empty value skips Nexus webhook setup; repos are still created.

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
  edaWebhookUrl: ""   # set after first EDA activation or from cluster-config
```

## EDA SCM source (canonical repo)

Rulebooks, playbooks, and `gitops/sdlc-eda/bootstrap-aap-eda.py` live in the **sibling clone** [`lw-sdlc-opencode`](../../../../lw-sdlc-opencode) under `lightwell-demo-lab` (remote `github.com/sshaaf/lw-sdlc-opencode`). Edit there, push `main`, then re-sync the tenant EDA project or re-run `eda-bootstrap`. Chart value `sdlc.scmUrl` points at that GitHub URL.

## Validate

```bash
./automation/gitops/scripts/verify-bootstrap-tenant.sh <guid>
./automation/gitops/scripts/verify-sdlc-flow.sh <guid>           # OpenCode + EDA + webhooks + JTs
./automation/gitops/scripts/verify-sdlc-flow.sh <guid> --smoke --smoke-rules --cleanup  # optional end-to-end probe
```

```bash
helm lint automation/gitops/bootstrap-tenant/
helm template tenant-test automation/gitops/bootstrap-tenant/ \
  --set guid=demo1 --set username=user-demo1 --set password=test \
  --set deployer.domain=apps.example.com \
  --set nexus.lightwellNetwork.username=x --set nexus.lightwellNetwork.password=y

./automation/gitops/scripts/verify-bootstrap-tenant.sh demo1
```

## Reset one tenant

```bash
LIGHTWELL_RESET_GUID=demo1 ./automation/gitops/scripts/reset-lightwell-platform.sh
```

## SDLC layer

Optional Argo apps from `lw-demo-test-agents`: see [`argocd-application-sdlc-tenant.yaml.example`](../argocd-application-sdlc-tenant.yaml.example).

Provisioning order: [`TENANT-PROVISIONING.md`](../TENANT-PROVISIONING.md).
