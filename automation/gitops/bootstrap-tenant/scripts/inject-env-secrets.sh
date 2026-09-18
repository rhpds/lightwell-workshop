#!/usr/bin/env bash
# Inject Lightwell Network + OpenAI secrets from .env.secrets (never commit that file).
# Usage:
#   GUID=<guid> ./automation/gitops/bootstrap-tenant/scripts/inject-env-secrets.sh
# Optional: ENV_SECRETS=... ARGO_APP=... SKIP_ARGO=1 SKIP_NEXUS_RECONCILE=1 SKIP_OPENCODE_RESTART=1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENV_FILE="${ENV_SECRETS:-${ROOT}/.env.secrets}"
GUID="${GUID:-}"

if [[ -z "${GUID}" ]]; then
  echo "ERROR: set GUID (e.g. GUID=7jtxj-1)" >&2
  exit 1
fi
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: missing ${ENV_FILE} (copy from .env.secrets.example)" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

: "${LIGHTWELL_NETWORK_USERNAME:?Set LIGHTWELL_NETWORK_USERNAME in ${ENV_FILE}}"
: "${LIGHTWELL_NETWORK_PASSWORD:?Set LIGHTWELL_NETWORK_PASSWORD in ${ENV_FILE}}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY in ${ENV_FILE}}"

NEXUS_NS="lightwell-nexus-${GUID}"
SDLC_NS="sdlc-${GUID}"
ARGO_APP="${ARGO_APP:-lightwell-tenant-${GUID}}"
ARGO_NS="${ARGO_NS:-openshift-gitops}"

echo "Injecting redhat-packages-credentials into ${NEXUS_NS}..."
oc create secret generic redhat-packages-credentials -n "${NEXUS_NS}" \
  --from-literal=username="${LIGHTWELL_NETWORK_USERNAME}" \
  --from-literal=password="${LIGHTWELL_NETWORK_PASSWORD}" \
  --dry-run=client -o yaml | oc apply -f -

echo "Injecting opencode-llm into ${SDLC_NS}..."
oc create secret generic opencode-llm -n "${SDLC_NS}" \
  --from-literal=api_key="${OPENAI_API_KEY}" \
  --dry-run=client -o yaml | oc apply -f -

if oc get deploy opencode -n "${SDLC_NS}" &>/dev/null; then
  HAS_KEY=$(oc get deploy opencode -n "${SDLC_NS}" \
    -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}{"\n"}{end}' \
    | grep -cx 'OPENAI_API_KEY' || true)
  if [[ "${HAS_KEY}" != "1" ]]; then
    echo "Wiring OPENAI_API_KEY onto opencode Deployment..."
    oc patch deploy opencode -n "${SDLC_NS}" --type=json -p='[
      {"op":"add","path":"/spec/template/spec/containers/0/env/-","value":{
        "name":"OPENAI_API_KEY",
        "valueFrom":{"secretKeyRef":{"name":"opencode-llm","key":"api_key"}}
      }}
    ]'
  else
    echo "OPENAI_API_KEY already present on opencode Deployment"
  fi
  if [[ "${SKIP_OPENCODE_RESTART:-0}" != "1" ]]; then
    oc rollout restart deploy/opencode -n "${SDLC_NS}"
  fi
fi

if [[ "${SKIP_ARGO:-0}" != "1" ]] && oc get application "${ARGO_APP}" -n "${ARGO_NS}" &>/dev/null; then
  echo "Updating Argo Application ${ARGO_APP} to use existingSecret refs..."
  TMP=$(mktemp)
  oc get application "${ARGO_APP}" -n "${ARGO_NS}" -o json > "${TMP}.in"
  python3 - "${TMP}.in" "${TMP}.out" <<'PY'
import json, re, sys
inp, outp = sys.argv[1], sys.argv[2]
with open(inp) as f:
    app = json.load(f)
vals = app["spec"]["source"].setdefault("helm", {}).get("values") or ""

