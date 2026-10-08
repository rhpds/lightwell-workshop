# Handoff notes

Shared scratchpad for whoever (or whichever agent) picks this up next. Keep it
short — a line or two per item, delete entries once they are done. This is not
a changelog; `git log` already is one.

Architectural decisions that back these items live in [ADR.md](ADR.md). **Always
update ADR.md in the same change** when you add, change, or close a Handoff item
that implies a decision (Handoff = list; ADR = context / decision / consequences).

Last updated: 2026-10-08

## Where the pieces live

| Piece | Repo |
|---|---|
| Helm charts, Showroom content, dashboard | this repo (`rhpds/lightwell-workshop`), pushes straight to `main` |
| Catalog item `lb1815-lightwell-tenant` | `rhpds/agnosticv`, `rh1-2027/` — via PR |
| OpenCode agent prompts, EDA rulebooks, AAP playbooks | `rhpds/lw-sdlc-opencode` — via PR |

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

## Next up

1. **Automation Orchestrator** is installed by `bootstrap-infra` (AO CR +
   CNPG) and wired per tenant via `sdlc.orchestrator` (`enabled`, webhook
   paths, `existingSecret` from `ao-bootstrap`). Remaining gaps: ensure
   `APP_INTEGRATION_URL_ALLOWED_HOSTS` includes the AAP route host so AO can
   create the AAP integration, and keep SCM on `rhpds/lw-sdlc-opencode`.
   → [ADR-008](ADR.md#adr-008--automation-orchestrator-on-the-shared-platform)
2. **CI on `rhpds/lw-sdlc-opencode` is dead.** Every run since 2026-10-07 ends
   in `startup_failure` with zero jobs allocated, so there are no logs. The
   workflow file is byte-identical to the one behind the last green run and
   parses fine, so it is an org/repo Actions policy or billing problem — needs
   someone with repo-admin or `admin:org` to read
   `/actions/permissions`. Meanwhile images are built by hand.
   → [ADR-010](ADR.md#adr-010--opencode-image-pin-hand-built-tag)
3. **Quay org mismatch.** Repo variable `QUAY_IMAGE_NAME` is
   `quay.io/sshaaf/sdlc-opencode`, but `values.yaml` pins
   `quay.io/bluesman/sdlc-opencode:sha-5e19550` (hand-built from
   lw-sdlc-opencode `main @ 5e19550`). Pick one org, then repoint the other.
   → [ADR-010](ADR.md#adr-010--opencode-image-pin-hand-built-tag)
4. **`nexus.lightwellNetwork` is still empty in AgnosticV.** Planned fix is a
   fake Lightwell — a Maven mirror holding some `.rhlw-*` packages for Nexus to
   proxy — which removes the need for real credentials.
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
