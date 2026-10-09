# Architecture Decision Records

Decisions that shape the Lightwell demo platform. Keep this file **in sync with
[HANDOFF.md](HANDOFF.md)**: when you add, change, or close a Handoff item that
implies an architectural choice, update (or add) the matching ADR here in the
same change.

- **HANDOFF.md** — short operational list (what’s done / next / gotchas).
- **ADR.md** — why we chose it (context, decision, consequences).

Last synced with HANDOFF: 2026-10-09

---

## Template for future ADRs

Copy and fill for each new decision:

```markdown
## ADR-NNN — Short title

| Field | Content |
|-------|---------|
| **Date** | YYYY-MM-DD |
| **Title** | |
| **Context** | |
| **Decision** | |
| **Consequences** | |
```

---

## ADR-001 — Optional Lightwell Network credentials

| Field | Content |
|-------|---------|
| **Date** | 2026-10-07 |
| **Title** | Tenant sync must succeed without Lightwell Network credentials |
| **Context** | Real Lightwell Maven credentials are often missing at provision time. Requiring them blocked Nexus Secret creation and failed the whole tenant Argo sync. |
| **Decision** | Nexus Secret fields are not `required`. `nexus-reconcile.py` skips repos it cannot create instead of exiting 1. Credentials may be injected later via `automation/gitops/bootstrap-tenant/scripts/inject-env-secrets.sh`. |
| **Consequences** | Tenants come up green without Lightwell. Validated/remediated proxy repos may be absent until secrets are injected. Prefer loud failure only when credentials *are* present but invalid. |

## ADR-002 — Dashboard off by default

| Field | Content |
|-------|---------|
| **Date** | 2026-10-07 |
| **Title** | Disable the demo dashboard unless explicitly enabled |
| **Context** | The dashboard’s credential-sync hook at sync-wave 3 could poll/fail and block waves 4–5 (`eda-bootstrap`, `nexus-reconcile`), failing the tenant sync. |
| **Decision** | `sdlc.dashboard.enabled` defaults to `false`. Enable only when `nexus.lightwellNetwork` is populated and the hook is safe. |
| **Consequences** | Default path has one fewer failure mode. Operators who want the dashboard must opt in and own the Lightwell secret lifecycle. |

## ADR-003 — EDA job templates scoped per AAP organization

| Field | Content |
|-------|---------|
| **Date** | 2026-10-07 |
| **Title** | Create SDLC job templates per tenant AAP organization |
| **Context** | Template names are unique per organization, not Controller-wide. A Controller-wide “already exists” check let the first tenant win; later tenants skipped creation while EDA resolved JTs by `(name, organization)` and failed. |
| **Decision** | `bootstrap-aap-eda.py` lists/creates job templates filtered by the tenant’s Controller organization id. All five templates (Start/Resume Orchestrator + Query TPA / Impact / MR Verifier) are ensured in that org. |
| **Consequences** | Multi-tenant shared clusters work. Older tenants provisioned before the fix may still lack JTs and need a bootstrap re-run. |

## ADR-004 — Unattended OpenCode tool permission

