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
{{- .Values.tpa.url | default (printf "https://trustify.%s" .Values.deployer.domain) -}}
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
