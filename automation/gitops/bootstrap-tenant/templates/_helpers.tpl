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
