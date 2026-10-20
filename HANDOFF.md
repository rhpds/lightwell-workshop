# Handoff notes

Shared scratchpad for whoever (or whichever agent) picks this up next. Keep it
short — a line or two per item, delete entries once they are done. This is not
a changelog; `git log` already is one.

Architectural decisions that back these items live in [ADR.md](ADR.md). **Always
update ADR.md in the same change** when you add, change, or close a Handoff item
that implies a decision (Handoff = list; ADR = context / decision / consequences).

Last updated: 2026-10-20 (Module 2 registry bug fixed; the second symptom was the test harness — see Next up 0000000)

## Where the pieces live

| Piece | Repo |
|---|---|
| Helm charts, Showroom content, dashboard | this repo (`rhpds/lightwell-workshop`), pushes straight to `main` |
| Catalog item `lb1815-lightwell-tenant` | `rhpds/agnosticv`, `rh1-2027/` — via PR |
| OpenCode agent prompts, EDA rulebooks, AAP playbooks | `rhpds/lw-sdlc-opencode` — via PR |
| Acme sample apps (3) | `redhat-ads-tech/{wire-transfer-svc,benefits-mgmt-app,report-generator-app}` |
| Acme deployment manifests | `redhat-ads-tech/acme-deployment` — Helm chart for ArgoCD app-of-apps |
| AO Path 2 operator helper + docs | this repo — [`ao-trigger-helper/`](ao-trigger-helper/) (scripts + [`docs/`](ao-trigger-helper/docs/)) |

## Recently done

