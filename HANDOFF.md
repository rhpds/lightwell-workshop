# Handoff notes

Shared scratchpad for whoever (or whichever agent) picks this up next. Keep it
short — a line or two per item, delete entries once they are done. This is not
a changelog; `git log` already is one.

Architectural decisions that back these items live in [ADR.md](ADR.md). **Always
update ADR.md in the same change** when you add, change, or close a Handoff item
that implies a decision (Handoff = list; ADR = context / decision / consequences).

Last updated: 2026-10-08 (app-of-apps refactor + Acme apps + Renovate + snow-mock)

## Where the pieces live

| Piece | Repo |
|---|---|
| Helm charts, Showroom content, dashboard | this repo (`rhpds/lightwell-workshop`), pushes straight to `main` |
| Catalog item `lb1815-lightwell-tenant` | `rhpds/agnosticv`, `rh1-2027/` — via PR |
| OpenCode agent prompts, EDA rulebooks, AAP playbooks | `rhpds/lw-sdlc-opencode` — via PR |
| Acme sample apps (3) | `redhat-ads-tech/{wire-transfer-svc,benefits-mgmt-app,report-generator-app}` |

## Recently done

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

A full pipeline run was proven on tenant `49t9b`: Nexus `CREATED` → EDA →
Query TPA → Impact Analyzer → OpenCode → GitLab MR → MR Verifier.
On `tr59k-1` the AO path was also proven: Nexus → EDA Start → AO canvas
(Query TPA → Impact) → MR → Resume → MR Verifier.
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
  Image: `quay.io/redhat-ads-tech/snow-mock:1.0.0`.
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

## Next up

1. **Automation Orchestrator** is installed by `bootstrap-infra` (AO CR +
   CNPG) and wired per tenant via `sdlc.orchestrator` (`enabled`, webhook
   paths, `existingSecret` from `ao-bootstrap`). Remaining gaps: ensure
   `APP_INTEGRATION_URL_ALLOWED_HOSTS` includes the AAP route host so AO can
   create the AAP integration, and keep SCM on `rhpds/lw-sdlc-opencode`.
   → [ADR-008](ADR.md#adr-008--automation-orchestrator-on-the-shared-platform)
2. **CI on `rhpds/lw-sdlc-opencode` is dead** (org/Actions policy). Lab path is
   now **shared BuildConfig → ImageStream (OpenShift integrated registry)** via
   `bootstrap-infra` `opencodeImage` (ADR-013). Tenants leave
   `sdlc.opencodeImage` empty. External quay.io pins remain an override only.
   → [ADR-013](ADR.md#adr-013--shared-opencode-image-build-to-openshift-integrated-registry)
3. **First infra sync after enablement** must finish Job
   `opencode-image-publish` (ImageStream build) before OpenCode pods can pull.
   Bump `opencodeImage.gitRef`/`tag` and tenant `sdlc.opencodeImageTag` together.
4. **`nexus.lightwellNetwork` is still empty in AgnosticV.** Planned fix is a
   fake Lightwell — a Maven mirror holding some `.rhlw-*` packages for Nexus to
   proxy — which removes the need for real credentials. The Renovate integration
   (ADR-012) needs these artifacts seeded into the tenant Nexus
   `lightwell-java-remediated` repo; a provisioning Job to seed them is not yet
   built.
5. **Renovate module content not yet written.** The Showroom AsciiDoc for the
   Renovate module needs the student-facing `oc apply` for the RenovateJob CR
   (templated with Antora `{guid}` / `{openshift_cluster_ingress_domain}`
   attributes). The `discoveryFilters` must scope to `acme-{guid}/*` or a
   specific app (e.g. `acme-{guid}/report-generator-app`). Each app repo
   already has a `renovate.json` with the Lightwell preset + placeholder
   `hostRules`; the RenovateJob inline config overrides with real Nexus URLs.
5. **Older tenants on `zlvnr` are missing EDA job templates** (provisioned
   before the org-scoping fix). Re-run the bootstrap job or re-order them.
6. **`publishing-house/spec/modules/*.md` and `spec/design.md` still say
   Artifactory / Deep Agent / RHACM.** The Showroom content under `content/`
   was updated to Nexus / Lightwell OpenCode Agents / TSSC + DevSecOps; the
   outlines were not.

### Smaller things

- `podman-compose.yaml` has a `$PID`/`$!` interpolation bug and an obsolete
  `version:` key.
- `inject-env-secrets.sh` prints secret values to stdout.
- Running the local Antora preview rewrites `site.yml` (the dev-mode container
  injects `/antora/lib/dev-mode.js`). Revert it before committing.

## Gotchas worth knowing

- **Watch for fail-open.** Four separate bugs here had the same shape: the
  component reported success and left the tenant non-functional. Prefer a loud
  failure at render or bootstrap time over a green sync that does nothing.
  → [ADR-011](ADR.md#adr-011--prefer-fail-closed-over-fail-open)
- Hook Jobs use `hook-delete-policy: HookSucceeded`, so **absence means
  success** — do not go looking for the Job afterwards.
- Debugging a live tenant needs **cluster-admin**
  (`cluster_admin_agnosticd_sa_token` from the order), not the tenant login.
  The tenant user is Forbidden on `sdlc-<guid>` and `openshift-gitops`.
