Reference Architecture v7: Lightwell remediation for Spring Boot 2.x with OpenCode and Nemotron on Red Hat AI Enterprise
Nov 15, 2026 · @Someone
v7 runs v5's Lightwell remediation without IBM Bob. OpenCode, an open-source coding agent that OpenShift AI 3.5 now ships as a Technology Preview, adapts the apps on self-hosted Nemotron 3 through Models-as-a-Service. Everything that decides whether an app needs a change stays as v5 built it, and a person still merges every merge request.
Four design decisions:
• OpenCode replaces Bob in the pipeline and in Dev Spaces. One agent definition and one AGENTS.md file per repo drive both the headless run and the developer's workspace. Like v6, v7 uses Red Hat previews where they fit and assumes they reach general availability.
• Platform services replace Bob's backend. Models-as-a-Service issues keys and meters tokens, and has been generally available since OpenShift AI 3.4. NeMo Guardrails checks what goes into and comes out of the agent, including MCP tool calls. MLflow keeps a trace of each run.
• Each agent run gets its own OpenShell sandbox. Egress is denied by default, and the kernel enforces the file and syscall limits. OpenShell is a Developer Preview in OpenShift AI 3.5, with a Technology Preview planned for 3.6. Until then, the same run works in a Kata container.
• GitLab and Jira are named, as in v6. GitLab holds the code and the merge requests. Jira tracks one remediation issue per affected app.
The rest of the stack is v5's: OpenShift Platform Plus, Red Hat AI Enterprise serving Nemotron 3 Ultra, Super and Nano, IBM Vault*, Developer Hub, Pipelines, Builds and GitOps, plus the Lightwell Remediated repository behind Artifactory or Nexus, Renovate and Red Hat Trusted Profile Analyzer. No Confluent. Broadcom's commercial support for Spring Boot 2.7 still ends with 2026 (Spring), so the timing argument from v5 holds.
*Or another secrets manager the External Secrets Operator supports, such as CyberArk Conjur. Red Hat doesn't ship a secrets store of its own.
At a glance
Only the agent and the services around it change. These rows are what differs from v5.
Area
v5: IBM Bob
v7: OpenCode
Coding agent
IBM Bob, self-hosted
OpenCode, MIT-licensed, shipped in OpenShift AI 3.5 as a Technology Preview
Pipeline run
bob run --mode lightwell-remediation
opencode run --agent lightwell-remediation --format json, inside an OpenShell sandbox
Agent rules
Bob's mode limits edits to src/main/, src/test/ and REMEDIATION.md
An OpenCode agent file with the same edit limits, plus shell commands limited to the build and Git reads
Developer workspace
Bob's IDE in Dev Spaces
OpenCode in the Dev Spaces terminal or VS Code, reading the same agent file; Cline for teams that want an extension
Keys, quotas, metering
Bob's backend, in front of MaaS
MaaS directly, one subscription per consumer
Guardrails
gpt-oss-20b screens every Bob request
NeMo Guardrails checks agent inputs, outputs and MCP tool calls
Isolation
A task pod with restricted egress
An OpenShell sandbox per run: default-deny egress, Landlock, seccomp
Run record
Bob's event stream in Tekton Results
OpenCode's JSON events in Tekton Results, traces in MLflow, sandbox audit events in the SIEM
Who supports the agent
IBM
Red Hat, once the preview is generally available; the upstream project until then
Code and tracking
A Git server
GitLab merge requests and one Jira issue per affected app
Unchanged from v5: the Lightwell tiers and Renovate presets, Trusted Profile Analyzer, the backport brief, the call-site map, the old-versus-new tests and replay, the five triage classes, the human gate, the Nemotron tiers and the GPU sizing.
Why a same-API fix can still break an app
A security fix closes a hole by changing what a library accepts or returns. The method signatures stay put, so the app compiles and starts. What it gets back at runtime can differ.
Lightwell says its patches keep their scope "limited to the fix itself", and that Red Hat tests them for upstream regressions and compatibility (get started, discover). Red Hat can't test your app, though. The Lightwell support policy excludes application code, debugging, and help applying patches. For the Predisclosure tier, Red Hat tells customers to use it only with a testing pipeline that checks application behavior. v7 builds that pipeline for every tier, as v5 did.
Library in a Spring Boot 2.7 app
Upstream precedent
What changed at runtime
Where the app feels it
jackson-core, 2.13 line
Jackson 2.15 added processing limits (StreamReadConstraints)
Input over a string-length, number-length or nesting limit now throws instead of parsing
Large base64 attachments or deeply nested JSON start failing
SnakeYAML, 1.x line
CVE-2022-1471, fixed in 2.0
Global tags are blocked by default, and tagged input throws
App code that loads typed YAML with !! class tags
spring-web, 5.3 line
CVE-2024-22243, fixed in 5.3.32
Parsing of externally supplied URLs changed, so host checks see the real host
Redirect and allow-list checks built on UriComponentsBuilder, and tests that pinned the old parse
These are upstream examples, not Lightwell releases. They show the kind of difference a backport can carry. Most bumps change nothing the app can see, so the pipeline's first job is to prove that cheaply and leave people's attention for the bumps that matter.
Architecture
Lightwell builds reach every app through the artifact repository, never directly. The pipeline creates a sandbox for each agent run, and both the sandboxes and Dev Spaces reach Nemotron and the MCP servers only through the gateways.
Part
Role in v7
From
Lightwell Network
The Remediated tier serves signed .rhlw backports for the versions apps already run; the Validated tier serves rebuilt current versions
Red Hat
Artifactory or Nexus
Proxies Lightwell as lightwell-remote and layers its tiers ahead of Maven Central
JFrog or Sonatype
Renovate
Opens one bump merge request per app using Lightwell's presets
Mend, open source
GitLab and Jira
Merge requests and code owners; one remediation issue per affected app
GitLab; Atlassian
Trusted Profile Analyzer
Matches each new build to deployed SBOMs and ranks the work by severity
Red Hat
Remediation pipeline
Tests old against new, replays traffic, starts the agent, checks its output, then signs and scans
Red Hat OpenShift Pipelines and Builds
OpenCode
The coding agent: headless in a sandbox for the pipeline, interactive in Dev Spaces
Red Hat OpenShift AI, from the open-source project
OpenShell sandboxes
One isolated pod per agent run, with default-deny egress and kernel-enforced limits
Red Hat OpenShift AI, from NVIDIA's open-source project
MaaS, MCP gateway, NeMo Guardrails
Keys and quotas for the models; one endpoint for the MCP servers; checks on inputs, outputs and tool calls
Red Hat OpenShift AI and Connectivity Link
Remediation MCP server
Serves briefs, replay reports, call sites and affected-app lists
Built by the platform team
Spring Boot 2.x apps
Pinned apps on Java 8, 11 or 17
Customer code on Spring
Remediation workflow
Most merge requests take the left path straight to review: no differences, no code change. Only a difference sends the work to OpenCode, and whatever it can't make green and explained goes to the owner. Every path ends with a person merging, and the Jira issue closes only when production runs the fix.
Narrative: one fix, release to production
This is v5's scenario with OpenCode in Bob's place. The library change is modeled on CVE-2024-22243, and the counts and times are round numbers for the story.
Morning: a fix lands. Lightwell publishes spring-web 5.3.31.rhlw-00002 to its Remediated repository. A CronJob on the hub that polls Lightwell's advisory feed sees the change, the pattern Red Hat's Lightwell workshop uses (OSV polling). Artifactory proxies the build within minutes. Trusted Profile Analyzer finds 212 deployed apps on spring-web 5.3.31. Automation opens 212 Jira issues, each owned by the team Developer Hub names and due by the date the CVE's severity sets.
One brief, written once. A pipeline diffs the upstream 5.3.31 source against the Lightwell source and asks Nemotron 3 Super for a backport brief. The brief lists which methods changed, which inputs now parse differently and which new exception can surface. NeMo Guardrails checks the brief before it's stored, because it was written from library source the platform doesn't control. The remediation MCP server then serves it to every app's pipeline.
Two hundred merge requests, mostly dull. Renovate opens 212 GitLab merge requests, each carrying its Jira key. Each pipeline builds the app, runs its tests on the old and new library, and replays recorded requests against both builds. 197 apps show no difference, so their merge requests are labeled lightwell/clean and owners approve them over the next two days. The other 15 go to the agent.
One app feels it. portal-gateway checks the returnUrl after login against an allow-list. Two of its unit tests fail, and 4 of 3,000 replayed logins now return a 500 instead of a redirect. The pipeline creates an OpenShell sandbox from the OpenCode image, clones the merge request's branch into it with a read-only token, and starts opencode run with the lightwell-remediation agent.
OpenCode adapts the app, not the fix. It reads the brief, the failing tests and the replay report through the remediation MCP server. It finds the call site in ReturnUrlValidator, where the new parse throws an unhandled exception. It treats an unparseable URL as not allowed and redirects to the home page. It rewrites the two tests that asserted the old, exploitable parse, and adds tests for the four replayed cases. Its agent file denies edits outside src/main/, src/test/ and REMEDIATION.md, so pom.xml is out of reach. The sandbox's network policy lets it reach only the model gateway, the MCP gateway, Artifactory and a read-only GitLab clone.
The pipeline, not the agent, pushes. The pipeline copies the diff out of the sandbox and deletes the sandbox. NeMo Guardrails checks the diff and the notes, and the pipeline pushes them to the merge request with its own token. The rerun is green, and each difference has an explanation in the merge request and on the Jira issue.
A person decides. The code owner reads the remediation notes in GitLab, checks the four cases and approves in about fifteen minutes. The merge builds and signs a new image, Conforma checks that the fix is still the Lightwell build, and ACS scans it. Argo CD promotes it to stage that afternoon and to production after the usual approval. When production syncs, the Jira issue closes.
What changed for the teams. Without remediation automation, the same 15 apps would have found the break in their own CI, or in production. With v7, the platform reads each Lightwell build once and OpenCode does the first pass of each adaptation. The agent's whole run, from prompt to diff, stays in Tekton Results and MLflow for anyone who later asks how a line of code got there.
How the agent decides whether behavior changed
No single test proves a bump is safe, so the pipeline gathers five signals before anyone, human or agent, changes code. The first two describe the library; the last three describe this app.
Signal
Produced by
What it answers
Backport brief
Brief job, once per Lightwell build: source diff plus the CVE text, read by Super
What the fix changed: new limits, new exceptions, changed defaults, changed parsing
Call-site map
Pipeline step: jdeps and a call-graph scan, checked against the brief's changed methods
Whether this app reaches the changed code at all
Tests on the new library
The app's own suite, run as usual
Whether anything the team already asserts now fails
Replay differences
Recorded requests replayed against builds with the old and new library
Whether real inputs now get different status codes, bodies or exceptions
Risk facts
Trusted Profile Analyzer and ACS
How urgent the bump is, which sets queue order and the Jira due date, never the verdict
The pipeline sets the clean merge requests aside, and OpenCode sorts the rest. It changes code only in the middle three classes.
Class
Example
What OpenCode does
What the reviewer checks
No contact
No call sites, tests green, no replay differences
Nothing; label lightwell/clean
The report is complete; approve
Adopt the stricter behavior
The app sends input the fix now rejects, such as an oversized JSON string
Handle the new failure, return a clear 4xx, validate earlier
The new error path suits clients
App relied on the unsafe behavior
The app loads YAML with class tags the fix now blocks
Replace the reliance with an explicit, safe mapping
The new design, not just the diff
Test asserted the old behavior
A test pinned the parse an attacker could exploit
Rewrite the test to assert the safe result, citing the CVE
The test change is justified
Can't explain
Differences with no matching item in the brief
No code change; writes findings and hands over to the owner
Take over in Dev Spaces
One rule binds every class: the agent adapts the app to the fix and never weakens the fix. It can't change the dependency version, add an exclusion, catch and ignore the new exception, or reach into library internals by reflection. The agent file, the guardrail check, the AI review, Conforma and the reviewer's checklist all enforce that rule.
The agent without Bob
Bob gave v5 three things in one product: an agent loop, rules that bound it, and a backend that governed its model calls. v7 fills each from Red Hat's platform or from configuration the platform team owns. Only the remediation-specific pieces are custom code, as in v5.
What Bob did in v5
What does it in v7
Status today
Agent loop: read, edit, build, test, repeat
OpenCode 1.x, run headless with opencode run
Technology Preview in OpenShift AI 3.5
lightwell-remediation mode with edit limits
An OpenCode agent file with permission rules for edits and shell commands
Configuration
BobShell's headless runs with a JSON event stream
opencode run --format json, with --pure to load no external plugins
Upstream feature
Model gateway and keys
Models-as-a-Service, with a ci-agents subscription for the pipeline
Generally available since OpenShift AI 3.4
Guardrail model on every request
NeMo Guardrails on the brief, the replay report and the agent's diff, and on MCP tool calls at the gateway
NeMo Guardrails ships with OpenShift AI; the MCP gateway integration is a Technology Preview
Usage metering
MaaS token limits per subscription, with showback dashboards
Limits generally available; dashboards a Technology Preview
Run history
JSON events in Tekton Results; traces in MLflow
MLflow generally available since 3.4
Agent in the developer's IDE
OpenCode in Dev Spaces, reading the same agent file
Community; Red Hat Developer documents the setup
Why OpenCode. It's the coding agent Red Hat now ships. OpenShift AI 3.5 lets you "deploy and operate OpenCode" with supported container images and operator-managed deployment manifests, validated with vLLM and OGX backends and MLflow tracing (release notes). OpenShell's own quickstart runs OpenCode on a Nemotron model (OpenShell quickstart). It calls any OpenAI-compatible endpoint, so it reaches MaaS directly, and v3 already configured it for Nemotron in Dev Spaces.
What you now own. Bob's modes, guardrail and metering came configured. In v7 they are three pieces of configuration: the agent file, the MaaS subscriptions and the guardrail rails. Keep all three in the AI platform repo and review changes to them like code. IBM's Java Modernization package goes too, so the modernization path below uses Red Hat's Migration Toolkit for Applications instead.
Pinning OpenCode. OpenCode ships often: version 1.19.5 came out on November 9, 2026, and a new V2 configuration format is in beta. Use the image Red Hat ships with the preview, or mirror and scan an upstream 1.x image. Turn off auto-update in workspace images, and treat the move to V2 as a planned change.
In the developer's workspace. Red Hat Developer shows OpenCode running in a Dev Spaces workspace from its terminal or VS Code (Red Hat Developer). The devfile mounts the same opencode.json the pipeline uses, so a developer gets the MaaS models and the MCP gateway without any setup. Teams that prefer a VS Code extension can use Cline, which Red Hat has validated with Dev Spaces and OpenShift AI models (guide). Cline reads its own rules files, though, so standardize on OpenCode for remediation work.
Implementation
Repositories. As in v5. Artifactory or Nexus proxies the Lightwell Remediated tier as a Maven remote, keyed lightwell-remote in Red Hat's example. Lightwell recommends layering tiers so the most-patched build resolves first: Predisclosure, then Remediated, then Validated (get started). Nexus needs the Strict layout policy so .rhlw suffixes resolve (configure). The Lightwell service-account token lives in Vault.
Renovate. Each app extends Lightwell's java-remediated preset, which only proposes Lightwell rebuild bumps such as .rhlw-00001 to .rhlw-00002. The presets are in beta and "for testing only" (renovate-config), so pin a release tag. With GitLab, Renovate runs as a scheduled job against the GitLab API, and each merge request title carries the app's Jira key.
{
  "extends": [
    "config:recommended",
    "github>lightwell-network/renovate-config:java-remediated#v1.0.0"
  ],
  "labels": ["lightwell"],
  "prConcurrentLimit": 0,
  "packageRules": [
    {
      "matchDatasources": ["maven"],
      "registryUrls": ["https://artifactory.example.com/artifactory/lightwell-java-all"]
    }
  ],
  "hostRules": [
    { "matchHost": "artifactory.example.com", "hostType": "maven", "token": "{{ secrets.ARTIFACTORY_TOKEN }}" }
  ]
}
Spring's version management. Spring Boot's parent manages most library versions, so a bump may land as a version property or as a managed dependency. The preset's pin-transitives.mjs script lists Lightwell updates for direct and transitive dependencies. With --write, it generates a pins BOM (lightwell-pins.xml) that the app imports in dependencyManagement. Check that the pins BOM wins over the Spring Boot parent, because the effective version is what the pipeline tests.
Pipeline. Pipelines as Code starts one Tekton pipeline on every merge request labeled lightwell. Two steps differ from v5: remediate runs OpenCode in a sandbox, and a new guard-check screens the agent's output before anything is pushed.
Step
What it does
Runs on
verify-provenance
Checks each .rhlw artifact's SLSA provenance with cosign verify-blob-attestation
Pipelines
test-new, test-old
Runs the suite against the merge request and the base branch; the old run is cached per commit
Pipelines, Builds
replay
Deploys both builds to a throwaway namespace and replays recorded requests; writes a difference report
Pipelines
call-sites
Maps the brief's changed methods to the app's call sites
Pipelines
ai-review
Reviews the diff and the report with Super
Pipelines, MaaS
remediate
Only when the report shows differences: creates an OpenShell sandbox, runs OpenCode in it, copies out the diff
Pipelines, OpenShell, MaaS
guard-check
Runs NeMo Guardrails' checks on the diff and REMEDIATION.md, then pushes them with the pipeline's GitLab token
Pipelines, NeMo Guardrails
sign-scan
Builds, signs and scans the image, runs Conforma, and pushes the SBOM to Trusted Profile Analyzer
Builds, Trusted Artifact Signer, Conforma, ACS
The remediate step, as a sketch. The openshell commands follow the OpenShell 0.1 documentation; confirm them against the version OpenShift AI ships.
- name: remediate
  when:
    - input: $(tasks.replay.results.differences)
      operator: notin
      values: ["0"]
  taskSpec:
    steps:
      - name: opencode
        image: quay.example.com/platform/openshell-cli:0.1
        timeout: 60m
        script: |
          SBX=lw-$(context.pipelineRun.name)
          openshell sandbox create --name "$SBX" --detach \
            --from quay.example.com/platform/opencode-java:1.19 \
            --provider maas-ci-agents --cpu 4 --memory 8Gi
          openshell sandbox exec -n "$SBX" --no-tty -- \
            git clone --branch "$(params.mr-branch)" "$(params.repo-url)" /sandbox/app
          openshell sandbox exec -n "$SBX" --no-tty --workdir /sandbox/app -- \
            opencode run --pure --agent lightwell-remediation --format json \
              "Adapt this app to the Lightwell build in this merge request." \
            | tee /workspace/out/opencode-events.jsonl
          openshell sandbox exec -n "$SBX" --no-tty --workdir /sandbox/app -- \
            git diff > /workspace/out/agent.patch
          openshell sandbox delete "$SBX"