| Field | Content |
|-------|---------|
| **Date** | 2026-10-07 |
| **Title** | Set OpenCode permission to allow for EDA-driven agents |
| **Context** | OpenCode defaults bash (and other tools) to `ask`. In a headless pod driven by EDA/AAP there is no operator to answer prompts, so the agent hangs forever. |
| **Decision** | Chart default `sdlc.opencodePermission: allow` (wired into the OpenCode deployment). **Agent-level permission in the image's `/app/opencode.json` overrides this** — that file is loaded *after* `OPENCODE_CONFIG_CONTENT`, so the chart cannot reach it. Every agent that runs headless must therefore also carry `bash."*": "allow"` in `rhpds/lw-sdlc-opencode`'s `opencode.json`. |
| **Consequences** | Agents can run the remediation pipeline unattended. Broader tool allowlist increases blast radius inside the sandbox; rely on sandbox RBAC and skill permissions for containment. The chart-level knob alone is **not** sufficient — verified on tenant `8vjv7` (2026-10-09), where `impact-analyzer` still had `bash."*": "ask"` and parked on a prompt nobody could answer while AAP reported every job successful. Fixed by [lw-sdlc-opencode#4](https://github.com/rhpds/lw-sdlc-opencode/pull/4). |

## ADR-005 — Per-tenant sandbox namespaces

| Field | Content |
|-------|---------|
| **Date** | 2026-10-07 |
| **Title** | Isolate OpenCode / MR-verifier sandboxes per guid |
| **Context** | A shared `sdlc-sandboxes` namespace let tenants interfere with each other and did not match multi-tenant RBAC. |
| **Decision** | Sandbox namespace `sdlc-sandboxes-<guid>` and ephemeral prefix `pr-test-mr-<guid>`. Agent prompts read `SDLC_SANDBOX_NAMESPACE` / `EPHEMERAL_NS_PREFIX` from the environment (`lw-sdlc-opencode` #3). |
| **Consequences** | OpenCode images must honor those env vars; older images that hardcode `sdlc-sandboxes` are unsupported. Chart pins an image known to carry the prompts. |

## ADR-006 — LiteLLM model alias for MaaS

| Field | Content |
|-------|---------|
| **Date** | 2026-10-07 |
| **Title** | Use MaaS model alias `qwen3-235b` |
| **Context** | The upstream model name `qwen3-235b-a22b` is rejected by the RHDP MaaS / LiteLLM gateway. AgnosticV wires per-tenant virtual keys (14d). |
| **Decision** | Use the gateway alias `qwen3-235b` as the configured model id (`litellm/{model}`). |
| **Consequences** | Docs and AgnosticV must not advertise the rejected upstream name. Key rotation / TTL is owned by the litellm_virtual_keys role. |

## ADR-007 — EDA rulebook selected by Orchestrator flag

| Field | Content |
|-------|---------|
| **Date** | 2026-10-08 |
| **Title** | Toggle AO vs legacy remediation via `sdlc.orchestrator.enabled` |
| **Context** | Two rulebooks exist: legacy EDA owns Query TPA → Impact → MR Verifier; AO path makes EDA a sensor (Start/Resume Orchestrator) and AO owns the canvas. Choosing the wrong rulebook without AO credentials fails the first event. |
| **Decision** | Helper `edaRulebookName` / `rulebookName`: `orchestrator.enabled=true` → `sdlc-remediation.yml`; `false` → `sdlc-remediation-legacy.yml`. Override only via explicit `sdlc.rulebookName`. Tenant AO knobs live under `sdlc.orchestrator` (not a separate `sdlc.ao` block). |
| **Consequences** | Enabling AO without a working AO install/SA secret yields loud bootstrap/runtime failures (preferred over silent no-op). Legacy remains a supported fallback. |

## ADR-008 — Automation Orchestrator on the shared platform

| Field | Content |
|-------|---------|
| **Date** | 2026-10-08 |
| **Title** | Install AO (+ CNPG) in bootstrap-infra; isolate tenants in AO projects |
| **Context** | Students need a visible orchestration canvas and per-tenant isolation. Shared AAP/EDA alone does not give per-user workflow UI isolation. |
| **Decision** | `bootstrap-infra` installs Automation Orchestrator (operator CR, Route `ao.<domain>`, CNPG Postgres). Per tenant, `ao-bootstrap` creates AO project `lightwell-{guid}`, local user, EDA service account, AAP credential + global AAP integration, and publishes the **Lightwell Remediation** workflow (Query TPA → condition → Impact; resume → MR Verifier) with guid-scoped webhook paths. |
| **Consequences** | AO must allowlist the AAP Route hostname (`APP_INTEGRATION_URL_ALLOWED_HOSTS` / workflow HTTP allowlist) when the Route resolves to a private IP, or integration create fails SSRF checks. SCM must include Start/Resume + worker playbooks (`rhpds/lw-sdlc-opencode`). |

## ADR-009 — SDLC SCM at rhpds/lw-sdlc-opencode

| Field | Content |
|-------|---------|
| **Date** | 2026-10-08 |
| **Title** | Single SCM URL for EDA rulebooks and Controller playbooks |
| **Context** | Rulebooks and playbooks must stay versioned together. Forks (personal GitHub, blues-man) drifted and broke AO playbooks. |
| **Decision** | Default `sdlc.scmUrl: https://github.com/rhpds/lw-sdlc-opencode.git` for both the EDA project and the Controller playbooks project. |
| **Consequences** | Chart and Argo overrides must not silently point at personal forks. Playbook/rulebook changes land via PR to `rhpds/lw-sdlc-opencode`. |

## ADR-010 — OpenCode image pin (hand-built tag)

| Field | Content |
|-------|---------|
| **Date** | 2026-10-08 |
| **Title** | Pin OpenCode to a known-good hand-built image while CI is broken |
| **Status** | Superseded by [ADR-013](#adr-013--shared-opencode-image-build-to-openshift-integrated-registry) for lab clusters with bootstrap-infra image build |
| **Context** | GitHub Actions on `rhpds/lw-sdlc-opencode` fails at `startup_failure` with no jobs since 2026-10-07. Chart needs the per-tenant sandbox prompts (ADR-005). |
| **Decision** | Pin `sdlc.opencodeImage` to `quay.io/bluesman/sdlc-opencode:sha-5e19550` (built from `lw-sdlc-opencode` `main` @ `5e19550`). Treat as temporary until CI publishes tags again. |
| **Consequences** | Quay org mismatch vs repo variable `QUAY_IMAGE_NAME` (`quay.io/sshaaf/...`). Rebuild/repoint when CI is healthy; document which org is canonical. |

## ADR-011 — Prefer fail-closed over fail-open

| Field | Content |
|-------|---------|
| **Date** | 2026-10-07 |
| **Title** | Loud failure at render/bootstrap over green sync that does nothing |
| **Context** | Multiple bugs reported success while leaving tenants non-functional (missing JTs, empty AO canvas, hung agents). |
| **Decision** | Prefer assert/fail at Helm render or bootstrap Job time when required wiring is incomplete. Hook Jobs use `hook-delete-policy: HookSucceeded` — absence means success. |
| **Consequences** | Sync may show red more often; debugging is clearer. Do not “fix” missing Jobs after HookSucceeded. |

## ADR-012 — Renovate for deterministic remediation

| Field | Content |
|-------|---------|
| **Date** | 2026-10-08 |
| **Title** | Use the Renovate operator for non-AI deterministic remediation |
| **Context** | The workshop primarily showcases AI-driven remediation (OpenCode / Deep Agent). A second path demonstrates deterministic (non-AI) remediation using Renovate to bump Lightwell `rhlw` rebuild versions. The real Lightwell Maven repository (`packages.redhat.com`) requires customer credentials; the workshop seeds a per-tenant Nexus `lightwell-java-remediated` repo with fake `.rhlw-*` artifacts instead. |
| **Decision** | Install the Renovate operator at cluster level (`bootstrap-infra`) via an ArgoCD child Application pointing at the upstream OCI Helm chart (`ghcr.io/mogenius/helm-charts/renovate-operator`). CRDs use `mode: template` (not hook Jobs) to avoid OpenShift SCC issues. The operator SA gets `nonroot-v2` SCC. Per-tenant infrastructure (SA, SCC ClusterRoleBinding, `renovate-token` secret) is deployed by `bootstrap-tenant`. The RenovateJob CR is **not** in the chart — the student creates it on demand from the Showroom lab guide. The repo's `renovate.json` uses the upstream `lightwell-experience/renovate-config:java-remediated` preset via `extends`, with `hostRules` and `packageRules` overriding the registry to point at the tenant's Nexus. |
| **Consequences** | Renovate runs only when the student triggers it (no premature MRs during the AI module). The Renovate operator image runs as uid 12021 — executor pods need the `renovate-runner` SA with `nonroot-v2` SCC. The `lightwell-java-remediated` Nexus repo must be seeded with fake `.rhlw-*` artifacts during provisioning (not yet automated). The upstream preset uses `managerFilePatterns` which requires Renovate v44+; the RenovateJob image must be pinned accordingly. |

## ADR-013 — Shared OpenCode image build → OpenShift integrated registry

| Field | Content |
|-------|---------|
| **Date** | 2026-10-08 |
| **Title** | Build OpenCode once on the platform; tenants pull from the integrated registry |
| **Context** | External quay.io pins (ADR-010) and broken GH Actions make labs brittle. In-cluster Quay is often unavailable or slow on lab clusters. Tenants should not each rebuild the same control-plane image. |
| **Decision** | `bootstrap-infra` owns a shared BuildConfig + ImageStream in `lightwell-images` (source `rhpds/lw-sdlc-opencode` @ pinned `gitRef`). Sync Job `opencode-image-publish` runs `oc start-build` into that ImageStream. Tenants leave `sdlc.opencodeImage` empty and resolve `image-registry.openshift-image-registry.svc:5000/lightwell-images/sdlc-opencode:<tag>`. Lab-wide `system:image-puller` on `lightwell-images` lets every tenant SA pull. |
| **Consequences** | Infra sync waits on first build (egress to GitHub/ghcr/mirror.openshift.com). No dependency on Quay for OpenCode. Bump `opencodeImage.gitRef` + `tag` and tenant `sdlc.opencodeImageTag` together. Override `sdlc.opencodeImage` still allowed for offline/dev. |

## ADR-014 — App-of-apps infra pattern

| Field | Content |
|-------|---------|
| **Date** | 2026-10-08 |
| **Title** | Refactor bootstrap-infra into an app-of-apps pattern |
| **Context** | The monolithic infra chart (56 templates, single ArgoCD Application) was hard to debug — a failure in any component blocked the entire sync. Components like Quay and AO have slow hook Jobs that serialized unnecessarily. |
| **Decision** | `bootstrap-infra` becomes an app-of-apps chart that renders 8 child ArgoCD Application CRs, each pointing at a standalone Helm subchart under `automation/gitops/cluster/`. Sync-wave ordering on Application CRs: cnpg (-3), keycloak (-2), rhads (-1), gitlab+aap (0), quay (1), opencode-image (2), ao (3). Renovate stays as an existing child Application (OCI chart). Values flow from parent to children via `helm.valuesObject`. |
| **Consequences** | 10 ArgoCD apps total (parent + 8 children + renovate-operator). Each component independently syncable and debuggable. GitLab, AAP, and Quay sync in parallel, reducing total provision time. No AgnosticV changes — `repo_path` stays `automation/gitops/bootstrap-infra`. Sync-waves on Application CRs control creation order but do not guarantee child health before the next wave starts — components with cross-dependencies rely on internal retry logic. |

## ADR-015 — Per-tenant GitLab groups with Acme apps

| Field | Content |
|-------|---------|
| **Date** | 2026-10-08 |
| **Title** | Isolate tenants in per-tenant GitLab groups with three sample apps |
| **Context** | The shared `lightwell` group exposed all tenant projects to each other. The single `lw-demo-help-app` from a personal GitHub repo (`sshaaf/lw-demo-help-app`) didn't reflect a realistic multi-app portfolio. The workshop narrative needs high-risk and low-risk apps to demonstrate remediation priority. |
| **Decision** | Replace the shared `lightwell` group with per-tenant `acme-{guid}` groups (private, Maintainer access for `user-{guid}`). Three Acme Inc. sample apps seeded from `redhat-ads-tech/` GitHub org: `wire-transfer-svc` (high risk, AI remediation target), `benefits-mgmt-app` (low risk), `report-generator-app` (low risk, Renovate target). `gitlab.appSeeds` is a configurable list in `values.yaml`. `REMEDIATION_APP_GITLAB_PATH` points to `wire-transfer-svc`. A dedicated `renovate-bot` GitLab user with per-tenant PAT is created for Renovate MRs. |
| **Consequences** | Tenants only see their own apps. `discoveryFilters` for Renovate scopes naturally to `acme-{guid}/*`. EDA webhook set only on `wire-transfer-svc`. Existing AO/EDA/dashboard wiring unchanged — reads from `demoProjectPath` helper. Apps have intentional vulnerabilities and each repo contains a `renovate.json` with the Lightwell preset + placeholder `hostRules`. |

---

## Mapping to HANDOFF.md

| Handoff theme | ADR |
|---------------|-----|
| No Lightwell credentials / inject later | ADR-001 |
| Dashboard off by default | ADR-002 |
| EDA JTs per org | ADR-003 |
| `opencodePermission: allow` | ADR-004 |
| Per-tenant sandboxes | ADR-005 |
| LiteLLM `qwen3-235b` | ADR-006 |
| Rulebook from `orchestrator.enabled` | ADR-007 |
| AO infra + tenant canvas | ADR-008 |
| SCM `rhpds/lw-sdlc-opencode` | ADR-009 |
| OpenCode image / Quay / CI | ADR-010 (superseded on-lab by ADR-013) |
| Fail-open gotcha | ADR-011 |
| Renovate for deterministic remediation | ADR-012 |
| Shared OpenCode build → integrated registry | ADR-013 |
| App-of-apps infra pattern | ADR-014 |
| Per-tenant GitLab groups with Acme apps | ADR-015 |
| Fake Lightwell / AgnosticV credentials | _(no ADR yet — planned, not decided)_ |
| Spec outlines still say Artifactory… | _(content debt, not an ADR)_ |
