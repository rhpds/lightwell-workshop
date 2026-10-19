# Architecture Decision Records

Decisions that shape the Lightwell demo platform. Keep this file **in sync with
[HANDOFF.md](HANDOFF.md)**: when you add, change, or close a Handoff item that
implies an architectural choice, update (or add) the matching ADR here in the
same change.

- **HANDOFF.md** — short operational list (what’s done / next / gotchas).
- **ADR.md** — why we chose it (context, decision, consequences).

Last synced with HANDOFF: 2026-10-19 (ADR-039 Merged+Build poll PaC)

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
| **Consequences** | Infra sync waits on first build (egress to GitHub/ghcr/mirror.openshift.com). No dependency on Quay for OpenCode. Override `sdlc.opencodeImage` still allowed for offline/dev. **A version bump touches six files, not three** — missing the helper default silently pins tenants to the old image: `bootstrap-infra/values.yaml`, `cluster/opencode-image/values.yaml` (`gitRef` + `tag`), `bootstrap-tenant/values.yaml` (`sdlc.opencodeImageTag`), `bootstrap-tenant/templates/_helpers.tpl` (fallback default), `bootstrap-infra/scripts/verify-bootstrap-infra.sh`, and `bootstrap-tenant/README.md`. |

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

## ADR-016 — Trigger artifacts must be declared dependencies of a seeded app

| Field | Content |
|-------|---------|
| **Date** | 2026-10-09 |
| **Title** | Only publish Lightwell rebuilds that some Acme app declares directly |
| **Context** | The chain starts when a `.rhlw-*` artifact is cached in the tenant Nexus proxy. TPA then matches affected repos from the SBOM, and `impact-analyzer` bumps the version in `pom.xml`. SBOM matching is broader than the pom: on tenant `8vjv7`, `jackson-databind` matched `wire-transfer-svc` via `sbom_label_and_dependency_coordinate`, but that pom declares struts / h2 / commons-dbcp and no jackson. The agent ran correctly and died on `ERROR: dependency com.fasterxml.jackson.core:jackson-databind not found in pom.xml`. Re-running with `com.h2database:h2:2.2.219.rhlw-00001`, which `wire-transfer-svc` does declare, produced MR !1 immediately. |
| **Decision** | The demo trigger set is restricted to artifacts that at least one seeded Acme app declares **directly** in its `pom.xml`. The fake-Lightwell mirror seeds exactly those coordinates, and Showroom instructs students to trigger with one of them. |
| **Consequences** | Pairs the mirror contents to the app poms — changing either side requires changing the other. Today only `com.h2database:h2` qualifies (upstream has no `org/apache/struts/`), so `benefits-mgmt-app` and `report-generator-app` need either matching rebuilds or pom changes before they can be remediation targets. Handling transitive-only findings would need `dependencyManagement` support in `gitlab_api.py bump-maven-mr`; out of scope for now. |

## ADR-017 — Keyless signing via TAS + Tekton Chains

| Field | Content |
|-------|---------|
| **Date** | 2026-10-12 |
| **Title** | Use Trusted Artifact Signer (TAS) with Tekton Chains for keyless container signing |
| **Context** | The workshop platform needs a supply-chain security story. Static key signing requires long-lived credentials and key rotation overhead. TAS is the Red Hat-supported Sigstore distribution (Fulcio, Rekor, CTLog, TSA, TUF). |
| **Decision** | Install OpenShift Pipelines (channel `pipelines-1.24`) via the `rhads` ArgoCD child app. Configure Tekton Chains for keyless signing using the cluster Kubernetes OIDC issuer for Fulcio certificate issuance and Rekor for transparency logging. Keycloak provides OIDC for human/email workflows via a dedicated `trusted-artifact-signer` client. TAS namespace changed from `lightwell-tas` → `trusted-artifact-signer`. A PostSync Job (`tektonconfig-patch-job`) patches TektonConfig and updates the Chains InstallerSet audience to `trusted-artifact-signer`. Keycloak OIDC client is configured by a Sync Job (`rhtas-keycloak-setup`). |
| **Consequences** | No long-lived signing credentials in the cluster. If the Chains audience patch fails (InstallerSet race), signing is misconfigured silently — the PostSync Job now validates the patch applied and warns if not. The `rhtas-setup` SA is scoped to a namespaced Role reading only `keycloak-initial-admin` (not a ClusterRole). ClusterInterceptor binding is scoped to `system:serviceaccounts:openshift-pipelines` — EventListeners in tenant namespaces that need ClusterInterceptors require an additional binding. |

## ADR-018 — Per-tenant TPA via Helm chart

| Field | Content |
|-------|---------|
| **Date** | 2026-10-12 |
| **Title** | Deploy TPA per tenant via upstream Helm chart, not a shared operator instance |
| **Context** | TPA does not support multi-tenancy — all users see each other's SBOMs, advisories, and vulnerability data. The original cluster-level deployment via the `rhtpa-operator` gave every tenant a shared view, which is unsuitable for a workshop where each student should see only their own analysis results. The dev-days project proved a per-tenant TPA pattern using the upstream Helm chart deployed as a nested ArgoCD Application per user. |
| **Decision** | Remove the `rhtpa-operator` subscription and shared `TrustedProfileAnalyzer` CR from the `rhads` cluster chart. Deploy TPA per tenant using the upstream `redhat-trusted-profile-analyzer` Helm chart (from `charts.openshift.io`) as a nested ArgoCD Application rendered by the tenant chart. Each tenant gets: namespace `tpa-{guid}` with its own PostgreSQL, S3 bucket (ObjectBucketClaim via NooBaa), TPA server, importer, and a short-URL Route (`tpa-{guid}.{domain}`). RHDA backend is optional (`tpa.rhda.enabled`). Keycloak OIDC clients (`tpa-frontend` public, `tpa-cli` confidential) are created once at cluster level in the `sso` realm by `job-tpa-keycloak-setup.yaml`. All tenants share these clients; data isolation comes from each tenant having its own TPA server and database. Default client scopes grant `create:document`, `read:document`, `update:document` to all users; `delete:document` is optional and requires the `tpa-admin` realm role. The `tpa-cli` client secret is stored in the `keycloak` namespace and copied into each tenant's namespace by a per-tenant OIDC setup Job. |
| **Consequences** | Each tenant consumes ~3 CPU, 12Gi memory (TPA server + PostgreSQL + importer), plus ~1 CPU, 2Gi if RHDA is enabled. Clusters must be sized for N × these resources. The `rhtpa-operator` is no longer installed — TPA is deployed purely via Helm. The old `trusted-profile-analyzer` Keycloak realm and its dot-separated scopes (`create.sbom`, etc.) are replaced by the shared `sso` realm with colon-separated scopes (`create:document`, etc.). Existing AgnosticV catalog items that create users in the old realm need updating. The per-tenant TPA templates live in `bootstrap-tenant/templates/tpa/` (not a Helm subchart) because Helm subchart value scoping prevents the parent's `guid` from reaching the subchart without changes to AgnosticV. A demo dataset is uploaded per tenant via a Job at sync-wave 3 using `tpa-cli` client credentials. |

## ADR-019 — OCI container registry in per-tenant Nexus

