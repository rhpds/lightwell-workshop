# Demo flow

The control plane has four outcomes. A person merges every platform request. `auto_approve` and `needs_approval` are written on the merge request and do not merge it.

## 1. One platform application, tests match

`commons-text` `1.9.rhlw-00001` affects only `benefits-mgmt-app` (`remediation_owner: ao`, `approval: auto_approve`, risk `LOW`). This is the path that ran to resolution on tenant `6wprg`.

```mermaid
flowchart TD
  publish["Publish commons-text 1.9.rhlw-00001"]
  nexus["Nexus CREATED webhook"]
  intake["lightwell-intake"]
  parent["Snow parent INC, opened before the TPA query"]
  tpa["TPA: benefits-mgmt-app only"]
  policy["policy.json: owner ao, approval auto_approve, risk LOW"]
  child["Child incident for benefits-mgmt-app"]
  job["RenovateJob lw-benefits-mgmt-app"]
  mr["Merge request, pom.xml version only"]
  pr["build-pull-request"]
  tests["fetch-source, run-tests, baseline-tests"]
  diff{"Outcome differences"}
  skip["adapt skipped"]
  report["report-validation: measured rows passed"]
  gate["GitLab keeps Merge disabled until the pipeline succeeds"]
  person["Person merges"]
  main["build-push-to-main"]
  build["maven-build, build-image, SBOM to TPA, promote image tag"]
  argo["wait-for-argo: acme-apps-guid Synced and Healthy"]
  resolve["resolve-incident closes the child, then the parent"]

  publish --> nexus --> intake --> parent --> tpa --> policy
  policy --> child --> job --> mr --> pr --> tests --> diff
  diff -->|"0"| skip --> report --> gate --> person --> main --> build --> argo --> resolve

  style person fill:#f8d7da,stroke:#b02a37,stroke-width:2px
```

## 2. The same request when test outcomes differ

This is the other branch of `build-pull-request`. The publish, intake, and deploy stages stay the same as scenario 1.

```mermaid
flowchart TD
  diff{"Outcome differences"}
  adapt["adapt, 30 minute timeout"]
  copy["Copy the workspace into the OpenCode sandbox"]
  agent["OpenCode agent lightwell-remediation, block until the session is idle"]
  allow{"Diff inside src/main, src/test, REMEDIATION.md"}
  push["Pipeline token commits the adaptation"]
  refuse["Refuse the diff and fail the task. pom.xml is never pushed"]
  report["report-validation"]
  person["Person merges after the pipeline is green"]
  main["build-push-to-main, same deploy closure as a clean diff"]

  diff -->|"not 0"| adapt --> copy --> agent --> allow
  allow -->|yes| push --> report --> person --> main
  allow -->|no| refuse

  style person fill:#f8d7da,stroke:#b02a37,stroke-width:2px
  style refuse fill:#f8d7da,stroke:#b02a37,stroke-width:2px
```

## 3. A platform application and a Renovate-owned application in one blast radius

Trusted Profile Analyzer currently finds `h2` in `wire-transfer-svc` and `report-generator-app`. `jackson-databind` has the same shape. `wire-transfer-svc` is `owner: ao`, `approval: needs_approval`, risk `HIGH`. `report-generator-app` is `owner: renovate`.

```mermaid
flowchart TD
  publish["Publish an h2 or jackson-databind .rhlw coordinate"]
  intake["lightwell-intake"]
  parent["Snow parent, opened before the TPA query"]
  tpa["TPA: wire-transfer-svc and report-generator-app"]
  wire["wire-transfer-svc: child incident and one RenovateJob"]
  skip["Comment on the parent: skip report-generator-app. No RenovateJob for it"]
  mr["Merge request on wire-transfer-svc. Risk row HIGH, action needs_approval"]
  pr["build-pull-request. adapt only if outcomes differ"]
  person["Person merges. needs_approval does not add a second gate"]
  main["build-push-to-main for wire-transfer-svc"]
  healthy{"acme-apps-guid Healthy on the promote commit"}
  close["Resolve the wire-transfer child. It is the only child, so resolve the parent"]
  hold["Comment on the child and leave both incidents open"]

  publish --> intake --> parent --> tpa
  tpa --> wire --> mr --> pr --> person --> main --> healthy
  tpa --> skip
  healthy -->|yes| close
  healthy -->|no| hold

  style person fill:#f8d7da,stroke:#b02a37,stroke-width:2px
```

## 4. A Renovate-owned application only

`postgresql` `42.3.8.rhlw-00001` affects only `report-generator-app`. Intake succeeds and stops. The Module 2 Renovate schedule is untouched.

```mermaid
flowchart TD
  publish["Publish postgresql 42.3.8.rhlw-00001"]
  nexus["Nexus CREATED webhook"]
  intake["lightwell-intake"]
  parent["Snow parent INC0023251"]
  tpa["TPA: report-generator-app only"]
  policy["policy.json: remediation_owner renovate"]
  comment["Comment: no platform applications, skip report-generator-app"]
  stop["No child incident. No RenovateJob. Run succeeds"]
  later["That repository stays on its own Renovate schedule"]

  publish --> nexus --> intake --> parent --> tpa --> policy --> comment --> stop
  stop -.-> later
```

If the rollout in scenario 1 or 3 is not healthy, `resolve-incident` still runs. It comments on the open child and does not resolve it, so the parent stays open too. A later healthy run for that application is what closes them.
