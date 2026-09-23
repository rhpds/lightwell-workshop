# Lightwell SDLC remediation — per-tenant architecture

How one tenant of the Lightwell demo is wired, and what happens end to end when a
remediated artifact lands in that tenant's Nexus.

Everything below is scoped to **a single tenant**, identified by its `{guid}`
(the validation run used `6bq2v-1`). Every tenant gets its own copy of the
per-tenant resources; the platform services are shared by all tenants on the
cluster.

---

## 1. Component view

One Argo CD `Application` — `lightwell-tenant-{guid}` in `openshift-gitops` —
renders the `bootstrap-tenant` Helm chart and owns everything in the left-hand
box. Everything in the right-hand box was installed once by `bootstrap-infra`
and is shared.

```mermaid
flowchart LR
  subgraph tenant["Per tenant — Argo Application lightwell-tenant-{guid}"]
    direction TB

    subgraph ns_sdlc["Namespace sdlc-{guid}"]
      OC["Deployment opencode<br/>Service :4096"]
      OCUI["Route opencode-ui<br/>basic auth, user opencode"]
      OC --- OCUI
    end

    subgraph ns_nexus["Namespace lightwell-nexus-{guid}"]
      NX["Nexus 3 StatefulSet + PVC + Route"]
      RV["proxy redhat-packages-validated-{guid}"]
      RR["proxy redhat-packages-remediated-{guid}"]
      MC["proxy maven-central-{guid}"]
      NX --- RV
      NX --- RR
      NX --- MC
    end

    subgraph ns_job["Namespace lightwell-tenant-{guid}"]
      CFG["ConfigMap tenant-integration"]
      JOBS["bootstrap Jobs<br/>gitlab / aap / tpa-seed / eda / nexus-reconcile"]
    end
  end

  subgraph shared["Shared cluster services"]
    direction TB
    AAP["AAP 2.5 — namespace aap<br/>controller behind gateway"]
    EDA["EDA activation sdlc-remediation-{guid}<br/>Job pod in aap + Service :5000 + Route"]
    GL["GitLab — namespace gitlab<br/>project lightwell/lw-demo-help-app-{guid}"]
    TPA["Trusted Profile Analyzer<br/>namespace lightwell-tpa"]
    KC["Keycloak / SSO — namespace keycloak"]
    ARGO["OpenShift GitOps — namespace openshift-gitops"]
    SBX["Namespace sdlc-sandboxes<br/>verify Jobs land here"]
    AAP --- EDA
    TPA --- KC
  end

  ARGO ==> tenant
  RR -- "component CREATED webhook" --> EDA
  RV -- "component CREATED webhook" --> EDA
  EDA -- "run_job_template" --> AAP
  AAP -- "HTTP :4096 session + prompt_async" --> OC
  AAP -- "query SBOM / CVE" --> TPA
  OC -- "MR, notes" --> GL
  OC -- "oc create Job" --> SBX
  OC -- "oc create ns" --> EPH["Namespace pr-test-mr-{iid}<br/>BuildConfig + Deployment + edge Route"]
  SBX -- "Maven resolves via" --> NX
  EPH -- "builder stage resolves via" --> NX
```

Note the **activation is per tenant but lives in the shared `aap` namespace**:
EDA runs each activation as a Kubernetes Job pod there, fronted by a Service on
port 5000 and a Route. The activation name carries the guid, so tenants do not
collide, but the namespace is not isolated.

The ephemeral namespace `pr-test-mr-{iid}` is also cluster-scoped, not inside
the tenant boundary — it is created on demand by the agent and torn down after
the demo.

---

## 2. Demo flow

The authentic path, from the artifact fetch to the verification note on the
merge request.

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Maven client
    participant NX as Nexus lightwell-nexus-{guid}
    participant EDA as EDA sdlc-remediation-{guid}
    participant AAP as AAP controller
    participant TPA as TPA lightwell-tpa
    participant OC as opencode sdlc-{guid}
    participant GL as GitLab project
    participant SBX as Job in sdlc-sandboxes
    participant EPH as Namespace pr-test-mr-{iid}

    Dev->>NX: fetch artifact version *.rhlw-NNNNN
    NX->>NX: proxy redhat-packages-remediated-{guid} caches from<br/>packages.redhat.com/lightwell/java/remediated/
    NX-->>EDA: webhook.repository, names=component — action CREATED

    Note over EDA: rulebook condition — action == CREATED<br/>AND version contains rhlw-

    EDA->>AAP: run_job_template — SDLC Query TPA
    AAP->>TPA: query SBOM label for CVE / package context
    TPA-->>AAP: affected repos + package_info
    AAP-->>EDA: POST tpa_results back to the EDA webhook

    EDA->>AAP: run_job_template — SDLC Trigger Impact Analyzer
    AAP->>OC: POST /session then /session/id/prompt_async<br/>agent impact-analyzer
    Note right of AAP: the job returns here — the agent work<br/>is asynchronous and not in the job output
    OC->>GL: bump pom.xml, push branch update-artifact-{version}
    OC->>GL: open MR with agent-handoff JSON in the description
    GL-->>EDA: merge_request opened webhook

    EDA->>AAP: run_job_template — SDLC Trigger MR Verifier
    AAP->>OC: POST /session then prompt_async, agent mr-verifier
    OC->>GL: read MR, parse agent-handoff block
    OC->>SBX: create Job verify-mr-{iid} — mvn clean verify
    SBX->>NX: resolve .rhlw- artifact via in-cluster Nexus Service
    SBX-->>OC: job Complete or Failed + logs

    OC->>EPH: create namespace, BuildConfig with inline Dockerfile
    EPH->>NX: builder stage resolves .rhlw- artifact via Nexus
    OC->>EPH: Deployment + edge Route on port 8080
    OC->>EPH: smoke test GET /api/status
    EPH-->>OC: per-library status incl. lightwellFix version
    OC->>GL: post verification note on the MR