| Field | Content |
|-------|---------|
| **Date** | 2026-10-13 |
| **Title** | Add OCI hosted repository to per-tenant Nexus for container image storage |
| **Context** | Tekton build pipelines need to push container images to a per-tenant registry. Nexus already runs per tenant for Maven artifacts. Adding OCI support to Nexus keeps all build artifacts (JARs + images) in one tool per tenant, avoids deploying a separate registry, and gives each tenant isolated image storage. |
| **Decision** | Add OCI registry support to the existing per-tenant Nexus: a Docker Bearer Token Realm, an OCI hosted repository (`oci`) on port 5000, a dedicated OCI Route (`nexus-oci-{guid}.{domain}`), and a short-URL Route for the Nexus UI (`nexus-{guid}.{domain}`). The `nexus-reconcile.py` script creates the OCI repo and enables the token realm idempotently. Storage increased from 20Gi to 50Gi. Authentication: anonymous read, admin credentials for push (reusing the existing Nexus admin Secret). Nexus bumped from 3.76.1 to 3.96.4-ubi for native OCI 1.1 referrers support (needed for Tekton Chains attestation storage without tag-based fallback). The reconcile script accepts the Community Edition EULA automatically (required since 3.77). |
| **Consequences** | Each tenant's Nexus PVC grows from 20Gi to 50Gi. Existing tenants keep the old PVC size unless manually expanded. The OCI Route uses edge TLS termination — pipeline `buildah` tasks must set `TLSVERIFY=false` or trust the cluster CA. The port name `oci-http` replaces the old `http` on the StatefulSet/Service (existing port 8081 renamed to `nexus-http`). Nexus 3.77+ (Community Edition) has a 40,000-component limit and 100,000 requests/day — sufficient for workshop use. The EULA must be accepted before any API calls work; the reconcile script handles this idempotently. |

## ADR-020 — Pipelines-as-Code for per-tenant build pipelines

| Field | Content |
|-------|---------|
| **Date** | 2026-10-14 |
| **Title** | Use Pipelines-as-Code with per-tenant Repository CRs for automated builds |
| **Context** | Each tenant has 3 Java app repos in GitLab that need automated build pipelines triggered on merge to `main`. The pipeline must build the app (Maven), build a container image with OCI labels (for SBOM source tracking), push to the tenant's Nexus OCI registry, generate an SBOM with syft, and upload the SBOM to the tenant's TPA. Pipeline definitions must live in the repo (`.tekton/`) so students can see and modify them. |
| **Decision** | Use Pipelines-as-Code (PaC) with per-tenant infrastructure in `bootstrap-tenant/templates/build/`. Each tenant gets a `build-{guid}` namespace with 3 PaC Repository CRs (one per app), GitLab push webhooks pointing at the PaC controller, and secrets for GitLab PAT, Nexus push credentials, and TPA OIDC. Repository CRs pass tenant-specific params (`image-registry`, `image-name`, `tpa-url`, `issuer-url`) so the `.tekton/` PipelineRun YAML is identical across all tenants. The PipelineRun uses separate Tekton tasks: `git-clone` → `maven` → `buildah` (with `BUILD_EXTRA_ARGS` for OCI labels) → inline `generate-upload-sbom` (syft + TPA upload). Tekton Chains signs the result automatically (ADR-017). |
| **Consequences** | Each tenant gets an additional namespace (`build-{guid}`) and 2 setup Jobs (secrets + webhooks). The `.tekton/` directory and `Containerfile` must be added to the 3 source repos on GitHub (`redhat-ads-tech/`). PaC Repository CR `params` feature (supported in Pipelines 1.24) eliminates tenant-specific templating in the pipeline YAML. WAR apps need a Tomcat-based Containerfile; the Spring Boot app uses a simpler JAR Containerfile. Build toggle: `build.enabled` in values. |

## ADR-021 — Maven builds via Nexus group with Lightwell hosted repos

| Field | Content |
|-------|---------|
| **Date** | 2026-10-14 |
| **Title** | Route Maven builds through Nexus group with Lightwell hosted repositories |
| **Context** | Pipeline Maven builds pull from Maven Central directly, missing the tenant's Nexus cache and unable to resolve Lightwell `-rhlw-*` rebuild artifacts. Each tenant also creates redundant `maven-central-{guid}` and `maven-releases-{guid}` repos that duplicate the default Nexus repos — since Nexus is already per-tenant, the guid suffix adds no isolation value. The official Lightwell Network publishes remediated and validated packages under `packages.redhat.com/lightwell/java/{remediated,validated}/`. |
| **Decision** | Remove `maven-central-{guid}` and `maven-releases-{guid}` from the repositories ConfigMap. Create two hosted repos aligned with official Lightwell Network naming: `lightwell-remediated` and `lightwell-validated`. Update the default `maven-public` group to include them (search order: `lightwell-remediated`, `lightwell-validated`, `maven-releases`, `maven-snapshots`, `maven-central`). The pipeline's Maven task uses `MAVEN_MIRROR_URL` pointing at `http://nexus.lightwell-nexus-{guid}.svc:8081/repository/maven-public` (cluster-internal, passed via PaC Repository CR param). All Maven downloads route through this single group URL — standard deps cache in `maven-central`, `-rhlw-*` versions resolve from `lightwell-remediated`. |
| **Consequences** | Lightwell proxy repos (with credentials) stay in the ConfigMap for the EDA/OpenCode remediation pipeline. The hosted `lightwell-remediated`/`lightwell-validated` repos need to be seeded with `-rhlw-*` artifacts separately. Existing tenants keep the old `maven-central-{guid}`/`maven-releases-{guid}` repos (harmless, unused). Maven builds are faster on repeat runs due to Nexus caching. |

---

## ADR-022 — snow-mock comments via ConfigMap + multi-app AO policy

| Field | Content |
|-------|---------|
| **Date** | 2026-10-15 |
| **Title** | Vendored snow-mock with comments API; GitOps-native deploy; per-app `.lightwell/policy.json` + multi-app AO canvas |
| **Context** | Product wants one AO run across wire-transfer (`needs_approval`), benefits (`auto`), and Renovate-owned report-generator, with ServiceNow as the ITSM trail. Upstream `snow-mock:1.0.0` has no comments API; waiting on Quay publish would block GitOps iteration. |
| **Decision** | (1) Vendor snow-mock under `bootstrap-tenant/files/snow-mock/` with `POST/GET …/comments` + UI; deploy via ConfigMap + UBI Python unless `snow.image` is set. (2) Inject `.lightwell/policy.json` from `gitlab.appSeeds[].policy` during `create-gitlab-tenant`. (3) Rebuild AO workflow: SNOW create → Query TPA → classify → for-each (Impact draft MR → Verifier → Switch → Approval/merge) → SNOW finalize; keep resume Verifier as legacy only. (4) Playbooks live in `rhpds/lw-sdlc-opencode` (sibling checkout). |
| **Consequences** | First pod start runs `pip install` (slower cold start). Existing tenants keep old quay image until Argo sync. Policy is chart-owned until upstream Acme repos also carry `.lightwell/`. AO validate/publish and SCM sync required before smoke. OpenCode Impact remains async for MR creation — Verifier may need MR iid lookup until a poll step lands. |

## ADR-023 — Classify candidates are TPA `affected_repos` only

