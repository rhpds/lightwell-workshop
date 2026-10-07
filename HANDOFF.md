# Handoff notes

Shared scratchpad for whoever (or whichever agent) picks this up next. Keep it
short — a line or two per item, delete entries once they are done. This is not
a changelog; `git log` already is one.

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
- Dashboard is **off by default** (`sdlc.dashboard.enabled: false`). Its
  credential-sync hook sits at sync-wave 3 and used to block waves 4–5.
- EDA job templates are created **per AAP organization**, not Controller-wide
  by name, and all five exist. Previously the second tenant onwards got none.
- `sdlc.opencodePermission: allow` — OpenCode defaults bash to `ask`, and a
  headless pod parks on that prompt forever.
- Sandbox namespaces are **per tenant**: `sdlc-sandboxes-<guid>` and ephemeral
  prefix `pr-test-mr-<guid>`. Agent prompts read `SDLC_SANDBOX_NAMESPACE` /
  `EPHEMERAL_NS_PREFIX` from env (lw-sdlc-opencode#3, merged).
- LiteLLM/MaaS wired through AgnosticV: model `qwen3-235b` (an alias — the
  upstream name `qwen3-235b-a22b` is rejected), 14d virtual keys.
- EDA rulebook falls back to `sdlc-remediation-legacy.yml` unless `sdlc.ao.*`
  is configured. See the AO item below.

A full pipeline run was proven on tenant `49t9b`: Nexus `CREATED` → EDA →
Query TPA → Impact Analyzer → OpenCode → GitLab MR → MR Verifier.

## Next up

1. **Automation Orchestrator is not installed anywhere.** `bootstrap-infra`
   deploys nothing for it. Until someone supplies `sdlc.ao.baseUrl`,
   `clientId`, `clientSecret`, `startWebhookPath` and `resumeWebhookPath`, the
   chart stays on the legacy rulebook. Setting `baseUrl` alone fails rendering
   on purpose — the orchestrator playbooks assert on all four.
2. **CI on `rhpds/lw-sdlc-opencode` is dead.** Every run since 2026-10-07 ends
   in `startup_failure` with zero jobs allocated, so there are no logs. The
   workflow file is byte-identical to the one behind the last green run and
   parses fine, so it is an org/repo Actions policy or billing problem — needs
   someone with repo-admin or `admin:org` to read
   `/actions/permissions`. Meanwhile images are built by hand.
3. **Quay org mismatch.** Repo variable `QUAY_IMAGE_NAME` is
   `quay.io/sshaaf/sdlc-opencode`, but `values.yaml` pins
   `quay.io/bluesman/sdlc-opencode:sha-5e19550` (hand-built from
   lw-sdlc-opencode `main @ 5e19550`). Pick one org, then repoint the other.
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
- Hook Jobs use `hook-delete-policy: HookSucceeded`, so **absence means
  success** — do not go looking for the Job afterwards.
- Debugging a live tenant needs **cluster-admin**
  (`cluster_admin_agnosticd_sa_token` from the order), not the tenant login.
  The tenant user is Forbidden on `sdlc-<guid>` and `openshift-gitops`.
