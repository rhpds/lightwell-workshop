{{- define "bootstrap-tenant.nexusNamespace" -}}
{{- printf "lightwell-nexus-%s" .Values.guid -}}
{{- end -}}

{{- define "bootstrap-tenant.jobNamespace" -}}
{{- printf "lightwell-tenant-%s" .Values.guid -}}
{{- end -}}

{{- define "bootstrap-tenant.aapOrg" -}}
{{- .Values.aap.org | default (printf "user-%s" .Values.guid) -}}
{{- end -}}

{{- define "bootstrap-tenant.gitlabHost" -}}
{{- printf "https://gitlab-%s.%s" .Values.gitlab.namespace .Values.deployer.domain -}}
{{- end -}}

{{- define "bootstrap-tenant.keycloakUrl" -}}
{{- .Values.keycloak.url | default (printf "https://sso.%s" .Values.deployer.domain) -}}
{{- end -}}

{{- define "bootstrap-tenant.tpaUrl" -}}
{{- .Values.tpa.url | default (printf "https://server-%s.%s" (.Values.tpa.namespace | default "lightwell-tpa") .Values.deployer.domain) -}}
{{- end -}}

{{- define "bootstrap-tenant.demoProjectPath" -}}
{{- .Values.gitlab.demoProjectPath | default (printf "%s/lw-demo-help-app-%s" .Values.gitlab.group .Values.guid) -}}
{{- end -}}

{{- define "bootstrap-tenant.tpaSbomLabel" -}}
{{- .Values.tpa.sbomLabel | default (printf "sdlc-demo-%s" .Values.guid) -}}
{{- end -}}

{{- define "bootstrap-tenant.nexusRepoValidated" -}}
{{- .Values.nexus.repoValidated | default (printf "redhat-packages-validated-%s" .Values.guid) -}}
{{- end -}}

{{- define "bootstrap-tenant.nexusRepoRemediated" -}}
{{- .Values.nexus.repoRemediated | default (printf "redhat-packages-remediated-%s" .Values.guid) -}}
{{- end -}}

{{- define "bootstrap-tenant.edaProjectName" -}}
{{- .Values.sdlc.projectName | default (printf "SDLC %s" .Values.guid) -}}
{{- end -}}

{{- define "bootstrap-tenant.edaActivationName" -}}
{{- .Values.sdlc.activationName | default (printf "sdlc-remediation-%s" .Values.guid) -}}
{{- end -}}

{{- define "bootstrap-tenant.nexusRouteUrl" -}}
{{- printf "https://nexus-%s.%s" (include "bootstrap-tenant.nexusNamespace" .) .Values.deployer.domain -}}
{{- end -}}

{{- define "bootstrap-tenant.sdlcNamespace" -}}
{{- .Values.sdlc.namespace | default (printf "sdlc-%s" .Values.guid) -}}
{{- end -}}

{{- define "bootstrap-tenant.aapControllerUrl" -}}
{{- .Values.aap.controllerUrl | default (printf "https://aap-%s.%s" .Values.aap.namespace .Values.deployer.domain) -}}
{{- end -}}

{{- define "bootstrap-tenant.edaWebhookUrl" -}}
{{- if .Values.sdlc.edaWebhookUrl -}}
{{- .Values.sdlc.edaWebhookUrl -}}
{{- else -}}
{{- printf "http://%s.%s.svc.cluster.local:5000/" (include "bootstrap-tenant.edaActivationName" .) .Values.aap.namespace -}}
{{- end -}}
{{- end -}}

{{- define "bootstrap-tenant.edaWebhookRouteUrl" -}}
{{- if .Values.sdlc.edaWebhookRouteUrl -}}
{{- .Values.sdlc.edaWebhookRouteUrl -}}
{{- else -}}
{{- printf "https://%s-%s.%s/" (include "bootstrap-tenant.edaActivationName" .) .Values.aap.namespace .Values.deployer.domain -}}
{{- end -}}
{{- end -}}

{{- define "bootstrap-tenant.gitlabWebhookTargetUrl" -}}
{{- .Values.sdlc.gitlabWebhookTargetUrl | default (include "bootstrap-tenant.edaWebhookRouteUrl" .) -}}
{{- end -}}

{{- define "bootstrap-tenant.opencodeBaseUrl" -}}
{{- if .Values.sdlc.opencodeBaseUrl -}}
{{- .Values.sdlc.opencodeBaseUrl -}}
{{- else -}}
{{- printf "http://opencode.%s.svc.cluster.local:4096" (include "bootstrap-tenant.sdlcNamespace" .) -}}
{{- end -}}
{{- end -}}

{{- define "bootstrap-tenant.opencodeServerPassword" -}}
{{- .Values.sdlc.opencodeServerPassword | default .Values.password -}}
{{- end -}}

{{- /*
  Build sandbox for the MR verifier. Per-tenant: the agent writes this
  tenant's GitLab PAT into it as Secret gitlab-pat, and keys verify-Job
  idempotency on mr-iid -- which restarts at 1 per project. A cluster-wide
  namespace therefore leaks credentials between tenants and lets one
  tenant's lookup find (and delete) another's Job.
*/ -}}
{{- define "bootstrap-tenant.sandboxNamespace" -}}
{{- printf "sdlc-sandboxes-%s" .Values.guid -}}
{{- end -}}

