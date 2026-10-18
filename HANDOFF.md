# Handoff notes

Shared scratchpad for whoever (or whichever agent) picks this up next. Keep it
short — a line or two per item, delete entries once they are done. This is not
a changelog; `git log` already is one.

Architectural decisions that back these items live in [ADR.md](ADR.md). **Always
update ADR.md in the same change** when you add, change, or close a Handoff item
that implies a decision (Handoff = list; ADR = context / decision / consequences).

Last updated: 2026-10-18 (full chain verified on a freshly seeded tenant)

## Where the pieces live

| Piece | Repo |
|---|---|
| Helm charts, Showroom content, dashboard | this repo (`rhpds/lightwell-workshop`), pushes straight to `main` |
| Catalog item `lb1815-lightwell-tenant` | `rhpds/agnosticv`, `rh1-2027/` — via PR |
| OpenCode agent prompts, EDA rulebooks, AAP playbooks | `rhpds/lw-sdlc-opencode` — via PR |
| Acme sample apps (3) | `redhat-ads-tech/{wire-transfer-svc,benefits-mgmt-app,report-generator-app}` |
| AO Path 2 operator helper + docs | this repo — [`ao-trigger-helper/`](ao-trigger-helper/) (scripts + [`docs/`](ao-trigger-helper/docs/)) |

## Recently done

