# bootstrap-tenant (per lab user)

Deployed once per tenant order via AgnosticV → Argo CD (`ocp4_workload_gitops_bootstrap` path `automation/gitops/bootstrap-tenant`).

Chart **v0.5.3** provisions T1–T4 plus the **SDLC control plane** (OpenCode, EDA bootstrap, Nexus webhooks, dashboard) in one release. T0 AgnosticV wiring is outside the chart.

## What this chart creates

| Layer | Resources |
|-------|-----------|
| **OpenShift** | `{{ username }}-app`, `lightwell-tenant-<guid>`, `lightwell-nexus-<guid>`, `sdlc-<guid>`; user `edit` on app + nexus NS, `view` on job NS |
| **GitLab** | User, `lightwell` group membership (Maintainer), demo project `lightwell/lw-demo-help-app-<guid>`, MR webhook → EDA (`GITLAB_WEBHOOK_TARGET_URL`) |
| **AAP** | Org `user-<guid>`, tenant user, org membership (best-effort gateway API) |
| **Nexus** | Dedicated instance, Maven repos + EDA webhooks (`nexus-reconcile` Job) |
| **TPA seed** | `trustify-ui` client (direct access + SBOM scopes), per-tenant uploader, demo SBOM upload (`deploy-tpa.yml` parity) |
| **EDA** | `eda-bootstrap` Job — project, decision env, activation `sdlc-remediation-<guid>`, Controller JTs (Start/Resume Orchestrator + worker JTs) |
| **Automation Orchestrator** | Installed by **bootstrap-infra** (one shared instance). AO has **projects**, not AAP orgs — that is the isolation boundary. `ao-bootstrap` creates project `lightwell-{guid}`, grants the student `project-admin` only there, removes them from the built-in `users` group (so they never see the shared `default` project), and uses guid-scoped webhook paths. List APIs hide other tenants’ workflows. |
| **OpenCode** | Deployment + Service in `sdlc-<guid>`; SA `opencode` (verifier RBAC); `GITLAB_PAT` from Job **`sync-gitlab-pat`** → Secret `gitlab-root-pat`; optional LLM via `opencode-llm` / `inject-env-secrets.sh` |
| **Demo dashboard** | Deployment + Service + authenticated Route in `sdlc-<guid>`; Secret references for GitLab, OpenCode/Keycloak, AAP, and Lightwell; sync Jobs copy the shared AAP password and Nexus upstream credentials into the tenant namespace |
| **ServiceNow mock** | Namespace `snow-<guid>`, Deployment + Service + edge Route; lightweight CRUD/UI stand-in for ServiceNow ITSM (`quay.io/redhat-ads-tech/snow-mock:1.0.0`). Source: [`redhat-ads-tech/snow-mock`](https://github.com/redhat-ads-tech/snow-mock) |

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
    existingSecret: redhat-packages-credentials   # preferred: secret created outside git
```

**Lightwell Network credentials (never in git)**

| Where | When |
|-------|------|
| **AgnosticV / RHDP** `ocp4_workload_gitops_bootstrap_helm_values` → `nexus.lightwellNetwork.username/password` | Workshop orders; values live in vault/CI, not the public repo |
| **Pre-created OpenShift Secret** + `nexus.lightwellNetwork.existingSecret: redhat-packages-credentials` | Labs / manual clusters; chart does not render the Secret |
| **Local `.env.secrets`** + `scripts/inject-env-secrets.sh` | Dev clusters; file is gitignored. Lightwell and `OPENAI_API_KEY` are independent — supply either or both |
| **Nothing at all** | Tenant still deploys, degraded — see below |

**Deploying without credentials.** Supplying none of the above is supported: the
chart renders `redhat-packages-credentials` with empty values, and
`nexus-reconcile` skips the two `requires_auth` proxy repos
(`redhat-packages-validated-<guid>`, `redhat-packages-remediated-<guid>`) and
their EDA webhooks, logs `DEGRADED: ...`, and exits 0. Every other wave
completes, so the Argo Application reaches Synced/Healthy. Maven Central, the
hosted release repo, AAP, GitLab, TPA and OpenCode all come up. What does not
work until credentials are added: pulling Lightwell validated/remediated
artifacts, and the Nexus→EDA webhook that drives the remediation flow.

Add them later with `scripts/inject-env-secrets.sh` (above). Note it also flips
the Argo Application to `existingSecret:` refs, which is what stops Argo
reverting the Secret on the next sync — so prefer the script over a bare
`oc create secret`, or make the same `existingSecret` edit yourself.

```bash
# From lightwell-workshop/:
#   cp .env.secrets.example .env.secrets   # gitignored; fill LIGHTWELL_NETWORK_* + OPENAI_API_KEY
# Script sources ${ROOT}/.env.secrets (override with ENV_SECRETS=...)
GUID=<guid> ./automation/gitops/bootstrap-tenant/scripts/inject-env-secrets.sh
```

```bash
NS=lightwell-nexus-<guid>
oc create secret generic redhat-packages-credentials -n "${NS}" \
  --from-literal=username='YOUR_SERVICE_ACCOUNT' \
  --from-literal=password='YOUR_TOKEN'
```

**OpenCode LLM:** same inject script writes `opencode-llm` (`api_key`) in `sdlc-<guid>` and sets `sdlc.llm.existingSecret: opencode-llm` on the Argo Application so the key never lands in git.
For LiteLLM, set the API endpoint (including `/v1`) and model through Helm
values. The token comes from `sdlc.llm.apiKey` in protected Helm values or an
`opencode-llm` Secret selected by `sdlc.llm.existingSecret`. OpenCode receives
an inline provider configuration that references the token environment variable;
the token is not embedded in that configuration.

```yaml
sdlc:
  llm:
    baseUrl: https://litellm.example.com/v1
    model: example-model-id
    existingSecret: opencode-llm  # Secret key: api_key
  dashboard:
    enabled: true
    image: quay.io/bluesman/lightwell-demo-dashboard:v0.5.2
    lightwell:
      url: https://packages.redhat.com/lightwell/java/remediated/
```

The dashboard does not load `.env.secrets` in the cluster or call LiteLLM. It
queries Lightwell Maven metadata directly to show available builds, then fetches
the selected JAR through Nexus. Nexus emits the EDA webhook; AAP, TPA, OpenCode,
and GitLab perform the remaining stages. Nexus gets Lightwell credentials from
`nexus.lightwellNetwork.username/password` in protected Helm values or from
`nexus.lightwellNetwork.existingSecret`. The chart copies that Secret to the
dashboard namespace before the Deployment starts.

The dashboard is **disabled by default** (`sdlc.dashboard.enabled: false`). Its
credential-sync hook runs at sync-wave 3 and polls 10 minutes for the Lightwell
Network Secret before failing; because it is a `Sync` hook it blocks waves 4-5
(`eda-bootstrap`, `nexus-reconcile`) and fails the entire tenant sync. Set
`sdlc.dashboard.enabled: true` only once `nexus.lightwellNetwork` is populated.

Argo Application helm values (only on the cluster / in AgnosticV, not committed):

```yaml
nexus:
  lightwellNetwork:
    existingSecret: redhat-packages-credentials
```

Re-run reconcile after the secret exists: `oc delete job nexus-reconcile -n "${NS}"` and sync the tenant app.

For local `helm template` only (do not commit real passwords), pass `--set nexus.lightwellNetwork.username=... --set nexus.lightwellNetwork.password=...` or use `existingSecret` as above.

```yaml
sdlc:
  enabled: true
  opencodeImage: quay.io/sshaaf/sdlc-opencode:sha-<tag>
```

## SCM vs GitOps

| Repo | Role |
|------|------|
| [`lw-sdlc-opencode`](../../../../lw-sdlc-opencode) | Rulebooks, playbooks, OpenCode agents/skills, container source (`github.com/sshaaf/lw-sdlc-opencode`). Demo A: blast radius → help-app MR — see `docs/DEMO-A-SMOKE.md` |
| **This chart** | All tenant + SDLC Kubernetes/GitOps (Helm only under `automation/gitops/bootstrap-*`) |

Integration ConfigMap `tenant-integration` includes `REMEDIATION_APP_GITLAB_PATH` (default `lightwell/lw-demo-help-app-<guid>`), `TPA_SBOM_LABEL` (`sdlc-demo-<guid>`), `OPENCODE_BASE_URL`, and EDA SCM URL (`sdlc.scmUrl`).

**Help-app GitLab seed:** with `gitlab.helpAppSeed.enabled` (default `true`), Job `create-gitlab-tenant` clones `gitlab.helpAppSeed.sourceRepo` (default `https://github.com/sshaaf/lw-demo-help-app.git` at `sourceRef`, default `main`) and force-pushes that branch into the tenant GitLab project. No app sources are vendored in this chart.


EDA bootstrap script: `files/bootstrap-aap-eda.py`. After SCM changes, re-sync the tenant Argo app or re-run the `eda-bootstrap` Job.

## Validate (after provision)

Run these from the **`lightwell-workshop`** repo root with `oc` logged into the lab cluster and the tenant already synced (GitLab, AAP/EDA, Nexus, OpenCode up).

```bash
GUID=7jtxj-1   # example

# Tenant namespaces / Jobs
./automation/gitops/bootstrap-tenant/scripts/verify-bootstrap-tenant.sh "${GUID}"

# SDLC wiring: OpenCode, EDA activation, webhooks, Controller job templates
./automation/gitops/bootstrap-tenant/scripts/verify-sdlc-flow.sh "${GUID}"

# Optional: HTTP ping to EDA (no remediation jobs)
./automation/gitops/bootstrap-tenant/scripts/verify-sdlc-flow.sh "${GUID}" --smoke

# Optional: fire rule payloads (starts Query TPA / Impact / Verifier jobs)
./automation/gitops/bootstrap-tenant/scripts/verify-sdlc-flow.sh "${GUID}" --smoke --smoke-rules
./automation/gitops/bootstrap-tenant/scripts/verify-sdlc-flow.sh "${GUID}" --cleanup
```

For a full Demo A curl (woodstox → MR), see [`lw-sdlc-opencode/docs/DEMO-A-SMOKE.md`](../../../../lw-sdlc-opencode/docs/DEMO-A-SMOKE.md) and the OpenCode [`README.md`](../../../../lw-sdlc-opencode/README.md#demo-validation-after-provision).

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