{{- /*
  Prefix for the ephemeral per-MR test namespaces. Same collision reason:
  two tenants both verifying !1 would otherwise both want pr-test-mr-1.
*/ -}}
{{- define "bootstrap-tenant.ephemeralNsPrefix" -}}
{{- printf "pr-test-mr-%s" .Values.guid -}}
{{- end -}}

{{/*
Rulebook for the EDA activation.

sdlc-remediation.yml makes EDA a sensor and hands the flow to the Automation
Orchestrator; its first job template POSTs to the AO webhook and asserts on
ao_base_url/ao_client_id/ao_client_secret/ao_webhook_path. With no AO reachable
that assert fails on the first Nexus event, so the tenant looks healthy and
remediation never runs. Default to the legacy rulebook unless AO is configured.
*/}}
{{- define "bootstrap-tenant.rulebookName" -}}
{{- include "bootstrap-tenant.edaRulebookName" . -}}
{{- end -}}

{{- define "bootstrap-tenant.snowNamespace" -}}
{{- printf "snow-%s" .Values.guid -}}
{{- end -}}

{{- define "bootstrap-tenant.lightwellNetworkSecretName" -}}
{{- .Values.nexus.lightwellNetwork.existingSecret | default "redhat-packages-credentials" -}}
{{- end -}}

{{- define "bootstrap-tenant.opencodeLlmSecretName" -}}
{{- .Values.sdlc.llm.existingSecret | default "opencode-llm" -}}
{{- end -}}

{{- define "bootstrap-tenant.orchestratorEnabled" -}}
{{- if hasKey (.Values.sdlc.orchestrator | default dict) "enabled" -}}
{{- .Values.sdlc.orchestrator.enabled -}}
{{- else -}}
{{- false -}}
{{- end -}}
{{- end -}}

{{- define "bootstrap-tenant.edaRulebookName" -}}
{{- if .Values.sdlc.rulebookName -}}
{{- .Values.sdlc.rulebookName -}}
{{- else if eq (include "bootstrap-tenant.orchestratorEnabled" . | toString) "true" -}}
{{- "sdlc-remediation.yml" -}}
{{- else -}}
{{- "sdlc-remediation-legacy.yml" -}}
{{- end -}}
{{- end -}}

{{- define "bootstrap-tenant.aoSecretName" -}}
{{- .Values.sdlc.orchestrator.existingSecret | default "automation-orchestrator" -}}
{{- end -}}

{{- /* Default AO URL from deployer.domain — same convention as infra Route ao.<domain>. */ -}}
{{- define "bootstrap-tenant.aoBaseUrl" -}}
{{- if and .Values.sdlc.orchestrator .Values.sdlc.orchestrator.baseUrl -}}
{{- .Values.sdlc.orchestrator.baseUrl -}}
{{- else -}}
{{- printf "https://ao.%s" .Values.deployer.domain -}}
{{- end -}}
{{- end -}}

{{- define "bootstrap-tenant.aoProjectName" -}}
{{- if and .Values.sdlc.orchestrator .Values.sdlc.orchestrator.projectName -}}
{{- .Values.sdlc.orchestrator.projectName -}}
{{- else -}}
{{- printf "lightwell-%s" .Values.guid -}}
{{- end -}}
{{- end -}}

{{- /* Guid-scoped webhook paths so tenants cannot fire each other's AO triggers. */ -}}
{{- define "bootstrap-tenant.aoStartWebhookPath" -}}
{{- if and .Values.sdlc.orchestrator .Values.sdlc.orchestrator.startWebhookPath -}}
{{- .Values.sdlc.orchestrator.startWebhookPath -}}
{{- else -}}
{{- printf "lightwell-remediation-start-%s" .Values.guid -}}
{{- end -}}
{{- end -}}

{{- define "bootstrap-tenant.aoResumeWebhookPath" -}}
{{- if and .Values.sdlc.orchestrator .Values.sdlc.orchestrator.resumeWebhookPath -}}
{{- .Values.sdlc.orchestrator.resumeWebhookPath -}}
{{- else -}}
{{- printf "lightwell-remediation-resume-%s" .Values.guid -}}
{{- end -}}
{{- end -}}

{{- /*
  OpenCode image pull ref.
  - sdlc.opencodeImage set → use as-is (external registry override).
  - empty → shared ImageStream in the OpenShift integrated registry
    (bootstrap-infra BuildConfig → lightwell-images/sdlc-opencode):
    image-registry.openshift-image-registry.svc:5000/<ns>/<name>:<tag>
*/ -}}
{{- define "bootstrap-tenant.opencodeImage" -}}
{{- if .Values.sdlc.opencodeImage -}}
{{- .Values.sdlc.opencodeImage -}}
{{- else -}}
{{- $ns := .Values.sdlc.opencodeImageNamespace | default "lightwell-images" -}}
{{- $name := .Values.sdlc.opencodeImageName | default "sdlc-opencode" -}}
{{- $tag := .Values.sdlc.opencodeImageTag | default "sha-5e19550" -}}
{{- printf "image-registry.openshift-image-registry.svc:5000/%s/%s:%s" $ns $name $tag -}}
{{- end -}}
{{- end -}}
