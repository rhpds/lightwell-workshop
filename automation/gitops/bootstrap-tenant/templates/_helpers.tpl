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
{{- if .Values.sdlc.rulebookName -}}
{{- .Values.sdlc.rulebookName -}}
{{- else if .Values.sdlc.ao.baseUrl -}}
sdlc-remediation.yml
{{- else -}}
sdlc-remediation-legacy.yml
{{- end -}}
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