The maas-ci-agents provider holds the MaaS key, and OpenShell injects it at the sandbox's network boundary, so the agent never sees it. The clone uses a read-only deploy token. Until OpenShell is a Technology Preview, run the same opencode run in the step itself and set the task pod's runtime class to kata from OpenShift sandboxed containers.
The agent file. .opencode/agents/lightwell-remediation.md lives in the platform's agent image and in each repo's workspace config. Its permission rules replace Bob's mode. The last matching rule wins, so each list starts with a deny-all.
---
description: Adapts a Spring Boot 2.x app to a Lightwell build without weakening the fix
mode: primary
model: maas/nemotron-3-ultra
steps: 60
permission:
  edit:
    "*": deny
    "src/main/*": allow
    "src/test/*": allow
    "REMEDIATION.md": allow
  bash:
    "*": deny
    "./mvnw *": allow
    "mvn *": allow
    "./gradlew *": allow
    "git diff*": allow
    "git status*": allow
  task: deny
  webfetch: deny
  websearch: deny
  external_directory: deny
  doom_loop: deny
---

Read the brief, the replay report and the call sites from the remediation
MCP server before you change anything. Change code and tests only. Never
change dependency versions, add exclusions, swallow the new exception or
reach into library internals. Explain every difference in REMEDIATION.md:
its class, the change, the new tests and any residual risk. After three
test rounds without a green, explained result, stop and write what you found.
Never pass --auto in the pipeline. Every action the agent needs is allowed explicitly, so nothing waits for approval.
The OpenCode config. One opencode.json points OpenCode at MaaS and at the MCP gateway. The pipeline bakes it into the agent image, and Dev Spaces mounts it into workspaces. Context matches v3's served limit of 262,144 tokens.
{
  "$schema": "https://opencode.ai/config.json",
  "autoupdate": false,
  "share": "disabled",
  "model": "maas/nemotron-3-ultra",
  "small_model": "maas/nemotron-3-nano",
  "provider": {
    "maas": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Models-as-a-Service",
      "options": {
        "baseURL": "https://maas.apps.ai.example.com/v1",
        "apiKey": "{env:MAAS_API_KEY}"
      },
      "models": {
        "nemotron-3-ultra": { "limit": { "context": 262144, "output": 32768 } },
        "nemotron-3-nano": { "limit": { "context": 262144, "output": 16384 } }
      }
    }
  },
  "mcp": {
    "platform": {
      "type": "remote",
      "url": "https://mcp.apps.dev.example.com/mcp",
      "headers": { "Authorization": "Bearer {env:MCP_GATEWAY_TOKEN}" },
      "oauth": false
    }
  }
}
Remediation MCP server. Unchanged from v5: a small service the platform team writes, registered with the Connectivity Link MCP gateway. Its tools are get_brief, get_replay_report, get_call_sites and get_affected_apps, all read-only. With NeMo Guardrails attached to the gateway, its responses are checked for injected instructions before the agent reads them.
GitLab and Jira
GitLab holds the code and the merge requests that carry every change. Jira holds the remediation clock: one issue per affected app per Lightwell build, closed only when production runs the fix.
Touchpoint
GitLab
Jira
Hosting
GitLab self-managed on VMs, following GitLab's reference architectures. GitLab limits production use of its OpenShift operator (GitLab docs)
Jira Data Center, which Atlassian ends on March 28, 2029 (Atlassian), or Jira Cloud
Pipelines
Pipelines as Code runs on merge requests; Tekton stays the CI engine
Pipeline steps comment on the issue
Developer Hub
GitLab catalog and scaffolder plugins, a Technology Preview in Developer Hub 1.9
Jira plugin, community-supported (plugin reference)
Dev Spaces
Signs in to GitLab to clone and push
None
OpenCode in Dev Spaces
GitLab MCP server behind the MCP gateway
Jira MCP server behind the MCP gateway
OpenCode in the pipeline
A read-only clone; the pipeline pushes
None; the pipeline posts the agent's notes
Lightwell flow
Renovate opens one merge request per app with the Jira key in its title
Automation opens the issue from the Trusted Profile Analyzer match, due by severity, and closes it when production syncs
GitOps
Argo CD environment repositories
None
Predisclosure issues. A Predisclosure fix describes a vulnerability that isn't public yet. Put those issues under a restricted security level in Jira, or keep the details in GitLab and link to them from a bare issue.
Human gate and promotion
A person merges every Lightwell merge request, including the clean ones. The automation makes that merge quick and well informed; it never makes it for the owner.
Control
Setting
Who can merge
A member of the app's code owners in GitLab. Renovate and the pipeline can open and push, but never approve
Required checks
verify-provenance, test-new, replay, ai-review, sign-scan; plus guard-check and remediation-notes on adapted merge requests
Labels
lightwell/clean when nothing changed; lightwell/adapted when the agent or a person changed code; mirrored to the Jira issue
Merge request contract
Package, old and new version, CVEs, link to the brief, then one entry per difference: its class, the code change, the new tests and any residual risk
Review deadline
The Jira due date, set from the CVE's severity in Trusted Profile Analyzer; Developer Hub shows each owner's open Lightwell merge requests
Policy
Conforma fails the build if the effective version of a patched library isn't the .rhlw build
Promotion
Image Updater opens the environment merge request, stage syncs on merge, production needs its own approval
Rollback
Argo CD returns to the previous image, and the Jira issue reopens
Clean doesn't mean unreviewed. A clean merge request shows the owner a one-screen report: no call sites, tests green, zero replay differences, and the brief's summary. Approving it should take a minute. Policy can require two approvers for critical apps.
When the agent is stuck. After three test rounds without a green, explained result, the run stops and writes what it found. The pipeline exports the OpenCode session with opencode export and attaches it to the merge request, which is assigned to the owner, and the Jira issue goes back to Open. The owner opens the workspace from Developer Hub, imports the session with opencode import, and picks up where the agent stopped, with the same brief and reports from the MCP server.
AI platform and model routing
The models and serving stack are v5's, on llm-d. What changes is who calls them: OpenCode and the pipeline reach MaaS directly, each with its own subscription, instead of through Bob's gateway.
MaaS model
v7 work
Subscription
nemotron-3-ultra
OpenCode's main model, for every pipeline run and for developers in Dev Spaces
ci-agents for the pipeline; engineering-agents for people, as in v3
nemotron-3-super
Backport briefs, AI review on every Lightwell merge request, Developer Hub Lightspeed
lightwell-pipeline
nemotron-3-nano
OpenCode's small model: session titles, summaries, quick sub-steps
ci-agents and engineering-agents
gpt-oss-20b
The model behind NeMo Guardrails' self-checks on the brief, the replay report and the agent's output
guardrails
Why Super writes the briefs. A brief is a reading task over one source diff and one advisory. It runs once per Lightwell build and every app reuses it, so Super handles it at a fraction of Ultra's cost.
Why Ultra does the adapting. Adapting an app means multi-step coding with builds and tests in the loop, which is the work v3 and v4 sized Ultra for.
Priority. v5 had to ask whether Bob's gateway marked pipeline traffic. In v7 the pipeline and people arrive with different MaaS keys, so the traffic is already separable. Priority-based flow control in llm-d is generally available in OpenShift AI 3.5 (release notes); confirm how it maps to MaaS subscriptions so the pipeline ranks below people.
Tool calls. OpenCode depends on tool calling. In OpenShift AI 3.5, llm-d passes tool definitions and tool-call responses through unchanged, a Technology Preview. Nemotron 3 uses the qwen3_coder tool-call format, and the Ultra model card asks coding agents to send force_nonempty_content: true in chat_template_kwargs. Confirm OpenCode can send that through the OpenAI-compatible provider, as v3 flagged.
Guardrails, placed where they work. NeMo Guardrails' chat endpoint isn't a transparent proxy, and Red Hat's docs recommend calling the model directly for tool calling and using the separate guardrail checks endpoint instead. So v7 doesn't put guardrails between OpenCode and Ultra. It checks the inputs before the agent sees them, the tool calls at the MCP gateway, and the output before it's pushed (NeMo Guardrails docs).
Sizing the AI tier to patch volume
The GPU math is v5's, because the work and the model are the same. A planning estate of 400 apps produces about 120 agent runs a month, and the worst wave day needs 20 concurrent Ultra sessions, under half of one replica. What v7 adds is CPU and memory for the sandboxes, and what it drops is an agent license.
Planning inputs. Replace these with pilot measurements.
Input
Planning value
Basis
Spring Boot 2.x apps
400
Example estate
Lightwell builds that touch the estate
10 a month
Assumption; count them in Artifactory
Apps affected per build
30%
Assumption; Trusted Profile Analyzer reports the real share
Merge requests that need the agent
10%
The narrative's 15 of 212 is 7%; 10% adds margin
Ultra tokens per agent run
2.4 million in, 40,000 out
v5's Bob estimate; OpenCode's real use is a pilot measure
Wall time per agent run
45 minutes
Includes builds and tests inside the agent's loop
Pipeline time per merge request
25 minutes
Two test runs, replay and signing
Cap on concurrent agent runs
20
Set in the pipeline to protect interactive users
Sandbox size
4 vCPU, 8 GiB
Assumption: enough for a Maven build and tests
Results.
Measure
Steady month
Wave day: one build hits all 400 apps, 25% need the agent
Lightwell merge requests
1,200
400
Agent runs
120
100
Ultra tokens
288 million in, 4.8 million out
240 million in, 4 million out
Concurrent Ultra sessions
Under one on average
20, the cap: about 43% of one replica
Time to clear the agent queue
Continuous
About 3.75 hours
Super tokens for briefs and reviews
About 40 million
About 13 million
Pipeline hours
500
167, or about 8.3 hours at 20 parallel pipelines
Sandbox capacity at the cap
Rarely used
80 vCPU and 160 GiB for about 3.75 hours
What it means:
• GPUs. No change from v5. v4 sized Ultra at 4 replicas for a 100-session interactive peak, and the 20-session cap fits in that headroom. A remediation-only deployment still needs one Ultra replica on 4 B200s, plus Super and gpt-oss-20b. gpt-oss-20b now runs a few checks per merge request rather than screening every agent request, so it has room to spare.
• MaaS. Give ci-agents a daily token ceiling of about 250 million to cover wave days, and lightwell-pipeline about 50 million tokens a month.
• CI and sandboxes. Plan about 160 vCPU for 20 parallel pipelines at 8 vCPU each, plus 80 vCPU and 160 GiB for 20 sandboxes. More parallelism clears waves faster; more GPUs don't.
• Licenses. The agent has no per-seat or per-run license. Its cost is the OpenShift AI subscription and the GPUs v4 already sized.
Optional modernization path
Lightwell lets an app stay on Spring Boot 2.7 safely, but 2.7 isn't a destination. The pipeline that compares old and new behavior for a Lightwell bump also guards an upgrade, so apps can move off 2.7 on their own schedule. Without Bob's Java Modernization package, the tools are Red Hat's Migration Toolkit for Applications (MTA) and OpenCode.
Path
Fits
Lightwell tier
Tools
Stay on 2.7
Stable apps that rarely change
Remediated
This pipeline
Java first
Apps on Java 8 or 11 that can move to Java 17 and keep Spring Boot 2.7
Remediated
MTA analysis and Red Hat Developer Lightspeed for MTA for the code changes; replay compares behavior
Current Spring Boot
Apps still in active development
Validated, with Lightwell's java-upgrade preset, which allows upstream version jumps
An OpenCode upgrade agent, written like the remediation agent with wider edit rights; replay compares behavior
Quarkus
Apps that should join the Quarkus estate
Validated
MTA's Spring Boot to Quarkus rules and Developer Lightspeed for MTA
How to choose. Sort apps in Developer Hub by change rate and by Lightwell merge request volume. Apps that take many Lightwell merge requests and still ship features gain the most from moving. Apps that rarely change can stay on Remediated.
One check before you rely on the tools. Developer Lightspeed for MTA comes with Red Hat Advanced Developer Suite and works with a public or self-hosted model of your choice. Confirm it can use the MaaS endpoint, and whether its IDE extension runs in Dev Spaces.
Pilot plan and metrics
Prove it in 10 weeks on one portfolio: 20 to 30 Spring Boot 2.7 apps, 3 to 5 owning teams, working test suites and a staging environment. The agent runs in shadow before it touches a real merge request.
Each gate needs evidence from the phase before it. Failing Gate 2 means fixing the tests and replay, not giving the agent more room.
What the first two weeks set up. Beyond v5's Lightwell, Renovate and Trusted Profile Analyzer work: the OpenCode image and agent file, the MaaS subscriptions, the OpenShell gateway and its network policy, NeMo Guardrails with its rails, the MCP gateway registrations, and the GitLab and Jira automation.
Seeded changes. Lightwell bumps that break something are rare, so the pilot can't wait for them. Build private copies of pilot libraries that carry known upstream behavior changes, such as those in the problem table, and feed them through the same pipeline. They show whether the tests and replay catch a difference before anyone relies on a clean label.
An agent-settings bake-off. The GPUs are a fixed cost, so the Shadow phase tunes for acceptance and wall time rather than price. Run the same seeded changes with Ultra's thinking fully on and at reduced effort, and with step caps of 40 and 60. Keep the settings with the best first-pass acceptance that still clears a wave inside a working day.
What to measure. Take the same measures for the last three months of manual dependency fixes, where the history exists, as a baseline.
Metric
How it's measured
Proposed target
Time to merge, clean
Lightwell publish to merge, from Artifactory and GitLab timestamps
Median under 2 business days
Time to merge, adapted
Same
Median under 5 business days
Time to production
Lightwell publish to Jira issue Done, meaning production runs the fix
Report; set a target after the pilot
Coverage
Affected apps in Trusted Profile Analyzer with a Jira issue and a merge request within 1 business day
100%
Seeded-change detection
Seeded changes flagged before merge
90% or more
False clean
Merge requests labeled clean that later show a difference
Zero
Agent first-pass acceptance
Adapted merge requests merged with no human code commits
50% or more
Reviewer time
First review to approval, from the merge request timeline
Clean under 5 minutes; adapted under 30 minutes
Sandbox denials
Connections the sandbox policy blocked that the agent needed
Zero after week 4
Escaped regressions
Incidents traced to a Lightwell bump within 30 days
Zero
Cost per adapted app
Ultra tokens, sandbox minutes and pipeline minutes per adapted merge request
Report; it replaces the sizing assumptions
Security and governance
v5's controls still apply. Without Bob, the controls that came with the agent now come from the platform, and the sandbox adds a layer v5 didn't have.
Risk
Control
A tampered or substituted package
Lightwell repositories are SLSA Level 3 with signed provenance. verify-provenance checks every .rhlw artifact with cosign before tests run. Artifactory serves .rhlw versions only from lightwell-remote
The agent weakens the fix
The agent file denies edits to pom.xml and every build file. Conforma fails the build if the effective version isn't the .rhlw build. The AI review and the reviewer checklist look for swallowed exceptions, disabled checks and reflection into library internals
Prompt injection through library source or app data
The brief job runs with no tools and no write access. NeMo Guardrails checks the brief and the replay report before the agent reads them, and checks MCP tool calls at the gateway
The agent reaching beyond its job
Each run gets an OpenShell sandbox: no outbound access except MaaS, the MCP gateway, Artifactory and a read-only GitLab clone; Landlock limits writes to /sandbox and /tmp; seccomp filters syscalls (Red Hat blog). Kata containers until OpenShell is a Technology Preview
Credentials in the agent's reach
The sandbox holds no write token and no model key. OpenShell injects the MaaS key at the boundary, and the pipeline, not the agent, pushes to GitLab
The agent's own supply chain
OpenCode comes from Red Hat's preview image, or an upstream 1.x image that is mirrored and scanned. --pure loads no external plugins, auto-update is off, and sharing is disabled in opencode.json
Code leaving the company
Every model runs on the AI cluster, and the sandbox can't reach the internet
Predisclosure fixes leaking
Briefs and merge requests describe vulnerabilities that aren't public yet. Keep those repositories and reports internal, limit who can see them, and restrict the Jira issues
Credentials at rest
The Lightwell token, Renovate's GitLab and Artifactory tokens, MaaS keys and the Jira token live in Vault and reach pods through the Vault Secrets Operator
Audit trail. Each Lightwell change leaves a complete record. The merge request holds the brief, the replay report, the agent's notes, the guardrail result, the AI review and the approval. Tekton Results keeps OpenCode's JSON events, MLflow keeps the run's trace, and OpenShell sends every allowed and denied connection to the SIEM as OCSF events. The image carries its signature and provenance, Trusted Profile Analyzer shows the fixed version running, and the Jira issue records when it reached production.
Readiness and assumptions
The Lightwell side and Models-as-a-Service are generally available. The agent, its sandbox and the MCP pieces are previews today, which v7 assumes reach general availability. The custom work is v5's three components.
Item
Status
Note
Lightwell Network, Remediated and Validated tiers
GA
Commercial launch July 8, 2026 (press release)
Lightwell Renovate presets
Beta
"For testing only and not yet officially supported"
Lightwell source for each .rhlw build
To confirm
Confirm a per-artifact sources jar for the brief job
Trusted Profile Analyzer
GA
Part of Red Hat Advanced Developer Suite
Models-as-a-Service
GA
Since OpenShift AI 3.4 (Red Hat blog)
OpenCode on OpenShift AI
Tech Preview
OpenShift AI 3.5; v7 assumes general availability
OpenShell agent sandboxes
Developer Preview
OpenShift AI 3.5; Technology Preview planned for 3.6; Kata containers until then
Connectivity Link MCP gateway
Tech Preview
As in v5
NeMo Guardrails on MCP tool calls
Tech Preview
OpenShift AI 3.5
Tool-call passthrough in llm-d
Tech Preview
OpenShift AI 3.5
Priority-based flow control in llm-d
GA
OpenShift AI 3.5; confirm how it maps to MaaS subscriptions
MLflow
GA
Managed component since OpenShift AI 3.4; OpenCode tracing is part of the OpenCode preview
OpenCode in Dev Spaces
Community
Documented by Red Hat Developer; not on Dev Spaces' validated list
OpenCode V2 configuration format
Beta
Pin 1.x; 1.19.5 released November 9, 2026
Developer Hub GitLab plugins
Tech Preview
Developer Hub 1.9; the Jira plugin is community-supported
Tekton driving OpenShell sandboxes
To confirm
The sketch follows OpenShell 0.1 docs
OpenShell key injection for MaaS
To confirm
A provider profile for an OpenAI-compatible endpoint inside the cluster
force_nonempty_content from OpenCode
To confirm
The Ultra model card asks coding agents to send it
Developer Lightspeed for MTA on MaaS
To confirm
Supports a self-hosted model of your choice
Backport brief job
Build it
A Tekton task and a prompt; stores briefs in Git
Replay harness
Build it
Needs recorded requests per app, such as captured staging traffic or contract tests
Remediation MCP server
Build it
Four read-only tools over briefs, reports and Trusted Profile Analyzer
Sources
• Reference Architecture v5, the design v7 builds on, and v3, for the Nemotron tiers and OpenCode in Dev Spaces
• OpenShift AI 3.5: Technology Preview features: OpenCode, MCP gateway, NeMo Guardrails with the MCP gateway, llm-d tool calling
• OpenShift AI 3.5: Developer Preview features: OpenShell sandboxing
• OpenShift AI 3.5: new features and enhancements: llm-d priority-based flow control
• Beyond container boundaries: kernel-level agent security in OpenShift AI 3.5 (Red Hat, September 2026)
• Red Hat AI and OpenShell (Red Hat, May 2026)
• OpenShell sandboxes and quickstart (NVIDIA)
• OpenShell donated to the CNCF (November 9, 2026)
• Delivering Models-as-a-Service with OpenShift AI 3.4 (Red Hat, May 2026)
• Enabling AI safety with NeMo Guardrails (OpenShift AI 3.5)
• OpenCode docs: CLI, agents, permissions, providers, MCP servers
• OpenCode in OpenShift Dev Spaces (Red Hat Developer, April 2026)
• A guide to AI code assistants in Dev Spaces (Red Hat Developer, January 2026)
• Lightwell Network: Get started (PDF), Discover (PDF), Configure (PDF)
• Lightwell support policy
• lightwell-network/renovate-config
• Lightwell OSV manifest polling (Red Hat workshop)
• IBM and Red Hat expand Lightwell (press release, July 2026)
• Spring Boot 2.7 support period extended (Spring)
• Jackson 2.15 release notes, CVE-2022-1471 and SnakeYAML 2.0 (Veracode), CVE-2024-22243 (Spring)
• Red Hat Developer Lightspeed for MTA
• GitLab Operator, Atlassian Data Center end of life, Developer Hub dynamic plugins reference