- **`argo-notifications-eda` namespace fix (19 Oct).** The Job was
  templated into `{{ .Release.Namespace }}` (`openshift-gitops`) while
  requesting the `lightwell-tenant-jobs` SA, which only exists in
  `lightwell-tenant-{guid}`. No pod was ever created, so the Sync hook
  never reached a terminal phase and every tenant order parked at wave 4
  until the RHDP playbook timed out — three orders failed this way before
  it was spotted. Now uses the `bootstrap-tenant.jobNamespace` helper
  like every other Job in the chart. The three live tenants were
  recovered by hand (terminate op, strip the hook finalizer, delete the
  stale Job, hard refresh), so **a fresh order is still the only real
  proof** — worth one before the next demo. → [ADR-036](ADR.md#adr-036--cicd--eda-bridge-pipelinerun--argo-producers)
- **`publish-remediation.sh` JAR fix (18 Oct).** Natale's change to
  republish the real upstream JAR meant Syft read `version=2.13.5` from
  the embedded `pom.properties`, so the SBOM showed no version change.
  Fixed: the script now patches `pom.properties` and the embedded
  `pom.xml` inside the JAR to reflect the `.rhlw` version before upload.
  Note which artifacts this applies to: `jackson-databind`,
  `commons-fileupload` and `flyway-core` all embed
  `META-INF/maven/.../pom.properties`, so the patch is what makes Syft
  report the remediated version. **`h2` embeds none**, so the patch is a
  no-op there and Syft falls back to the filename, which already carries
  the `.rhlw` version. Both paths work; only the first needs the fix.
- **`publish-remediation.sh` TPA route fix (18 Oct).** The SME's TPA
  route discovery used `oc get route` in the TPA namespace, which the
  tenant user can't access. Added `|| true` and a fallback to
  `server-tpa-{guid}.{domain}` (the API-serving route).
- **ArgoCD app-of-apps for sample apps (16 Oct).** Per-tenant AppProject
  (`acme-{guid}`), ArgoCD Application pointing at GitLab
  `acme-{guid}/acme-deployment`, role-based RBAC so tenant users see
  only their apps. Deployment repo cloned into GitLab during
  provisioning. `seed-app-tags` Job reads commit SHAs after initial
  builds and updates `values.yaml`. Promotion is a separate git commit
  (not pipeline-driven) — ready for AO integration. **Superseded:**
  `promote-to-deployment-repo` merged in the app repos' PR #1, so a
  merge to main now bumps `imageTag` in `acme-deployment` from the
  pipeline and ArgoCD deploys it. Verified end to end.
  Upstream deployment chart: `redhat-ads-tech/acme-deployment`.
- **Sample apps now runnable (16 Oct).** `report-generator-app` switched
  to H2 in-memory + landing page at `/`. `benefits-mgmt-app` runs on
  Tomcat with mock API servlet (benefits plan data). `wire-transfer-svc`
  rebranded to "Acme Inc. Bank". All three have unit tests (`mvn verify`)
  and PaC `run-tests` pipeline step.
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

00af. **~~AO → AAP job log link 403 for tenant user~~ → ADR-053.**
   `create-aap-tenant` only granted gateway **Organization Member**. That
   cannot list JTs or read `/jobs/{id}/stdout` (verified `user-cng2l`:
   jobs count 0, job 785 → 403). Gateway **Organization Audit** is a no-op
   for Controller jobs. Fix: also attach Controller org **Auditor** via
   `/api/controller/v2/roles/{auditor}/users/`. Chart updated; **cng2l
   patched live** (Auditor + Member). Reused tenants need the same attach
   or a re-run of `create-aap-tenant`.
   → [ADR-053](ADR.md#adr-053--tenant-users-get-controller-org-auditor-for-job-logs)

00ae. **~~SNOW titles `[unknown]` despite TPA CVE~~ → ADR-052 (lab on cng2l).**
   Nexus → Start forwards `cve_id: unknown` as an AAP **extra_var**, which
   shadows every later `set_fact: cve_id=CVE-…` from query-tpa. Parent PATCH
   and child create read the extra_var and wrote `[unknown]` even when
   `package_info.cve_id` was correct. Fix (local `lw-sdlc-opencode`, injected
   into AAP project 7 on `cng2l`): pick first `^CVE-[0-9]` from
   `package_info` / `resolved_cve_id` / `cve_id`; normalize `unknown` → `CVE-`
   at Start + parent create. Verified e2e: commons-text
   `1.9.rhlw-102844` → INC titles `[CVE-2022-42889]`, benefits !10 merged,
   parent Resolved; h2 `2.2.224.rhlw-102845` → `[CVE-2023-48795]`, wire !18
   left open. **Still push `lw-sdlc-opencode`** (not on SCM yet).
   → [ADR-052](ADR.md#adr-052--snow-cve-titles-ignore-extra_var-unknown)

00ad. **~~auto_approve merge waits 2 minutes~~ → ADR-041 (lab on cng2l).**
   Start Merge JT pauses `merge_delay_seconds=120` before GitLab merge so
   the open MR is visible. Node renamed “Wait 2m + merge…”. Inject
   `merge-gitlab-mr.yml` + republish Start; push `lw-sdlc-opencode`.

00ac. **~~Deploy fan-out → wire finalize fail~~ → ADR-049 (lab on cng2l).**
   Bridge POSTed Deploy for every AO path on shared Argo Healthy; wire had
   no child → finalize failed → `completed_with_errors`. Fix: bridge POSTs
   only the app in the promote commit title; finalize soft-skips when no
   parent. Bridge promote-scoped + finalize soft-skip live on `cng2l`; push
   `lw-sdlc-opencode` for SCM durability.
   → [ADR-049](ADR.md#adr-049--deploy-signals-only-the-promoted-app-finalize-soft-skips-orphans)

00ab. **~~Deploy finalize empty parent~~ (lab cng2l).** Deploy *did* fire
   (bridge `20116e7b` → lifecycle OK with `parent_incident=INC0000001`);
   finalize failed because Deploy EDA has no `trigger.parent_incident`.
   Fix: finalize ← `${lc_deployed.artifacts.parent_incident}`; lifecycle
   never exports `""` (AAP drops it); finalize also looks up by
   `cmdb_ci`/`gitlab_path`. Deploy **v5**; reinjected; catch-up finalize
   **#679** successful → parent Resolved. Still push `lw-sdlc-opencode`.
   Superseded for fan-out noise by **00ac** / ADR-049.

0000000. **Module 2 (Renovate) — one real bug, now fixed; the other was my
   test.** Diagnosed with `LOG_LEVEL=debug` on the Renovate job (at default
   level it logs nothing about which versions it retrieved or discarded).

   **Real bug, fixed:** the repo's `renovate.json` extends
   `github>lightwell-experience/renovate-config:java-remediated`, whose
   custom manager hardcodes
   `"registryUrlTemplate": "https://packages.redhat.com/lightwell/java/remediated"`.
   The tenant gets `401 Dependency lookup unauthorized` from it. Module 2's
   `packageRules.registryUrls` override does **not** displace a manager's own
   `registryUrlTemplate` — confirmed with both `custom.regex` and `regex`.
   Fix: module 2's RenovateJob now redefines `customManagers` inline with the
   tenant Nexus, instead of trying to patch the preset's manager.

   **Not a bug — my test harness:** the second symptom (no update proposed
   even with the right registry) was caused by the test generating
   clock-derived suffixes. The versioning regex maps the rhlw digits to
   `major`, so `rhlw-121618` is a major increment of ~121k and Renovate
   silently drops it:
   `Skipping …@2.13.5.rhlw-999999 because major increment 878381 exceeds maxMajorIncrement 500`.
   With an increment of 1 it works immediately — verified, Renovate opened
   `[Lightwell] Update dependency com.fasterxml.jackson.core:jackson-databind`.
   `test-lab-flow.sh` now derives the suffix from the pom's current rhlw
   number + 1, matching the lab's `rhlw-00001` / `rhlw-00002` sequence.

   Worth knowing generally: a suffix that jumps by more than 500 is discarded
   without an error. Anyone hand-triggering a demo should keep the sequence
   tight.

   Still outstanding: `publish-remediation.sh` overwrites
   `maven-metadata.xml` rather than appending, so Nexus lists only the newest
   rebuild.

000000. **CVE lookup fixed and verified; CVSS still blank.**
   `lw-sdlc-opencode` PR #8 is merged and confirmed on `8gmp5` (AAP project
   synced to `a8386b6`, Prepare job 328). All four new tasks ran and the MR
   facts now resolve from the Lightwell advisory:

   ```
   cve_id:          CVE-2022-42889
   cve_title:       Apache Commons Text prior to 1.10.0 allows RCE ...
   cve_description: <full upstream text>
   cvss_score:      ""          <- still empty
   ```

   **Remaining gap:** `cvss_score` stays blank because the seeded CVE records
   carry no `base_score`, so the MR renders "CVSS Score: not scored" even
   with the CVE correctly identified. Either the dataset needs records with
   scores, or the MR body should fall back to the advisory's own
   `severity[].score` (publish-remediation.sh writes a CVSS v3 vector into
   every RHLW advisory, so the data is already there).

   Requires advisories published with the coordinate in the summary — i.e.
   `publish-remediation.sh` at 3bda34f or later.

00000a. **Blast radius 504s on a reused tenant.** Hit three times on `8gmp5`:
   `"benefits-mgmt-app: packages: HTTP Error 504"` from
   `/api/v3/sbom/{id}/packages`, after which classify fails closed with
   "No blast radius ... Skipping remediation". The same call returns 200 in
   0.46s when TPA is idle, and a fresh tenant (`jq89x`) produced MRs fine.
   Correlates with accumulated SBOMs — `8gmp5` had 7 for one app and
   Postgres at ~500m CPU. Fails safe, but it silently drops an app from the
   blast radius, so a demo re-run on a warm tenant can look like the
   remediation simply ignored an application. Worth a retry/backoff in
   `tpa_blast_radius.py` rather than one attempt.

00000. **TPA CVE dataset silently does not ingest on a fresh tenant.**
   Both tenants on `cluster-klrql` came up with `GHSA-OSV: 285` and
   **`CVElist-v5: 0`**, while `8gmp5` on the older cluster has 222. The
   `tpa-dataset-upload-cve` Job reports `HTTP response code: 201` and
   "Upload and ingestion successful" — nothing lands. Consequence: no CVE
   records at all, so `/api/v3/vulnerability` is empty and every remediation
   MR renders `CVE: not referenced`, which is what made Module 3 look like it
   had no advisory data.

   **Workaround (verified):** re-POST the zip by hand and it ingests in ~7s —
   `curl -k -X POST "$TPA/api/v3/dataset?labels.importer=CVElist-v5"
   -H "Content-Type: application/zip" -H "Authorization: Bearer $TOK"
   --data-binary @lb1815-cve.zip` → 201 with the full file list, and the count
   goes 285 → 507.

   **Unproven hypothesis:** the CVE and OSV upload Jobs both sit at sync-wave
   3 and POST concurrently; one appears to be accepted and dropped. Serialising
   them (wave 3 and 4) is the obvious thing to try. Not yet tested.

   Worth fixing properly — a fresh tenant is what every attendee gets, and
   this one fails silently with a success message.

0000. **Gotcha, not a task: script ConfigMap edits never reach an *existing*
   tenant.** The tenant Argo Application sets
   `ignoreDifferences: [{jsonPointers: ["/data"], kind: ConfigMap}]` — a rule
   from the RHDP side, in neither this repo nor agnosticv. File-backed script
   ConfigMaps are frozen at creation-time content while Argo reports
   `Synced`. Affects `bridge.py`, `snow-mock` code/static,
   `nexus-reconcile.py`, eda/ao bootstrap sources, `opencode-ui-gate`.

   **Not a lab problem:** every attendee gets a newly ordered tenant, and
   creation is not a diff — a fresh order always has current content. This
   only bites a lab developer reusing one tenant across chart changes.

   **Workaround when it does bite** (a plain sync will not do it, hard
   refresh or not):
   ```
   oc create configmap <name> -n <ns> --from-file=<key>=<path> \
     --dry-run=client -o yaml | oc apply -f -
   oc rollout restart deploy/<name> -n <ns>
   ```
   How it surfaced: Shaaf's ADR-049 promote-scoping looked broken on `8djv7`
   when his code was fine — the tenant was running a 401-line `bridge.py`
   against 493 in the repo, so `wire-transfer-svc` (never merged) was marked
   deployed three times. Patched by hand on both `8djv7` and `8gmp5`.
   Decided **not** to engineer around it.
   → [ADR-051](ADR.md#adr-051--script-configmap-edits-do-not-reach-an-existing-tenant-accepted)

000. **FIXED (pending PR merge + AO republish): `auto_approve` merged with
   the validation table still `Pending`.** On `8djv7`, AO merged the MR ~33 s
   after it opened while `build-pull-request` — the pipeline that fills the
   table — did not start until 43 s *after* the merge. All seven rows stayed
   `Pending` and SNOW still recorded "auto-merged after the verifier passed".
   `verifier_ok` only checks that the Verifier JT returned successful, and
   those JTs report success as soon as they launch the async agent, so the
   gate could not fail. The h2 → `wire-transfer-svc` run cleared the table
   logic itself (6/7 ✅ Passed, 🔴 HIGH, correctly left open) — it was only
   ever a race on the auto path.

   **Fix:** `merge-gitlab-mr.yml` polls the `build-pull-request` commit
   status on the MR head and asserts green before merging. Inside the merge
   playbook rather than as a separate AO node (Shaaf's call, and the better
   one): check and merge stay atomic, and the Start canvas keeps a single
   node. The fixed `merge_delay_seconds=120` pause is dropped — the real
   wait already leaves the MR open ~110 s, which is the window it existed
   for, and a sleep cannot tell a slow pipeline from a failed one.

   This reverses the earlier "not adopted" position (previous ADR-050),
   decided by Natale.

   **To land:** [PR #7](https://github.com/rhpds/lw-sdlc-opencode/pull/7)
   must merge, **then** AO republish. Until both, tenants auto-merge
   unvalidated exactly as before. Then re-run both scenarios and confirm the
   auto-merged MR comes out with a filled table.
   → [ADR-050](ADR.md#adr-050--gate-auto_approve-on-the-pull-request-check-inside-the-merge)

000a. **Idea (Natale): pre-pull Tekton images with a DaemonSet.** Cold
   cluster image pulls delay first PaC runs; a prepuller would make Module
   3 timings more predictable.

0a. **Remediation MR body — verified end to end on a freshly seeded tenant
   (`54dp7`, 18 Oct).** Seed -> Nexus event -> AO -> MR
   `[LW] 🔴 Bump h2 ... to fix CVE-2023-48795` -> pipeline fills the
   validation table -> merge -> promote -> ArgoCD deploys. Agent side is
   merged (`sha-7447545`).
   → [ADR-032](ADR.md#adr-032--remediation-mr-body-as-the-review-artifact)

0b. **Upstream PRs: six merged (18 Oct), three open.** The app repos own
   their pipelines — the chart does not inject them (removed in 24f3114,
   because James iterates on the same PaC pipelines and a seed-time copy
   would silently overwrite him). `#1` pipelines and `#2` integration
   tests are merged in all three repos. **`#3` artifact checks is open**
   in each ([wire-transfer-svc](https://github.com/redhat-ads-tech/wire-transfer-svc/pull/3),
   [benefits-mgmt-app](https://github.com/redhat-ads-tech/benefits-mgmt-app/pull/3),
   [report-generator-app](https://github.com/redhat-ads-tech/report-generator-app/pull/3)):
   those commits were pushed after `#1` had already been merged, so they
   never reached main.

0c. **Validation table: six of eight rows are real.** Unit and integration
   tests from surefire/failsafe; binary integrity verified against the
   checksum Nexus records (an *integrity* check — the tenant mirror ships
   no detached GPG signature, so it is labelled as such); licence compared
   between the base and remediated POM, normalised so h2's
   "MPL 2.0 or EPL 1.0" vs "MPL 2.0" + "EPL 1.0" is not a false alarm;
   SBOM generated by the CycloneDX Maven plugin and asserted to list the
   bumped coordinate; dependency compatibility asserts the pom declares
   what the build resolved. **Regression scan is still Pending and needs a
   decision** — "behavioural diff" means running the suite against the
   target-branch baseline too, which doubles build time. Nothing is ever
   reported green without having been measured.
1. **~~The auto-approve path cannot happen~~ → fixed (real TPA blast radius).**
   `query-tpa.yml` matches GAV → SBOM `name` → `acme-{guid}/{app}`
   (`tpa_blast_radius.py`). Live on `cng2l`: flyway → benefits; h2 → wire.
   Parent/child SNOW + canvas in workshop + `lw-sdlc-opencode` (`ece73c4`).
   **Still push** local `fetch-app-policy.yml` (`auto_approve` allowlist) and
   republish AO + sync AAP for CI/CD gates (1a).
   → OpenSpec `ao-operator-async-remediation`; [ADR-033](ADR.md#adr-033--async-cicd-via-ao-approval-patch)

1a. **Merged+Build poll PaC (ADR-039) — live on cng2l (lab inject).**
   AO Merged **v3**: SNOW merged → Poll PaC → SNOW build_*; on
   `build_failed`, lifecycle JT fails after commenting (`fail_on_bad_outcome`)
   so the AO run is Failed. Build WF retired; bridge quiet. Controller
   project `scm_update_on_launch=false` + playbook inject (push
   `lw-sdlc-opencode` for durability). TPA SBOM upload 500 remains.
   → [ADR-039](ADR.md#adr-039--mergedbuild-one-canvas-poll-pac)

1b. **Prepare Remediation (ADR-040) — live on cng2l (lab inject).**
   Start **v4**: `eda_trigger` → JT `SDLC Prepare Remediation` (parent
   SNOW → TPA → classify → comment → children) → `apps_loop`. Playbook
   `prepare-remediation.yml` + JT #24 injected; push `lw-sdlc-opencode`
   when you want SCM durability.
   → [ADR-040](ADR.md#adr-040--start-prep-as-one-aap-jt-prepare-remediation)

1c. **snow-mock list filters `cmdb_ci` + `guid`.** Lifecycle lookup uses
   `GET /api/v1/incidents?cmdb_ci=…&guid=…&open_only=1` instead of scanning
   200 opens client-side. Create playbooks stamp `guid` on parent/child.
   Roll snow-mock + reinject `snow-lifecycle-event.yml` on live tenants.

1e. **benefits missing GitLab MR→EDA webhook (cng2l).** Chart `ensure_mr_webhook`
   should cover every `remediation_owner=ao` seed; live tenant only had it on
   wire-transfer. AO auto-merge of benefits MR !1 did not start Merged WF.
   Hook added by hand on benefits; confirm create-gitlab job covers all AO
   seeds on next provision / re-run.

1d. **Prepare set_stats concat (cng2l Start v5 fail).** AAP concatenates
   string/list `set_stats` across plays in one job →
   `parent_incident=INC…INC…`, duplicated `ao_apps` without
   `child_incident` on the first item → Impact/loop fail. Fix:
   `sdlc_suppress_set_stats` in imported plays + one final export in
   `prepare-remediation.yml`. Reinject before next smoke.

2. **Automation Orchestrator** is installed by `bootstrap-infra` (AO CR +
   CNPG) and wired per tenant via `sdlc.orchestrator` (`enabled`, webhook
   paths, `existingSecret` from `ao-bootstrap`). Keep SCM on
   `rhpds/lw-sdlc-opencode`. The `APP_INTEGRATION_URL_ALLOWED_HOSTS` gap is
   **closed** — verified on `8vjv7`, the AAP route host is present on the
   backend, background-worker and worker, and the AAP integration created
   cleanly. → [ADR-008](ADR.md#adr-008--automation-orchestrator-on-the-shared-platform)
3. **CI on `rhpds/lw-sdlc-opencode` is dead** (org/Actions policy). Lab path is
   now **shared BuildConfig → ImageStream (OpenShift integrated registry)** via
   `bootstrap-infra` `opencodeImage` (ADR-013). Tenants leave
   `sdlc.opencodeImage` empty. External quay.io pins remain an override only.
   → [ADR-013](ADR.md#adr-013--shared-opencode-image-build-to-openshift-integrated-registry)
4. **First infra sync after enablement** must finish Job
   `opencode-image-publish` (ImageStream build) before OpenCode pods can pull.
   Bump `opencodeImage.gitRef`/`tag` and tenant `sdlc.opencodeImageTag` together.
5. **`nexus.lightwellNetwork` is still empty in AgnosticV**, so a fresh tenant
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
6. **Renovate module content (Module 2) tested end-to-end (18 Oct).**
   `publish-remediation.sh` publishes a remediated JAR (real upstream binary
   with patched `pom.properties` so Syft reports the `.rhlw` version) and
   OSV advisories to TPA. Renovate detects the bump, student merges, Tekton
   builds, TPA shows reduced vuln count. Screenshots added.
   **Remaining:** AgnosticV needs Showroom UI tabs for TPA and Nexus
   (currently patched manually on test clusters via `SHOWROOM_UI_CONFIG`).
7. **Older tenants on `zlvnr` are missing EDA job templates** (provisioned
   before the org-scoping fix). Re-run the bootstrap job or re-order them.
8. **`publishing-house/spec/modules/*.md` and `spec/design.md` still say
   Artifactory / Deep Agent / RHACM.** The Showroom content under `content/`
   was updated to Nexus / Lightwell OpenCode Agents / TSSC + DevSecOps; the
   outlines were not.

### Smaller things

- `podman-compose.yaml` has a `$PID`/`$!` interpolation bug and an obsolete
  `version:` key.
- Running the local Antora preview rewrites `site.yml` (the dev-mode container
  injects `/antora/lib/dev-mode.js`). Revert it before committing.

## Gotchas worth knowing

- **Never use `.Release.Namespace` in `bootstrap-tenant`.** The chart is
  deployed by an Application whose destination is `openshift-gitops`, so
  `.Release.Namespace` renders as `openshift-gitops` — not the tenant
  namespace you probably meant. Jobs belong in
  `{{ include "bootstrap-tenant.jobNamespace" . }}`, which is where the
  `lightwell-tenant-jobs` SA lives. A Job pointed elsewhere never gets a
  pod (`error looking up service account ...: not found`), and as a Sync
  hook it then blocks the whole tenant sync forever. `helm template`
  renders it happily; only a real order catches it.
- **Argo needs both a hard refresh and a sync when chart *files* change.**
  An explicit sync alone picked up a changed ConfigMap *key* on `cd2fp`,
  but on `54dp7` a change to `files/snow-mock/app.py` (pulled in by
  `.Files.Get`) was invisible: the app reported `Synced` at the right
  revision, did not list the ConfigMap as OutOfSync, and the live object
  had not been touched for three days. `argocd.argoproj.io/refresh=hard`
  first, *then* sync. Pods also need a rollout restart afterwards —
  a ConfigMap change does not restart them.
- **The EDA activation's extra_vars never reach AO-launched job templates.**
  AO passes its own payload, so anything set only on the activation is
  invisible. Per-app data has to travel in `.lightwell/policy.json`, which
  classify carries into `affected_repos`.
- **Demo Path 2 entry = `publish-remediation.sh` only.** Do **not** use
  `trigger-nexus-webhook.sh` for demos/e2e — testing/debug when Nexus→EDA
  webhooks are missing. Real path: publish → Nexus CREATED webhook → EDA → AO.

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