| Field | Content |
|-------|---------|
| **Date** | 2026-10-16 |
| **Title** | Do not expand classify to the three Acme apps; use Query TPA artifacts |
| **Context** | `classify-affected-apps.yml` replaced `affected_repos` with a hardcoded wire/benefits/report list when `blast_radius_mode=multi_app_policy_demo`. On tenant `t8s2n` v9, TPA correctly returned only `wire-transfer-svc`, but AO still looped all three; Impact on `benefits-mgmt-app` found no `com.h2database:h2` and never opened an MR, leaving the JT stuck on MR poll. |
| **Decision** | Classify normalizes candidates strictly from `query_tpa.artifacts.affected_repos`. Policy split (AO vs Renovate vs fail-closed) still runs per candidate. `blast_radius_mode` is informational only. Multi-app demos require TPA to return multiple matches (SBOM coverage), not a classify-side invention. |
| **Consequences** | Single-app TPA results → single for-each iteration (correct). Empty TPA list fails classify loudly. EDA default `blast_radius_mode` renamed to `tpa_affected_repos`. Local GitLab SCM mirror + AAP project update needed before the next smoke. |

## ADR-024 — OpenCode idle wait uses `GET /session/status`

| Field | Content |
|-------|---------|
| **Date** | 2026-10-16 |
| **Title** | Poll documented session status map; do not use `/session/:id` fields |
| **Context** | Impact/Verifier JTs waited on `GET /session/{id}` for `status` / `time.completed`, which the OpenCode 1.19 API never sets (`/session/:id/status` is SPA HTML). Agents finished in ~15–30s but AAP burned ~10 min (60×10s) of false retries. |
| **Decision** | Wait via `GET /session/status` ([docs](https://opencode.ai/docs/server/)): map of `{sessionID: {type: idle\|busy\|retry}}`. Idle sessions are omitted — treat missing id as idle. Shared task `opencode-wait-idle.yml`; settle 2s after `prompt_async` to avoid false idle. Keep GitLab MR poll as Impact completion proof. |
| **Consequences** | Wall time drops from ~10 min tax to agent runtime + settle. Stuck `{type:busy}` sessions (if any) still block until timeout — use `POST /session/:id/abort` operationally. |

## ADR-025 — Drop legacy GitLab MR resume Verifier

| Field | Content |
|-------|---------|
| **Date** | 2026-10-16 |
| **Title** | AO in-loop Verifier only; remove EDA MR-open → Resume |
| **Context** | With multi-app AO canvas, Impact already launches in-loop Verifier. EDA still fired `SDLC Resume Orchestrator` on `update-artifact-*` MR open, starting a second `mr_verifier` session that raced the in-loop agent (4M+ token bash sed/grep loops). |
| **Decision** | (1) Remove GitLab MR-open rule from `sdlc-remediation.yml`. (2) Remove AO `resume_trigger` + `mr_verifier_legacy` nodes. (3) Keep `sdlc-remediation-legacy.yml` for `orchestrator.enabled=false` only. (4) Approval branching uses `auto_approve` / `needs_approval` (not bare `auto` — Ansible/AO reserved); see ADR-026 for condition vs switch. Verifier JT defaults to GitLab MR-open check (`verifier_use_opencode: false`) until ephemeral skill is fixed in image. |
| **Consequences** | No dual Verifier. Benefits/low-risk apps use `approval: auto_approve`; wire-transfer uses `needs_approval`. Full ephemeral verify needs skill + image bump. |

## ADR-026 — Approval policy as condition, not switch

| Field | Content |
|-------|---------|
| **Date** | 2026-10-16 |
| **Title** | Binary if/else for auto vs human merge after Verifier |
| **Context** | AO `switch` with `default_port: auto_approve` and a case also named `auto_approve` fails at runtime: `Case port 'auto_approve' conflicts with default_port` (seen on `t8s2n` v11–v16). Two-way approval does not need multi-case switch semantics. |
| **Decision** | Replace `approval_switch` with condition node `approval_auto`: `${verifier.artifacts.approval} == "auto_approve"` → true=`merge_auto`, false=`human_approval`. Keep artifact values `auto_approve` / `needs_approval` (never bare `auto`). |
| **Consequences** | Unknown/empty approval falls through to human gate (safer than auto-merge). Republish `Lightwell Remediation` after bootstrap-ao so tenants leave the broken switch behind. |

## ADR-027 — Impact `already_current` skips MR poll

| Field | Content |
|-------|---------|
| **Date** | 2026-10-16 |
| **Title** | Treat “already on fix version” as a successful Impact outcome |
| **Context** | Classify/`ao_apps` means TPA-affected + AO policy, not “still needs a pom bump.” After earlier smokes, `wire-transfer-svc` already had `com.h2database:h2:2.2.219.rhlw-00001`. Impact OpenCode correctly returned “already current / no MR,” then the playbook still polled GitLab 90× (~15 min) and failed. |
| **Decision** | (1) After OpenCode idle, detect `already_current` from agent text and/or default-branch `pom.xml` containing the fix GAV. (2) Skip `poll-gitlab-mr` when already current; `set_stats` `iteration_outcome=already_current` (else `mr_opened`). (3) AO condition `impact_already` → true=`snow_iter_already`, false=Verifier→approval→merge. |
| **Consequences** | Re-triggers on already-remediated apps finish in seconds with a SNOW note instead of hanging. Classify pre-filter remains optional. ADR-024’s “MR poll as completion proof” applies only to the `mr_opened` path. |

## ADR-028 — Multi-app AO path and Oct 16 hardening

| Field | Content |
|-------|---------|
| **Date** | 2026-10-16 |
| **Title** | Rollup: multi-app AO+SNOW+classify, then runtime hardening |
| **Context** | Across 15–16 Oct the lab path moved from Demo-A single-app to a multi-app AO canvas with ServiceNow audit, then hit runtime failures on `t8s2n` (dual Verifier, switch `default_port` conflict, OpenCode idle API misuse, Impact MR-poll hang when GAV already on `main`, classify inventing apps). Work spans this repo (`bootstrap-ao-tenant`, snow-mock) and `rhpds/lw-sdlc-opencode` (playbooks/rulebooks). |
| **Decision** | Treat ADR-022–027 as one delivery arc: (1) **15 Oct** — multi-app AO+SNOW+classify path (create → TPA → classify → for-each Impact/Verifier/approval/merge → finalize; vendored snow-mock; policy files). (2) **16 Oct** — harden merge (undraft then merge), OpenCode idle via `/session/status`, classify = TPA `affected_repos` only, drop EDA/AO legacy MR resume (no dual Verifier), approval as condition not switch, Impact `already_current` short-circuit. Proven on `t8s2n` AO **v18**. |
| **Consequences** | Demo path is coherent on the tenant when playbooks + AO are republished. **Done:** `demo-update` → `rhpds/main` and tenant Argo sync restored; OpenSpec leftovers (benefits auto-approve with real TPA hit; Renovate skip on classify) closed. Auto-approve smoke with a *new* bump still needs an app whose pom is not already on the fix GAV (or a pom rollback). Sibling playbook commits land via tenant GitLab mirror / AAP project sync until chart SCM points at published `lw-sdlc-opencode`. Verifier still on GitLab MR-open check until ephemeral OpenCode skill + `verifier_use_opencode: true`. |

## ADR-029 — OpenCode UI gate for web session visibility

| Field | Content |
|-------|---------|
| **Date** | 2026-10-16 |
| **Title** | Route the OpenCode web UI through a bootstrap gate; keep AAP on the raw Service |
| **Context** | On `t8s2n`, `GET /session` returned 26 agent sessions under `directory=/app`, but the embedded web UI showed "No projects open" / empty sidebar. OpenCode 1.19 keeps *open projects* in browser `localStorage` and does not auto-adopt the server cwd (upstream #37096 / #44216; fix still open as #55230). Deep-linking a session ID works once `/app` is seeded; a fresh browser does not. |
| **Decision** | When `sdlc.exposeUi` is true: (1) Deploy `opencode-ui-gate` (same OpenCode image, `python3` reverse proxy from `files/opencode-ui-gate/proxy.py`) that injects a bootstrap into `text/html` responses registering `/app` as an open project and redirecting bare `/` to the `/app` workspace URL. (2) Point Route `opencode-ui` at Service `opencode-ui-gate:8080`. (3) Leave Service `opencode:4096` for AAP/EDA — no HTML injection on the API path. |
| **Consequences** | Demo browsers see Impact/Verifier transcripts without DevTools. Gate can roll independently of the opencode pod (preserves emptyDir sessions). Drop the gate when upstream auto-adopts the server directory. WebSocket/SSE are tunneled; do not put AAP traffic through the gate. |

## ADR-030 — Renovate OIDC via Keycloak

| Field | Content |
|-------|---------|
| **Date** | 2026-10-15 |
| **Title** | Wire the Renovate operator web UI to Keycloak SSO for per-user visibility |
| **Context** | The Renovate operator web UI shows all tenants' RenovateJobs by default. Without authentication, students could see and trigger each other's jobs. The operator supports OIDC for the web UI and per-job `spec.access` rules for visibility control. |
| **Decision** | A sync hook Job in `bootstrap-infra/templates/renovate/oidc-setup-job.yaml` creates a `renovate-ui` OIDC client in the Keycloak `sso` realm and stores the client secret in the `renovate-operator` namespace. The operator Helm values enable `auth.oidc` with the SSO issuer URL and redirect callback. Each student's RenovateJob sets `spec.access.adminUsers` to their Keycloak email (`{user}@demo.redhat.com`). The Renovate namespace is `{username}-renovate` (not `sdlc-{guid}`) with an `edit` RoleBinding and a custom Role granting access to `renovatejobs` and `renovateprojects` CRDs. |
| **Consequences** | Students log in via SSO and only see their own RenovateJobs. The OIDC client uses a wildcard redirect URI (`/*`). The operator matches `adminUsers` against the OIDC email claim, not the username — the `@demo.redhat.com` domain comes from the Keycloak user setup in AgnosticV. If the Keycloak email domain changes, the showroom's `oc apply` and the matching must be updated. |

## ADR-031 — Showcase Nexus webhook trigger script

| Field | Content |
|-------|---------|
| **Date** | 2026-10-16 |
| **Title** | Repo-local script to fire Path 2 (AO) via EDA without Nexus upload |
| **Context** | Demo / operator smoke needs a repeatable way to start the multi-app AO canvas for both approval policies. Real Nexus webhooks are often missing (empty Lightwell Network creds) and a cached GAV cannot re-fire. Showroom `inject-remediation.sh` uploads to Nexus for Renovate (Path 1), not EDA. |
| **Decision** | Keep an AO Path 2 operator helper under [`ao-trigger-helper/`](ao-trigger-helper/): (1) **Demo entry** = `publish-remediation.sh` (Nexus upload → real webhook → EDA → AO). (2) `trigger-nexus-webhook.sh` is **testing only** (synthetic `CREATED` when Nexus→EDA is broken). (3) `reset-demo-repos.sh` re-seeds `acme-<guid>/*` from GitHub + `.lightwell/policy.json`. (4) Docs in [`ao-trigger-helper/docs/`](ao-trigger-helper/docs/). Entry: [`ao-trigger-helper/README.md`](ao-trigger-helper/README.md). |
| **Consequences** | Operators can demo AO without seeding Nexus and reset GitLab apps between runs without re-provisioning the tenant. Docs stay with the helper so Path 2 wiring / investigation are not confused with Showroom or Path 1. Auto-approve still depends on TPA SBOM coverage for the chosen GAV (override `AUTO_APPROVE_GAV` if needed). Scripts are not student Showroom content; Path 1 keeps using `inject-remediation.sh`. Upstream GitHub repos are never modified. |

## ADR-032 — Remediation MR body as the review artifact

| Field | Content |
|-------|---------|
| **Date** | 2026-10-16 |
| **Title** | Rich, two-phase MR description for agent remediations |
| **Context** | The MR opened by `impact-analyzer` carried only artifact, version, GitLab path, a free-text paragraph and the handoff JSON. A reviewer could not see which CVE was addressed, its severity, whether the application is one where dependency changes need sign-off, or whether anything had been tested. The MR is the only artifact a human actually reads in this demo, so it has to carry the decision. |
| **Decision** | `build_mr_description` renders Summary, Vulnerability Details, Automated Validation, Risk Assessment and Recommended Action; the title is `[LW] <dot> Bump <artifact> to <version> to fix <CVE>`. Filled in **two phases**, because test results do not exist at MR-creation time: `impact-analyzer` writes every validation row as `Pending`, and `mr-verifier` calls the new `gitlab_api.py mr-validation` once the verify Job has run. That command rewrites only the text between `lw:validation` / `lw:action` markers and derives Recommended Action itself (failed check → do not merge; HIGH/CRITICAL risk class → human review; otherwise safe to merge). Advisory data comes from a TPA `/api/v3/vulnerability` lookup added to `query-tpa.yml`; risk class comes from `gitlab.appSeeds[].riskClass` in the tenant chart, surfaced as `APP_RISK_METADATA`. |
| **Consequences** | A check that nobody reported stays `Pending` rather than defaulting to passed — the table is only worth having if a reviewer can trust it, and both skill docs tell the agents not to invent advisory data or results. The advisory lookup is best-effort: a tenant whose TPA has no advisory still gets the MR, with "not referenced" / "not scored" in place of fabricated values. `riskClass` lives in `.lightwell/policy.json` next to `approval`, because the EDA activation's extra_vars never reach AO-launched job templates. Changing the section layout means updating both the builder and the marker-replacement path together. |
| **Checks** | Six of eight rows are measured. Unit and integration tests come from surefire/failsafe. **Binary signature is an integrity check, not a signature**: the tenant mirror publishes jar/pom/metadata with no detached GPG signature, so the jar is verified against the checksum Nexus records (read from the REST assets API — Nexus writes no `.sha1` sibling for raw PUT uploads). Licence compares base against remediated POM, normalised so h2's `MPL 2.0 or EPL 1.0` versus `MPL 2.0` + `EPL 1.0` is not a false alarm. SBOM is generated by the CycloneDX Maven plugin in the same invocation as the tests and asserted to list the bumped coordinate. Dependency compatibility asserts the pom declares what the build resolved. **Regression scan is unimplemented**: a behavioural diff needs the suite run against the target-branch baseline, doubling build time, so it stays Pending rather than being faked. |

## ADR-033 — Async CI/CD via AO Approval PATCH

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Park post-merge build/deploy on Approval gates; EDA decides via Approvals API |
| **Context** | Operators need one AO run from Nexus through deploy Healthy. Product **Wait** is duration-only (no external resume). Re-using `eda_trigger` / Start Orchestrator for PipelineRun or Argo would spawn a second remediation (forbidden by ADR-025). Live spike on `cng2l`: `POST …/activities/{id}/signal` returns Temporal 500; `PATCH /api/v1/approvals/{id}` with `{"status":"approved"}` advances the parked node. |
| **Decision** | (1) After merge, canvas parks on Approval nodes `await_build` then `await_deploy` (`decision_window` 1800s, `fallback_decision: reject`, `continue_on_failure: true`). Prompts embed `gitlab_path` + `guid`. (2) EDA rules for `pipelinerun_terminal` and `argo_app_health` run JT `SDLC Signal AO CI/CD Gate` only — never Start. (3) JT authenticates with the EDA bridge SA (`client_credentials`) and PATCHes the matching pending approval (`approval_node_id` + path/guid). (4) Bootstrap assigns the SA **project-user** so it has `approval:decide:project`. (5) Smoke helper `ao-trigger-helper/trigger-cicd-signal.sh`; tenant Job stamps `lightwell.eda-webhook` on Acme Applications. Full Argo Notifications controller→EDA service wiring remains optional until cluster CM ownership is settled. Parent/child SNOW (create children after classify; comments on children) ships in the same delivery arc. |
| **Consequences** | Operator sees Waiting on named CI/CD gates; one execution through deploy. Timeout → reject → child `build_failed` / `deploy_failed` with manual-verify note. Requires sdlc SCM push + AAP sync + AO republish. Progressing-only Argo events must not approve deploy. |

## ADR-034 — Student merges needs_approval MRs in GitLab

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | AO merges only auto_approve; needs_approval merges happen in GitLab |
| **Context** | Parking on AO “Approve remediation MR” taught the wrong demo story: the human review artifact is the GitLab MR. AO should not be the merge button for high-risk apps. ADR-025 already forbids MR-**open** → Resume (dual Verifier). We still need a lifecycle signal when the student **merges** so the same AO run can await build/deploy. |
| **Decision** | (1) `auto_approve` → JT Merge MR → `await_build` → `await_deploy`. (2) `needs_approval` → Approval gate `await_gitlab_merge` (prompt: merge in GitLab; AO will not merge) → on EDA signal → `await_build` → `await_deploy`. (3) Remove `human_approval` + `merge_approved`. (4) EDA rule: GitLab `object_kind=merge_request` + `object_attributes.action=merge` → Signal `await_gitlab_merge` (never Start; never act on MR open). (5) MR webhooks to EDA only on `needs_approval` AO apps. |
| **Consequences** | Module 3 review happens in GitLab. Merge starts PaC (`build-push-to-main`) via push webhook; AO tracks CI/CD via existing Approval gates. Republish AO + sync rulebook/playbook + ensure GitLab MR hook. Soft-skip Signal JT if no pending `await_gitlab_merge` (benign races). |
| **Superseded by** | [ADR-035](#adr-035--webhook-driven-ao-no-approval-nodes) (all merges in GitLab; no AO Approvals). |

## ADR-035 — Webhook-driven AO (no Approval nodes)

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Remove AO Approvals; GitLab merge + EDA→AO lifecycle webhooks |
| **Context** | Approval gates (`await_gitlab_merge` / `await_build` / `await_deploy`) and AO merge for `auto_approve` made the UX look like AO is the human gate. Product Wait cannot resume on events; Approval+PATCH was a workaround (ADR-033). Operators want a simple story: student merges in GitLab → webhook → pipelines continue; AO listens via `eda_trigger` webhooks. |
| **Decision** | (1) **No** `type: approval` nodes and **no** AO Merge JT on the canvas. (2) Start path: Nexus → SNOW → TPA → classify → for-each (Impact → Verifier → SNOW `awaiting_merge`) → parent note; execution completes. (3) Students merge **only** in GitLab (policy labels remain informational). (4) Additional AO `eda_trigger` paths — `merged` / `build` / `deploy` — each start a short execution that books SNOW (resolve child by `gitlab_path`). (5) EDA rules POST those paths via JT `SDLC AO Lifecycle Webhook` (never Start remediation; never MR-open). (6) MR webhooks on **all** AO-owned apps. |
| **Consequences** | One Nexus start run no longer spans deploy; lifecycle is a series of webhook-driven AO executions (honest for AO’s trigger model). Supersedes Approval parking in ADR-033/034. Requires republish AO + push `lw-sdlc-opencode` rulebook/playbooks + AAP/EDA sync. Old parked Approval executions on tenants should be cancelled. |
| **Amended by** | [ADR-041](#adr-041--ao-merges-auto_approve-after-verifier) — restores AO Merge JT for `auto_approve` only; Approval-node removal stands. |
| **Superseded in part by** | [ADR-037](#adr-037--single-ao-eda_trigger--switch-on-triggertype) (path model) → [ADR-038](#adr-038--four-ao-workflows-one-eda_trigger-each). |

## ADR-036 — CI/CD → EDA bridge (PipelineRun + Argo producers)

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Per-tenant watcher POSTs build/deploy events to EDA |
| **Context** | ADR-035 added AO `build`/`deploy` eda_triggers and EDA rules for `pipelinerun_terminal` / `argo_app_health`, but only GitLab MR-merged was wired as a producer. PaC push webhooks go to the PaC controller (not EDA). OpenShift GitOps on this cluster has the Notifications CRD but no notifications controller pod; owning cluster-wide `argocd-notifications-cm` is multi-tenant fraught (ADR-033 deferred). |
| **Decision** | Deploy `cicd-eda-bridge` per tenant (`bootstrap-tenant/templates/cicd-eda-bridge/`): a small Python poller (SA in `lightwell-tenant-{guid}`) that (1) lists PipelineRuns in `build-{guid}` with PaC `push` event-type, and on terminal Succeeded/Failed POSTs `pipelinerun_terminal` with `gitlab_path` from PaC labels; (2) watches Application `acme-apps-{guid}`, and on Synced+Healthy or Degraded/Missing POSTs `argo_app_health` for each AO-owned `gitlab.appSeeds` path. Idempotency via annotations `lightwell.io/eda-build-signaled` / `lightwell.io/eda-deploy-signaled` (**revision-keyed** for deploy — see ADR-045). Startup primes existing terminal objects without POSTing. Keep `trigger-cicd-signal.sh` as a manual fallback. |
| **Consequences** | Build/deploy AO lifecycle runs fire without changing Acme `.tekton/` pipelines or enabling cluster Notifications. Deploy fan-out may comment SNOW for every AO app when the shared Acme Application goes Healthy (acceptable for demo; tighten with per-app Argo apps later). Bridge must stay Running; hibernation delays signals until the next poll after wake. The companion `argo-notifications-eda-{guid}` Sync hook annotates the Applications; it runs in `lightwell-tenant-{guid}` because that is where its `lightwell-tenant-jobs` SA lives, while its Role/RoleBinding stay in `openshift-gitops` where the Applications are. Templating that Job into `openshift-gitops` instead broke every tenant order on 19 Oct — see the Handoff gotcha. |

## ADR-037 — Single AO eda_trigger + switch on trigger.type

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Collapse four AO webhook paths into one; route with switch |
| **Context** | ADR-035 used four `eda_trigger` paths (`start` / `merged` / `build` / `deploy`). Feedback: prefer a single trigger and branch on payload. AO switch uses ordered `cases[{port,label,condition}]` + `default_port` (not value-match); ADR-026’s conflict was case port == `default_port`. A single path does **not** make one continuous execution — each EDA POST still starts a new run. |
| **Decision** | (1) One `eda_trigger` on `lightwell-remediation-{guid}` (shorter than the old `*-start-*` path). (2) Switch `route` cases on `${trigger.type}` → `start` / `merged` / `build` / `deploy`; `default_port: unmatched` (no downstream). (3) Chart helpers alias merged/build/deploy/resume paths to that single path unless overridden. (4) EDA lifecycle rules set `ao_lifecycle_webhook_path` to `ao_start_webhook_path`. (5) Keep separate Start vs Lifecycle JTs so lifecycle never re-enters Nexus remediation (ADR-025). (6) When republishing over a multi-trigger canvas, `POST …/unpublish` then publish — if AO still returns `WEBHOOK_TRIGGER_PATH_CONFLICT` on the old path, publish with the new `lightwell-remediation-{guid}` path (seen on `cng2l` v8→v10). |
| **Consequences** | Simpler AO surface and EDA→AO wiring; still N short executions for merge/build/deploy. Republish AO + sync `lw-sdlc-opencode` rulebook/playbook + refresh EDA activation extra vars (all path keys → single path). |
| **Superseded by** | [ADR-038](#adr-038--four-ao-workflows-one-eda_trigger-each) |

## ADR-038 — Four AO workflows (one eda_trigger each)

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Split remediation into Start / Merged / Build / Deploy workflows |
| **Context** | ADR-037 put start + lifecycle on one canvas behind a switch. That hid the apps `for_each` loop next to short lifecycle branches and made demos hard to follow. Product still cannot resume a run on external events, so merge/build/deploy remain separate executions either way. |
| **Decision** | (1) Four published workflows per tenant: `Lightwell Remediation — Start` (Nexus → SNOW → TPA → classify → **apps_loop** Impact/Verifier), `— Merged`, `— Build`, `— Deploy`. (2) One `eda_trigger` + guid-scoped path each (`…-start/merged/build/deploy-{guid}`). (3) Bootstrap retires legacy monolith `Lightwell Remediation` (unpublish + disable). (4) EDA Start JT → start path; Lifecycle JT → merged/build/deploy paths. |
| **Consequences** | Start canvas is only the multi-app loop; lifecycle canvases stay short. Students see four workflows in the project. Republish AO + refresh EDA extra vars + sync rulebook. **OpenCode bake:** `ao-bootstrap` exports `OPENCODE_BASE_URL` / username / password (from `opencode-server` secret or chart default); `_trigger_common` writes them into Start node `extra_vars` so Impact does not 401 when EDA omits the password (same class of bug as empty `snow_url`). |
| **Superseded in part by** | [ADR-039](#adr-039--mergedbuild-one-canvas-poll-pac) (Build canvas folded into Merged). |

## ADR-039 — Merged+Build one canvas (poll PaC)

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Fold Build into Merged; poll PaC commit status instead of PipelineRun webhook |
| **Context** | ADR-038 used separate Merged / Build AO executions. AO cannot resume on Tekton events; `cicd-eda-bridge` POSTed `pipelinerun_terminal` to start Build. Demos want one story from student merge through CI. AAP JTs already poll (OpenCode idle / GitLab MR); PaC already mirrors PipelineRun onto GitLab commit statuses. |
| **Decision** | (1) **Merged** workflow: SNOW `merged` → JT `SDLC Poll Build Status` (GitLab commit statuses for `build-push-to-main` on `merge_commit_sha`) → condition → SNOW `build_succeeded` / `build_failed`. (2) On `build_failed`, SNOW lifecycle sets `fail_on_bad_outcome` so the JT fails after commenting — the AO run ends **Failed** (no `continue_on_failure`). (3) Retire AO workflow `Lightwell Remediation — Build` (unpublish + disable). (4) EDA drops PipelineRun→AO rules; chart `aoBuildWebhookPath` aliases to merged. (5) Bridge stops POSTing `pipelinerun_terminal` by default (`POST_BUILD_EVENTS=false`); still watches Argo for Deploy. (6) Bake `GITLAB_URL` / `GITLAB_TOKEN` into Merged node vars. |
| **Consequences** | Three AO workflows (Start / Merged / Deploy). Merged runs longer (poll up to ~15 min). Failed PaC builds fail the Merged execution (SNOW note still written). Deploy unchanged. Requires `lw-sdlc-opencode` playbook + rulebook sync + AO republish + bridge rollout. |

## ADR-040 — Start prep as one AAP JT (Prepare Remediation)

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Collapse Start canvas prep (SNOW→TPA→classify→children) into one JT |
| **Context** | ADR-038 Start had five AAP nodes before `apps_loop` (Create SNOW, Query TPA, Classify, SNOW Comment, Create Children). That made the canvas noisy and forced AO to thread `parent_incident` / `affected_repos` / `ao_apps` across node artifacts. Facts already persist across plays in one Controller job via `set_fact`. |
| **Decision** | (1) New playbook `prepare-remediation.yml` (`import_playbook` of create → TPA → classify → comment → children). (2) JT `SDLC Prepare Remediation`. (3) Start canvas: `eda_trigger` → **prepare** → `apps_loop` (Impact → Verifier → iteration SNOW) → parent awaiting-merge note. (4) Final `set_stats` from create-children still export `ao_apps` (with `child_incident`) + `parent_incident` + `package_info` for the loop. |
| **Consequences** | Start shows one prep node before the multi-app loop. Lab: JT inject + Start **v4** on `cng2l`. Push `lw-sdlc-opencode` for SCM durability (`scm_update_on_launch` stays false until then). |

## ADR-041 — AO merges auto_approve after Verifier

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Restore AO merge for `auto_approve`; keep `needs_approval` open in GitLab |
| **Context** | ADR-035 removed AO Approval gates *and* the Merge JT, so both policy types waited for a student merge — Module 3’s low-risk vs human-gate contrast went flat (HANDOFF 00). |
| **Decision** | After Verifier pass on Start: condition `${loop.item.approval} == "auto_approve"` → JT `SDLC Merge GitLab MR` (pauses `merge_delay_seconds`, default **120**) → SNOW `merged`; else → SNOW `awaiting_merge` (MR stays open). No Approval nodes. Merged/Deploy webhooks unchanged (student or AO merge both fire GitLab `action=merge`). |
| **Consequences** | Benefits/low-risk auto-merges in AO after a short demo window so the open MR is visible; wire-transfer stays for GitLab review. Bake `GITLAB_URL`/`GITLAB_TOKEN`/`merge_delay_seconds` into the Merge node. Republish Start + inject `merge-gitlab-mr.yml`. |

## ADR-042 — Meaningful SNOW comments with MR / pipeline URLs

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | SNOW iteration/lifecycle comments carry human headlines + clickable URLs |
| **Context** | Demo comments were sparse bullets (`outcome`, `MR: !N`, `guid`). Impact already exported `merge_request_url`; PaC commit statuses expose `target_url` — neither reached the SNOW body. |
| **Decision** | (1) `snow-iteration-comment` / `snow-lifecycle-event` use outcome headlines and append MR URL (artifact or `{gitlab_url}/{path}/-/merge_requests/{iid}`) and build/pipeline URL. (2) `poll-build-status` exports `build_url` from GitLab status `target_url`. (3) Merge JT exports `merge_request_url`. (4) AO Start/Merged bake `gitlab_url` + pass `merge_request_url` / `build_url` into comment JTs. |
| **Consequences** | Child INC comments link straight to GitLab MR and Tekton/PaC UI. Lab: reinject playbooks + republish Start/Merged; push `lw-sdlc-opencode` for SCM durability. |

## ADR-043 — OpenCode session deep links + summary in AAP/SNOW

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | After Impact idle, export UI deep link + short agent summary |
| **Context** | AO/AAP only showed `opencode_session_id`. Full reasoning lives in OpenCode UI; operators had to hunt sessions. `GET /session/{id}/message` returns the transcript while the pod’s emptyDir still holds it (ADR-029). |
| **Decision** | (1) Bake `OPENCODE_UI_URL` (`https://opencode-ui-sdlc-{guid}.{domain}`) into Start nodes. (2) Task `opencode-session-summary.yml` after idle: fetch session + messages, summarize last assistant text (`files/opencode_session_summary.py`), log to AAP stdout, export `opencode_session_ui_url` (`…/global/session/{id}`), title, summary. (3) Iteration SNOW comments include OpenCode link + truncated summary; lifecycle keeps pipeline URL. |
| **Consequences** | Demo path: click OpenCode from the child INC; AAP Impact job Output shows the same summary. Transcripts still die on OpenCode pod restart. |

## ADR-044 — snow-mock comment Markdown + autolink

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Render journal comments with a safe Markdown subset in the mock UI |
| **Context** | ADR-042/043 put URLs and agent summaries into comments, but the SPA escaped everything as plain `pre-wrap` text. |
| **Decision** | Client-side escape-first renderer: headings, lists, `hr`, bold/italic/code, `[label](https://…)`, bare `http(s)` autolinks (`target=_blank`). No raw HTML. AO comment playbooks emit that Markdown. |
| **Consequences** | Activity feed is readable in demos; XSS surface stays closed. Duplicate “Work notes list” panel removed — comments appear only under Activities. Roll `snow-mock-static` ConfigMap on existing tenants. |

## ADR-045 — Deploy bridge signal keyed by Argo revision

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | `eda-deploy-signaled` includes git revision so each promote can fire Deploy |
| **Context** | After flyway auto_approve, PaC promoted and Argo reached Synced/Healthy, but AO Deploy never started. Annotation was sticky `Synced/Healthy` (set at prime or first success); later returns to the same status were no-ops. |
| **Decision** | Key `lightwell.io/eda-deploy-signaled` as `{sync}/{health}@{revision}` (`status.sync.revision`, else operation/history/reconciledAt). Also keep a process-local set (Argo self-heal can strip CR annotations). Payload includes `revision`. Legacy annotations without `@` are not re-primed — first scan POSTs once (catch-up). |
| **Consequences** | Each `acme-deployment` bump that reconciles Healthy fires `argo_app_health` again. Restart primes when annotation absent; in-memory set stops re-storm if the annotation is wiped. Roll `cicd-eda-bridge` ConfigMap + restart. |

## ADR-046 — Deploy SNOW comments link Argo / Route / console

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Deploy lifecycle + finalize comments include operational deep links |
| **Context** | Deploy SNOW notes said Healthy but gave operators nowhere to click. |
| **Decision** | Bake `ARGO_CD_URL`, `OPENSHIFT_CONSOLE_URL`, `APPS_NAMESPACE`, `APPS_DOMAIN` into AO Deploy nodes. Shared task builds (1) Argo Application URL, (2) `https://{app}-{guid}.{domain}` Route, (3) console `/k8s/cluster/projects/{ns}`. Child `deployed`/`deploy_failed` comments include Argo (+ Route/console when Healthy). Parent deep-link dump removed — see ADR-047. |
| **Consequences** | Demo ITSM trail opens Argo, the app URL, and the OpenShift project from the **child**. Republish Deploy + reinject playbooks. |

## ADR-047 — Parent INC holds top-level status only

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Parent SNOW comments are workflow finish rollups with child links |
| **Context** | Parent tickets accumulated the same MR/build/deploy/agent detail as children, making the parent unreadably long. |
| **Decision** | (1) JT `SDLC SNOW Parent Status` + shared task posts a short headline/plain body + **[open child]** links. (2) Start canvas ends with that JT after `apps_loop` complete. (3) Lifecycle (`merged`/`build_*`/`deploy*`) posts the same brief parent rollup after the child comment. (4) Finalize only PATCHes parent to Resolved — no detail comment. (5) Create-children posts one “Child tickets opened” status with all new child links. |
| **Consequences** | Parent thread = event milestones; child thread = operator detail. Lab: inject playbooks, create JT, republish Start/Merged/Deploy. Push `lw-sdlc-opencode` for SCM durability. |

## ADR-048 — Deploy finalize reads parent from lifecycle artifacts

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Deploy finalize uses `lc_deployed.artifacts.parent_incident`, not the EDA trigger |
| **Context** | Bridge/EDA `argo_app_health` payloads carry `gitlab_path` but not SNOW INC numbers. Lifecycle looked up the child and exported `parent_incident`, yet Deploy finalize was wired to `${trigger.parent_incident}` (always empty) → AO `completed_with_errors` after a successful Deploy signal. |
| **Decision** | (1) Finalize node vars use `${lc_deployed.artifacts.parent_incident}`. (2) Lifecycle/finalize `set_stats` never export `""` (AAP drops empty strings so AO cannot read the property). (3) Finalize playbook can re-resolve parent via `cmdb_ci`/`gitlab_path` when the var is missing. |
| **Consequences** | Deploy ends Resolved on the parent after Healthy. Lab: Deploy **v5** + playbook inject on `cng2l`. Push `lw-sdlc-opencode` for SCM durability. |

## ADR-049 — Deploy signals only the promoted app; finalize soft-skips orphans

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Narrow bridge Deploy fan-out; never fail finalize without a parent INC |
| **Context** | Shared Argo Application `acme-apps-{guid}` goes Synced/Healthy on any `acme-deployment` promote. Bridge POSTed `argo_app_health` for **every** AO-owned path (benefits + wire). Wire had no child INC → lifecycle `parent=unknown` → finalize assert fail → AO Deploy `completed_with_errors` on every auto_approve run even when benefits finalized correctly. |
| **Decision** | (1) Bridge reads the promote commit title via GitLab (`promote <app> to <sha>`) and POSTs Deploy only for matching `AO_APP_PATHS`; fall back to full fan-out if token/parse unavailable. (2) `snow-finalize.yml` soft-skips (success + `finalize_skipped=true`) when parent cannot be resolved after `cmdb_ci` lookup — never fail the JT for orphan paths. |
| **Consequences** | One Deploy execution per real promote in the common case; orphan fan-out (if any) no longer reds the AO canvas. Requires bridge ConfigMap + env (GITLAB_URL/TOKEN) + playbook inject; push `lw-sdlc-opencode` for finalize durability. |

## ADR-050 — Gate `auto_approve` on the pull-request check, inside the merge

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | `merge-gitlab-mr.yml` waits for `build-pull-request` before merging; fixed pause dropped |
| **Context** | Measured on tenant `8djv7`: AO merged the `auto_approve` MR 33 s after it opened, while `build-pull-request` — the pipeline that writes the Automated Validation table — did not start until 43 s **after** the merge. The merged MR carried all seven rows `⏳ Pending`, `updated_at` equal to the merge time, and no verifier note; SNOW still said "auto-merged after the verifier passed". `verifier_ok` only asserts the Verifier *job template* returned successful, and the OpenCode JTs report success the moment they launch the async agent, so the gate could not fail. The h2 → `wire-transfer-svc` run cleared the table logic itself (6/7 ✅ Passed, 🔴 HIGH, correctly left unmerged), so this was only ever a race on the auto path. ADR-041 added `merge_delay_seconds=120` for demo pacing, which incidentally usually hid the symptom; an earlier revision of this ADR recorded the gate as *not adopted* on those grounds. A fixed sleep cannot tell a slow pipeline from a failed one, so a **failed** build still auto-merged. Reversed by Natale. |
| **Decision** | Poll inside `merge-gitlab-mr.yml`, not as a separate AO node (Shaaf's call, and the better one): the canvas keeps a single `Merge GitLab MR (auto_approve)` node, check and merge are **atomic** with no window between them where the MR could change, and the Start canvas stays as flat as ADR-040 intended. The playbook reuses the MR it already fetches, polls the `build-pull-request` commit status on `_mr.json.sha`, and asserts green before merging. Vars: `wait_for_status_context` (`""` disables), `wait_for_status_retries` 60, `wait_for_status_delay` 10 — a 10-minute budget, because a cold cluster pulls Tekton images first (76 s measured from MR open to pipeline start) and a tight timeout would fail a healthy run mid-demo. `merge_delay_seconds` is removed: waiting for the real check already leaves the MR open ~110 s, which is the window the pause existed for, and keeping both pushed the merge out to ~4 minutes. |
| **Consequences** | The auto path can now fail, and the validation table is guaranteed populated before the merge, because the pipeline being waited on is the one that writes it. A non-green check fails the JT with "the MR is left open for human review" — fail-closed, but with no SNOW comment explaining it. Accepted deliberately: the lab only demonstrates the happy path. A "merge withheld" SNOW comment is the upgrade if that path ever needs showing. Requires `lw-sdlc-opencode` [PR #7](https://github.com/rhpds/lw-sdlc-opencode/pull/7) merged **before** an AO republish, or the merge JT runs the old playbook and merges unvalidated as now. |
| **Amends** | [ADR-041](#adr-041--ao-merges-auto_approve-after-verifier) — the merge is gated, and its `merge_delay_seconds` pacing clause is superseded. |

## ADR-051 — Script ConfigMap edits do not reach an existing tenant (accepted)

| Field | Content |
|-------|---------|
| **Date** | 2026-10-19 |
| **Title** | Accept `ignoreDifferences` on ConfigMap `/data`; document the workaround |
| **Context** | The tenant Argo Application carries `ignoreDifferences: [{jsonPointers: ["/data"], kind: ConfigMap}]`, listed twice. The rule is in neither this repo nor agnosticv — the RHDP side that creates the Application sets it. Every file-backed script ConfigMap is therefore frozen at **creation-time** content for the life of that tenant, while Argo reports `Synced`. Found when Shaaf's ADR-049 promote-scoping appeared not to work on `8djv7`: his code was correct, but the live `bridge.py` was still 401 lines against 493 in the repo, so Deploy kept fanning out and `wire-transfer-svc` — never merged, never built — was marked deployed three times. |
| **Decision** | **Do not engineer around it.** Scope is narrow: every attendee is handed a newly ordered tenant, whose ConfigMaps are *created* from current `main` — creation is not a diff, so `ignoreDifferences` does not apply and a fresh order is always correct. The only people affected are lab developers reusing one tenant across chart changes. For them the workaround is two commands: `oc create configmap <name> -n <ns> --from-file=<key>=<path> --dry-run=client -o yaml \| oc apply -f -` then `oc rollout restart deploy/<name> -n <ns>`. A plain Argo sync will not do it, with or without a hard refresh. |
| **Consequences** | No change to seven templates and no ConfigMap rename on every script edit. The cost is that the failure stays silent — Argo says `Synced` while the tenant runs old code — so the gotcha has to be *known*, which is why it is also in Handoff. Revisit only if long-lived shared tenants become normal. The real repair is for the Application template to stop ignoring `/data`; raise it with whoever owns that template, since the duplicated rule looks more like an accident than a decision. |
| **Rejected** | Content-hash ConfigMap names (`cicd-eda-bridge-<sha8>`), which would make edits land by creating a new object. Correct, but it buys nothing for attendees and costs noise on every edit. |

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
| Remediation MR body / risk class | ADR-032 |
| Trigger artifacts must match app poms | ADR-016 |
| Fake Lightwell / AgnosticV credentials | ADR-016 (contents); install still planned |
| Spec outlines still say Artifactory… | _(content debt, not an ADR)_ |
| TAS + Tekton Chains keyless signing | ADR-017 |
| Per-tenant TPA via Helm chart | ADR-018 |
| OCI container registry in Nexus | ADR-019 |
| PaC build pipelines per tenant | ADR-020 |
| Maven via Nexus group + Lightwell repos | ADR-021 |
| snow-mock comments + multi-app AO policy | ADR-022 |
| Classify candidates = TPA affected_repos only | ADR-023 |
| OpenCode idle wait via GET /session/status | ADR-024 |
| Drop EDA/AO legacy MR resume dual-Verifier | ADR-025 |
| Approval policy = condition (not switch) | ADR-026 |
| Impact already_current skips MR poll | ADR-027 |
| Multi-app AO path + Oct 16 hardening (rollup) | ADR-028 |
| OpenCode UI gate (web sessions visible) | ADR-029 |
| Renovate OIDC via Keycloak | ADR-030 |
| Showcase Nexus webhook trigger script | ADR-031 |
| Async CI/CD Approval gates + parent/child ITSM | ADR-033 (superseded park model → ADR-035) |
| Student merges needs_approval in GitLab | ADR-034 (superseded → ADR-035 all merges in GitLab) |
| Webhook-driven AO, no Approval nodes | ADR-035 |
| CI/CD → EDA bridge (PipelineRun + Argo) | ADR-036 |
| Single AO eda_trigger + type switch | ADR-037 (superseded) |
| Four AO workflows (start/merged/build/deploy) | ADR-038 (Build superseded → ADR-039) |
| Merged+Build poll PaC (retire Build WF) | ADR-039 |
| Start prep = one JT (Prepare Remediation) | ADR-040 |
| AO merges auto_approve after Verifier | ADR-041 |
| SNOW comments with MR / pipeline URLs | ADR-042 |
| OpenCode session deep links + summary | ADR-043 |
| snow-mock comment Markdown + autolink | ADR-044 |
| Deploy bridge signal keyed by Argo revision | ADR-045 |
| Deploy SNOW comments link Argo / Route / console | ADR-046 |
| Parent INC = top-level status + child links only | ADR-047 |
| Deploy finalize parent from lifecycle artifacts | ADR-048 |
| Deploy promote-scoped signal + finalize soft-skip | ADR-049 |
| Gate auto_approve on the PR check, inside the merge | ADR-050 |
| Script ConfigMap edits skip existing tenants (accepted) | ADR-051 |