- **AO Path 2 operator helper** in [`ao-trigger-helper/`](ao-trigger-helper/) —
  scripts POST Nexus-shaped `CREATED` to EDA (`needs-approval` / `auto-approve`)
  and reset Acme repos. AO-context docs:
  [`DEMO-FLOW.md`](ao-trigger-helper/docs/DEMO-FLOW.md) (narrative),
  [`architecture.md`](ao-trigger-helper/docs/architecture.md) (wiring),
  [`DEMO-FLOW-INVESTIGATION.md`](ao-trigger-helper/docs/DEMO-FLOW-INVESTIGATION.md)
  (live snapshot). Index: [`docs/README.md`](ao-trigger-helper/docs/README.md).
  → [ADR-031](ADR.md#adr-031--showcase-nexus-webhook-trigger-script)

- **OpenCode web UI shows agent sessions.** Route `opencode-ui` now targets
  `opencode-ui-gate` (HTML bootstrap injecting `/app` into the SPA's open-
  projects localStorage). Fresh browsers list Impact/Verifier transcripts;
  AAP still calls Service `opencode:4096` directly. Live on `t8s2n` without
  restarting the opencode pod. → [ADR-029](ADR.md#adr-029--opencode-ui-gate-for-web-session-visibility)

- **Multi-app AO path (15–16 Oct).** Built the multi-app AO+SNOW+classify
  path (15 Oct), then hardened merge/OpenCode/classify, removed dual-Verifier,
  fixed approval branching, and taught Impact/AO to short-circuit when the
  remediating GAV is already on `main` (16 Oct). Live on `t8s2n` as AO
  **v18**; playbooks on tenant GitLab `lw-sdlc-opencode-local` + AAP sync.
  Details:
  → [ADR-028](ADR.md#adr-028--multi-app-ao-path-and-oct-16-hardening),
  [ADR-022](ADR.md#adr-022--snow-mock-comments-via-configmap--multi-app-ao-policy)–[027](ADR.md#adr-027--impact-already_current-skips-mr-poll)

- **`demo-update` landed on `rhpds/main`; tenant Argo sync restored.** Chart
  + AO canvas + snow-mock are on `main`; `lightwell-tenant-t8s2n` syncs from
  there. → [ADR-028](ADR.md#adr-028--multi-app-ao-path-and-oct-16-hardening)

- **OpenSpec multi-app smoke leftovers closed.** Benefits auto-approve with a
  real TPA hit; Renovate skip on classify comment. Verifier still defaults to
  GitLab “MR open” until ephemeral OpenCode skill is fixed
  (`verifier_use_opencode: true`).
  → [ADR-022](ADR.md#adr-022--snow-mock-comments-via-configmap--multi-app-ao-policy)

- Tenant renders and syncs with **no Lightwell Network credentials**. Nexus
  Secret no longer uses `required`; `nexus-reconcile.py` skips repos it cannot
  create instead of exiting 1. Credentials can be injected later with
  `automation/gitops/bootstrap-tenant/scripts/inject-env-secrets.sh`.
  → [ADR-001](ADR.md#adr-001--optional-lightwell-network-credentials)
- Dashboard is **off by default** (`sdlc.dashboard.enabled: false`). Its
  credential-sync hook sits at sync-wave 3 and used to block waves 4–5.
  → [ADR-002](ADR.md#adr-002--dashboard-off-by-default)
- EDA job templates are created **per AAP organization**, not Controller-wide
  by name, and all five exist. Previously the second tenant onwards got none.
  → [ADR-003](ADR.md#adr-003--eda-job-templates-scoped-per-aap-organization)
- `sdlc.opencodePermission: allow` — OpenCode defaults bash to `ask`, and a
  headless pod parks on that prompt forever.
  → [ADR-004](ADR.md#adr-004--unattended-opencode-tool-permission)
- Sandbox namespaces are **per tenant**: `sdlc-sandboxes-<guid>` and ephemeral
  prefix `pr-test-mr-<guid>`. Agent prompts read `SDLC_SANDBOX_NAMESPACE` /
  `EPHEMERAL_NS_PREFIX` from env (lw-sdlc-opencode#3, merged).
  → [ADR-005](ADR.md#adr-005--per-tenant-sandbox-namespaces)
- LiteLLM/MaaS wired through AgnosticV: model `qwen3-235b` (an alias — the
  upstream name `qwen3-235b-a22b` is rejected), 14d virtual keys.
  → [ADR-006](ADR.md#adr-006--litellm-model-alias-for-maas)
- EDA rulebook defaults from `sdlc.orchestrator.enabled` (true →
  `sdlc-remediation.yml` AO bridge; false → `sdlc-remediation-legacy.yml`).
  SCM default `rhpds/lw-sdlc-opencode`. See AO item below.
  → [ADR-007](ADR.md#adr-007--eda-rulebook-selected-by-orchestrator-flag),
  [ADR-009](ADR.md#adr-009--sdlc-scm-at-rhpdslw-sdlc-opencode)

- **`impact-analyzer` no longer hangs.** It carried `bash."*": "ask"`, and
  agent-level permission beats the chart's `sdlc.opencodePermission: allow`
  (the image's `/app/opencode.json` loads *after* `OPENCODE_CONFIG_CONTENT`).
  Fixed in [lw-sdlc-opencode#4](https://github.com/rhpds/lw-sdlc-opencode/pull/4),
  built as `sha-aad125a`. → [ADR-004](ADR.md#adr-004--unattended-opencode-tool-permission)

A full pipeline run was proven on tenant `49t9b`: Nexus `CREATED` → EDA →
Query TPA → Impact Analyzer → OpenCode → GitLab MR → MR Verifier.
On `tr59k-1` the AO path was also proven: Nexus → EDA Start → AO canvas
(Query TPA → Impact) → MR → Resume → MR Verifier.
Re-proven end to end on `8vjv7` (2026-10-09) on image `sha-aad125a`, with
`com.h2database:h2:2.2.219.rhlw-00001`: cache → Start Orchestrator → AO →
Query TPA → Impact Analyzer → MR !1 (one-line `pom.xml` bump) → Resume
Orchestrator → MR Verifier, ~90s from trigger to MR.
- **Renovate operator** deployed at cluster level (`bootstrap-infra`
  `templates/renovate/` — ArgoCD child Application pointing at the upstream
  OCI Helm chart v6.4.0, `nonroot-v2` SCC, OpenShift Route for the web UI,
  CRD install via template mode). Per-tenant SA + SCC + `renovate-token`
  secret deployed by `bootstrap-tenant`. Student creates the RenovateJob CR
  on demand from Showroom. Tested end-to-end on tenant `kbdhw`: Renovate
  discovered `lw-demo-help-app-kbdhw`, found `woodstox-core 6.0.3.rhlw-00001`
  in the tenant Nexus `lightwell-java-remediated` repo, and created MRs.
  Uses the upstream `lightwell-experience/renovate-config:java-remediated`
  preset via `extends`. → [ADR-012](ADR.md#adr-012--renovate-for-deterministic-remediation)
- **ServiceNow mock** deployed per tenant via `bootstrap-tenant`
  `templates/snow/` (namespace `snow-<guid>`, Deployment, Service, Route).
  Default: ConfigMap-mounted app from `files/snow-mock/` on UBI Python
  (comments API + UI). Override with `snow.image`. `SNOW_URL` /
  `SNOW_SVC_URL` on `tenant-integration`.
  → [ADR-022](ADR.md#adr-022--snow-mock-comments-via-configmap--multi-app-ao-policy)
- **ArgoCD admin password Job removed** from `bootstrap-infra`. The
  `set-admin-password` Job raced with the OpenShift GitOps operator. Use
  the operator-managed password or "Log in via OpenShift" instead.
- **Nexus startupProbe** added to the tenant StatefulSet (10s interval,
  60 attempts = 10 min). Nexus 3.76 takes 3-5+ minutes to start and the
  liveness probe was killing it before startup completed.
- **App-of-apps refactor** of `bootstrap-infra`. The monolithic chart (56
  templates, single ArgoCD app) is now an app-of-apps that creates 8 child
  Applications, each pointing at a standalone subchart under
  `automation/gitops/cluster/`. Components sync in parallel (GitLab + AAP
  at wave 0, Quay at wave 1, AO at wave 3). No AgnosticV changes — `repo_path`
  stays `automation/gitops/bootstrap-infra`.
  → [ADR-014](ADR.md#adr-014--app-of-apps-infra-pattern)
- **Per-tenant GitLab groups** with three Acme sample apps. Replaced the shared
  `lightwell` group and single `lw-demo-help-app` with per-tenant `acme-{guid}`
  groups containing `wire-transfer-svc` (high risk, AI target),
  `benefits-mgmt-app`, and `report-generator-app`. `gitlab.appSeeds` is a
  configurable list. `REMEDIATION_APP_GITLAB_PATH` points to `wire-transfer-svc`.
  → [ADR-015](ADR.md#adr-015--per-tenant-gitlab-groups-with-acme-apps)
- **Renovate-bot GitLab user** created per tenant with a scoped PAT. MRs from
  Renovate show as `Renovate Bot` instead of `root`. PAT stored as
  `renovate-token` secret in `sdlc-{guid}`.
  → [ADR-012](ADR.md#adr-012--renovate-for-deterministic-remediation)
- **Keycloak login label** set to "Lightwell Patch to Production Workshop" via
  a sync hook Job that patches the realm `displayName`.
- **BuildConfig `triggers: []` drift** fixed — OpenShift strips empty trigger
  arrays, causing perpetual OutOfSync.
- **Renovate operator web UI wired to Keycloak SSO.** OIDC client
  `renovate-ui` created by a sync hook Job in `bootstrap-infra`. Students
  log in with their tenant SSO credentials and only see their own
  RenovateJobs via `spec.access.adminUsers` (matched on Keycloak email,
  e.g. `user-{guid}@demo.redhat.com`).
  → [ADR-030](ADR.md#adr-030--renovate-oidc-via-keycloak)
- **Renovate namespace** moved from `sdlc-{guid}` (not accessible to tenant
  users) to `{username}-renovate` with `edit` RoleBinding + custom Role
  for RenovateJob/RenovateProject CRDs. Students create RenovateJobs from
  the Showroom terminal.
- **All hook Jobs switched to `BeforeHookCreation`** delete policy (12 Jobs
  across tenant and cluster charts). Prevents "spec.template immutable"
  errors when scripts change between syncs.
- **SDLC Inventory auto-created** in tenant AAP org. AAP 2.5+ doesn't
  create a default inventory; the EDA bootstrap script now creates one
  with a localhost host.
- **Build namespace RBAC** — tenant user granted `admin` in `build-{guid}`
  so they can view pipeline runs.
- **Repo name alignment** — `lightwell-java-remediated` → `lightwell-remediated`
  across showroom and RenovateJob config (matches ADR-021 naming).
- **GitHub Pages + spell check workflows** added. Antora site deploys to
  Pages on push to main; cspell checks `content/**/*.adoc` on push and PRs.
- **Showroom Module 2 rewritten** — Renovate web UI flow (OIDC login,
  Trigger button, Logs), `publish-remediation.sh` attachment script,
  `maven-public` registry URL, per-user access control, enterprise
  callouts (auto-merge, 100+ ecosystems, Vault/ExternalSecrets), SLSA
  Level 3 compliance, tradeoffs section.
- **PaC build infrastructure** per tenant. `build-{guid}` namespace with 3 PaC
  Repository CRs (one per app from `gitlab.appSeeds`), GitLab push webhooks
  pointing at the PaC controller, and secrets (GitLab PAT, Nexus push
  credentials, TPA OIDC). Repository CRs pass tenant-specific params
  (`image-registry`, `image-name`, `tpa-url`, `issuer-url`) so `.tekton/`
  PipelineRun YAML is identical across tenants. Toggle: `build.enabled`.
  `.tekton/` + `Containerfile` added to all 3 source repos. Pipeline
  verified end-to-end: git-clone → maven → buildah → SBOM → TPA upload.
  → [ADR-020](ADR.md#adr-020--pipelines-as-code-for-per-tenant-build-pipelines)
- **Maven builds via Nexus group with Lightwell hosted repos.** Removed
  redundant `maven-central-{guid}` and `maven-releases-{guid}` (Nexus is
  already per-tenant). Created `lightwell-remediated` and `lightwell-validated`
  hosted repos (aligned with official Lightwell Network naming). Updated
  `maven-public` group to include them (search order: lightwell repos first,
  then defaults). Pipeline Maven task uses `MAVEN_MIRROR_URL` pointing at the
  group URL. Lightwell proxy repos in the ConfigMap stay untouched (EDA/OpenCode
  need them). Hosted repos need seeding with `-rhlw-*` artifacts separately.
  → [ADR-021](ADR.md#adr-021--maven-builds-via-nexus-group-with-lightwell-hosted-repos)
- **OCI container registry in per-tenant Nexus.** Added Docker Bearer Token
  Realm, OCI hosted repository (`oci`) on port 5000, OCI Route
  (`nexus-oci-{guid}.{domain}`), and short-URL Route for the UI
  (`nexus-{guid}.{domain}`). Storage increased from 20Gi to 50Gi.
  `nexus-reconcile.py` creates the OCI repo and enables the token realm
  idempotently. Anonymous read, admin push.
  Nexus bumped from 3.76.1 to **3.96.4-ubi** for native OCI 1.1 referrers
  (Tekton Chains stores attestations without tag-based fallback). Community
  Edition EULA is accepted automatically by the reconcile script (required
  since 3.77). Verified end-to-end on fresh tenant `t3st1`: OCI repo
  created, image push + catalog working, no manual intervention.
  → [ADR-019](ADR.md#adr-019--oci-container-registry-in-per-tenant-nexus)
- **Per-tenant TPA** via upstream Helm chart. Removed the shared `rhtpa-operator`
  and `TrustedProfileAnalyzer` CR from `cluster/rhads`. Each tenant gets a
  `tpa-{guid}` namespace with PostgreSQL, S3 (ObjectBucketClaim), TPA server,
  importer, and a short-URL Route. RHDA backend is optional (`tpa.rhda.enabled`).
  Keycloak OIDC clients (`tpa-frontend`, `tpa-cli`) created once at cluster level
  in the `sso` realm; client secret copied per tenant. Default scopes:
  `create/read/update:document`; `delete:document` requires `tpa-admin` role.
  Templates live in `bootstrap-tenant/templates/tpa/` (not a subchart — Helm
  subchart value scoping prevents `guid` from reaching the subchart without
  AgnosticV changes). Old seed templates (`seed-tpa-keycloak.py`, demo-sbom
  ConfigMap) removed. Dataset uploaded per tenant via a Job using `tpa-cli`
  client credentials.
  → [ADR-018](ADR.md#adr-018--per-tenant-tpa-via-helm-chart)
- **OpenShift Pipelines + Tekton Chains keyless signing** added to the `rhads`
  child app. Pipelines operator installs via `subscription-pipelines.yaml`
  (channel `pipelines-1.24`, Automatic). A PostSync Job patches TektonConfig for
  multi-PVC support and configures Chains to use TAS Fulcio/Rekor with the
  cluster Kubernetes OIDC issuer. TAS namespace is now `trusted-artifact-signer`
  (was `lightwell-tas`). Keycloak OIDC client `trusted-artifact-signer` is
  created by the `rhtas-keycloak-setup` Sync Job. If signing is broken: check
  the `tektonconfig-patch` Job logs in `openshift-pipelines` — the Job now logs
  a WARNING if the Chains InstallerSet audience patch did not apply.
  → [ADR-017](ADR.md#adr-017--keyless-signing-via-tas--tekton-chains)

## Next up

0a. **Verified on a freshly seeded tenant (`54dp7`, 18 Oct).** Group deleted
   and re-seeded from the chart, nothing applied by hand: group public,
   `acme-deployment` public, `.tekton` pipelines and `.lightwell/policy.json`
   (with `riskClass`) injected at seed, PaC webhook on push + merge_request.
   Then Nexus event -> AO -> MR `!1`
   `[LW] 🔴 Bump h2 to 2.2.224.rhlw-70003 to fix CVE-2023-48795` ->
   `build-pull-request` filled the table (`5/5 tests passed`) -> merge ->
   `promote-to-deployment-repo` -> ArgoCD deployed `0126b6d`, pod 1/1.
   lw-sdlc-opencode#5 is merged and the image is `sha-7447545`.
   → [ADR-032](ADR.md#adr-032--remediation-mr-body-as-the-review-artifact)
1. **Automation Orchestrator** is installed by `bootstrap-infra` (AO CR +
   CNPG) and wired per tenant via `sdlc.orchestrator` (`enabled`, webhook
   paths, `existingSecret` from `ao-bootstrap`). Keep SCM on
   `rhpds/lw-sdlc-opencode`. The `APP_INTEGRATION_URL_ALLOWED_HOSTS` gap is
   **closed** — verified on `8vjv7`, the AAP route host is present on the
   backend, background-worker and worker, and the AAP integration created
   cleanly. → [ADR-008](ADR.md#adr-008--automation-orchestrator-on-the-shared-platform)
2. **CI on `rhpds/lw-sdlc-opencode` is dead** (org/Actions policy). Lab path is
   now **shared BuildConfig → ImageStream (OpenShift integrated registry)** via
   `bootstrap-infra` `opencodeImage` (ADR-013). Tenants leave
   `sdlc.opencodeImage` empty. External quay.io pins remain an override only.
   → [ADR-013](ADR.md#adr-013--shared-opencode-image-build-to-openshift-integrated-registry)
3. **First infra sync after enablement** must finish Job
   `opencode-image-publish` (ImageStream build) before OpenCode pods can pull.
   Bump `opencodeImage.gitRef`/`tag` and tenant `sdlc.opencodeImageTag` together.
4. **`nexus.lightwellNetwork` is still empty in AgnosticV**, so a fresh tenant
   comes up green with no Lightwell proxy repos and therefore **no Nexus
   webhooks** — the whole chain has no entry point until credentials are
   injected (`scripts/inject-env-secrets.sh`, then `nexus-reconcile` re-runs
   and creates both repos and both webhooks). Planned fix is a fake Lightwell
   Maven mirror. Real upstream
   (`packages.redhat.com/lightwell/java/remediated/`) is browsable with the
   credentials and carries `jackson/` and `woodstox/` trees, e.g.
   `jackson-databind` has 12 `.rhlw-*` rebuilds — useful for seeding.
   **Naming:** the chart creates `redhat-packages-{validated,remediated}-{guid}`.
   The name `lightwell-java-remediated` used in ADR-012 appears nowhere in
   `automation/` or `content/` — settle which is canonical before writing the
   seeding Job or the Renovate `hostRules`.
   **Contents:** seed only coordinates an Acme app declares *directly* in its
   `pom.xml` — SBOM matching is broader than the pom, and the agent dies on
   `dependency … not found in pom.xml` otherwise. Today only
   `com.h2database:h2` qualifies (upstream has no `org/apache/struts/`), so
   `benefits-mgmt-app` and `report-generator-app` cannot yet be targets.
   → [ADR-016](ADR.md#adr-016--trigger-artifacts-must-be-declared-dependencies-of-a-seeded-app)
5. **Renovate module content (Module 2) written and tested.** Student creates
   RenovateJob from Showroom terminal, injects fake remediation via
   `publish-remediation.sh` (attachment), triggers from Renovate web UI, reviews
   MR in GitLab, watches pipeline. Remaining: screenshots for MR-created log,
   PR activity, GitLab MR, pipeline run, TPA SBOM before/after. ArgoCD
   deployment step is a placeholder pending CD wiring for sample apps.
6. **Older tenants on `zlvnr` are missing EDA job templates** (provisioned
   before the org-scoping fix). Re-run the bootstrap job or re-order them.
7. **`publishing-house/spec/modules/*.md` and `spec/design.md` still say
   Artifactory / Deep Agent / RHACM.** The Showroom content under `content/`
   was updated to Nexus / Lightwell OpenCode Agents / TSSC + DevSecOps; the
   outlines were not.

### Smaller things

- `podman-compose.yaml` has a `$PID`/`$!` interpolation bug and an obsolete
  `version:` key.
- Running the local Antora preview rewrites `site.yml` (the dev-mode container
  injects `/antora/lib/dev-mode.js`). Revert it before committing.

## Gotchas worth knowing

- **An Argo `refresh=hard` annotation is not a sync.** On `cd2fp` the app
  reported `Synced` at the right revision while still serving a stale
  manifest; only an explicit sync operation picked up a new ConfigMap key.
- **The EDA activation's extra_vars never reach AO-launched job templates.**
  AO passes its own payload, so anything set only on the activation is
  invisible. Per-app data has to travel in `.lightwell/policy.json`, which
  classify carries into `affected_repos`.
- **`trigger-nexus-webhook.sh` synthesises a version that is not in Nexus.**
  Fine for exercising AO, but any build of the resulting MR dies on
  `Could not find artifact`. To test a build or a merge, trigger with a
  version `publish-remediation.sh` actually published.
- **After a hibernation everything takes minutes to serve.** GitLab, Keycloak,
  TPA and the AAP gateway all return HTTP 000 until they are ready. macOS also
  caches the negative DNS from while the cluster was down — use `--resolve`,
  or fire requests from inside the cluster.
- **TPA OIDC setup Job must not be a Sync hook.** ArgoCD processes hooks
  separately from regular resources. If the OIDC Job is a hook, the RBAC
  (Roles/RoleBindings) in the same sync never gets applied before the hook
  runs, causing a permissions loop. The Job is a regular resource at
  sync-wave 0; RBAC is at sync-wave -1.
- **TPA server needs 8Gi memory.** The per-tenant LimitRange defaults to
  8Gi per container. Lower limits cause OOMKill.
- **Migrating from shared to per-tenant TPA** leaves orphaned resources
  (old seed ConfigMaps, keycloak RBAC) that ArgoCD reports as `PruneSkipped`.
  Delete them manually or provision fresh tenants.
- **Watch for fail-open.** Four separate bugs here had the same shape: the
  component reported success and left the tenant non-functional. Prefer a loud
  failure at render or bootstrap time over a green sync that does nothing.
  → [ADR-011](ADR.md#adr-011--prefer-fail-closed-over-fail-open)
- Hook Jobs now use `hook-delete-policy: BeforeHookCreation` — the old
  Job is deleted before the new one is created on each sync. Absence
  between syncs means the previous run completed (check ArgoCD sync
  result for success/failure).
- **AgnosticV `common_password` can lack digits.** `lookup('password', ...,
  chars=['ascii_letters', 'digits'])` is a uniform sample — ~2% chance of
  all letters, no digits. AO rejects passwords without 3+ character classes.
  Workaround: the AO bootstrap script should append `1!` to the password,
  or AgnosticV should guarantee complexity.
- **Do not trigger within a minute of a tenant sync.** The sync re-runs
  `eda-bootstrap`, which can disable/enable the activation and restart the
  webhook listener; a Nexus POST landing in that gap is lost silently. Seen on
  `8vjv7`: listener pod created 23:46:59, trigger at 23:47:00, no chain. Check
  the `activation-job-*` pod age in `aap` before firing.
- **A cached artifact cannot re-trigger.** The webhook fires on *component
  created*, so re-pulling the same GAV does nothing — use a different version.
- **MR Verifier runs `verify-mr-<iid>` as a Job inside
  `sdlc-sandboxes-<guid>`**, not in an ephemeral `pr-test-mr-*` namespace.
  Looking for the latter and finding nothing is not a failure.
- Both OpenCode job templates **start the agent asynchronously** and report
  `successful` immediately. A green AAP job says nothing about whether the
  agent worked — read the `opencode` pod log or the session transcript.
- Debugging a live tenant needs **cluster-admin**
  (`cluster_admin_agnosticd_sa_token` from the order), not the tenant login.
  The tenant user is Forbidden on `sdlc-<guid>` and `openshift-gitops`.