```

Steps worth understanding rather than just watching:

- **The AAP jobs are launchers, not the work.** `SDLC Trigger Impact Analyzer`
  and `SDLC Trigger MR Verifier` only create an opencode session and fire
  `prompt_async`. Their job output is a handful of tasks; none of the agent's
  reasoning, file edits, or `oc` calls appear there.
- **Two agents, deliberately disjoint.** `/app/opencode.json` defines
  `impact-analyzer` (the default) and `mr-verifier` as primary agents.
  `impact-analyzer` denies the `mr-verify-ephemeral` skill; `mr-verifier` denies
  `dependency-impact-remediation`. Neither can drift into the other's half of
  the pipeline.
- **The app repo ships no Dockerfile.** The ephemeral build passes a multi-stage
  Dockerfile inline via `--dockerfile`; the git source supplies only the code.
  Its builder stage points Maven at the tenant Nexus, otherwise the `.rhlw-`
  artifact cannot be resolved and the build looks like a bad bump when it is
  really a misconfigured build.

---

## 3. Why the `rhlw-` filter matters

Nexus fires `component CREATED` on the **first** cache of any component in a
proxy repo. That gives two useful properties and one trap.

```mermaid
flowchart TD
  A["Nexus caches a component<br/>in a tenant proxy repo"] --> B{"already cached?"}
  B -- yes --> Z["no event — artifact is a<br/>one-shot trigger per tenant"]
  B -- "no, first cache" --> C["webhook fires:<br/>action CREATED"]
  C --> D{"version contains rhlw- ?"}
  D -- no --> E["rulebook falls through to<br/>the catch-all debug rule"]
  D -- yes --> F["run_job_template: SDLC Query TPA"]
  F --> G["pipeline proceeds"]

  E -.->|"without the filter"| H["every transitive dependency matches"]
  H --> I["MR verify build resolves through<br/>the same proxies"]
  I --> J["each pulled artifact re-triggers<br/>the pipeline"]
  J --> K["run_job_template BLOCKS until the job ends<br/>— roughly one job per minute, serial"]
  K --> L["a cold cache becomes a long backlog,<br/>not a burst"]
```

Two consequences to plan the demo around:

1. **One shot per artifact per tenant.** Once the artifact is cached, refetching
   it produces no event. To re-run the demo, use a different `.rhlw-` version or
   reset the tenant's Nexus.
2. **EDA processes events serially.** `run_job_template` blocks until the AAP job
   completes, so events queue rather than run in parallel. Without the `rhlw-`
   filter, a cold cache produces a backlog that takes many minutes to drain.

---

## 4. Where to watch each stage

| Stage | Where to look |
| --- | --- |
| Artifact cached, webhook registered | Nexus console for `lightwell-nexus-{guid}` — proxy repos and browse/components |
| Event matched, job launched | AAP → Jobs list, and the EDA activation's log |
| TPA lookup | The `SDLC Query TPA` job output |
| **Agent reasoning and tool calls** | **The opencode web UI** at `https://opencode-ui-sdlc-{guid}.<apps-domain>` — the only place this is visible |
| Dependency bump | GitLab MR on branch `update-artifact-<version>`, `lightwell/lw-demo-help-app-{guid}` |
| Compile and unit test | Job `verify-mr-{iid}` in `sdlc-sandboxes` |
| Running remediated app | The edge Route in `pr-test-mr-{iid}`, path `/api/status` |
| Verdict | The verification note on the MR |

The opencode UI is served by the opencode server itself at `/` and is protected
by that server's own basic auth (user `opencode`). Sessions are stored under
`HOME=/tmp`, which is an `emptyDir` — **transcripts do not survive a pod
restart**, so avoid rolling the `opencode` Deployment mid-demo.

---

## 5. Per-tenant resource reference

| Resource | Name |
| --- | --- |
| Argo CD Application | `lightwell-tenant-{guid}` (in `openshift-gitops`) |
| OpenCode control plane namespace | `sdlc-{guid}` |
| Nexus namespace | `lightwell-nexus-{guid}` |
| Bootstrap jobs / config namespace | `lightwell-tenant-{guid}` |
| Nexus proxy — validated | `redhat-packages-validated-{guid}` → `https://packages.redhat.com/lightwell/java/validated/` |
| Nexus proxy — remediated | `redhat-packages-remediated-{guid}` → `https://packages.redhat.com/lightwell/java/remediated/` |
| Nexus proxy — Maven Central | `maven-central-{guid}` |
| EDA activation | `sdlc-remediation-{guid}` (Job pod in `aap`, Service `:5000`, Route) |
| GitLab project | `lightwell/lw-demo-help-app-{guid}` |
| OpenCode Service | `opencode.sdlc-{guid}.svc:4096` |
| OpenCode UI Route | `opencode-ui-sdlc-{guid}.<apps-domain>` |
| AAP organization | `user-{guid}` |

AAP job templates, in execution order: `SDLC Query TPA` →
`SDLC Trigger Impact Analyzer` → `SDLC Trigger MR Verifier`.

AAP 2.5 fronts the controller behind its gateway, so controller API calls use
the `/api/controller/v2/...` path rather than the pre-2.5 `/api/v2/...`.