# Replace only username/password under lightwellNetwork; ensure existingSecret
vals = re.sub(
    r"(?m)^([ \t]+)(?:username|password):.*\n",
    "",
    vals,
)
if "existingSecret: redhat-packages-credentials" not in vals:
    if re.search(r"(?m)^([ \t]*)lightwellNetwork:\s*$", vals):
        vals = re.sub(
            r"(?m)^([ \t]*)lightwellNetwork:\s*$",
            r"\1lightwellNetwork:\n\1  existingSecret: redhat-packages-credentials",
            vals,
            count=1,
        )
    elif re.search(r"(?m)^nexus:\s*$", vals):
        vals = re.sub(
            r"(?m)^nexus:\s*$",
            "nexus:\n  lightwellNetwork:\n    existingSecret: redhat-packages-credentials",
            vals,
            count=1,
        )
    else:
        vals += "\nnexus:\n  lightwellNetwork:\n    existingSecret: redhat-packages-credentials\n"

# Ensure sdlc.llm.existingSecret without replacing the rest of sdlc
vals = re.sub(r"(?m)^[ \t]*apiKey:.*\n?", "", vals)
if "existingSecret: opencode-llm" not in vals:
    if re.search(r"(?m)^([ \t]*)llm:\s*$", vals):
        vals = re.sub(
            r"(?m)^([ \t]*)llm:\s*$",
            r"\1llm:\n\1  existingSecret: opencode-llm",
            vals,
            count=1,
        )
    elif re.search(r"(?m)^([ \t]*)sdlc:\s*$", vals):
        vals = re.sub(
            r"(?m)^([ \t]*)sdlc:\s*$",
            r"\1sdlc:\n\1  llm:\n\1    existingSecret: opencode-llm",
            vals,
            count=1,
        )
    else:
        vals += "\nsdlc:\n  llm:\n    existingSecret: opencode-llm\n"

app["spec"]["source"]["helm"]["values"] = vals
with open(outp, "w") as f:
    json.dump(app, f)
print(vals)
PY
  oc apply -f "${TMP}.out"
  rm -f "${TMP}.in" "${TMP}.out"
fi

if [[ "${SKIP_NEXUS_RECONCILE:-0}" != "1" ]]; then
  echo "Re-running nexus-reconcile Job..."
  if oc get job nexus-reconcile -n "${NEXUS_NS}" &>/dev/null; then
    oc patch job nexus-reconcile -n "${NEXUS_NS}" --type=json \
      -p='[{"op":"remove","path":"/metadata/finalizers"}]' 2>/dev/null || true
    oc delete job nexus-reconcile -n "${NEXUS_NS}" --force --grace-period=0 --ignore-not-found
  fi
  sleep 2
  CHART="${ROOT}/automation/gitops/bootstrap-tenant"
  DOMAIN="${DEPLOYER_DOMAIN:-}"
  if [[ -z "${DOMAIN}" ]]; then
    DOMAIN="$(oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}' 2>/dev/null || true)"
  fi
  PASSWORD="${TENANT_PASSWORD:-}"
  if [[ -z "${PASSWORD}" ]]; then
    PASSWORD="$(oc get secret nexus-admin-secret -n "${NEXUS_NS}" -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)"
  fi
  if [[ -n "${DOMAIN}" ]]; then
    helm template inject "${CHART}" \
      --set "guid=${GUID}" \
      --set "username=user-${GUID}" \
      --set "password=${PASSWORD:-changeme}" \
      --set "deployer.domain=${DOMAIN}" \
      --set "nexus.lightwellNetwork.existingSecret=redhat-packages-credentials" \
      --set "sdlc.enabled=true" \
      --set "sdlc.llm.existingSecret=opencode-llm" \
      --show-only templates/nexus/reconcile-job.yaml | oc apply -f -
  else
    echo "WARN: no ingress domain; recreate nexus-reconcile via Argo sync" >&2
  fi
fi

echo "Done. Secrets applied from ${ENV_FILE} (not in git)."
