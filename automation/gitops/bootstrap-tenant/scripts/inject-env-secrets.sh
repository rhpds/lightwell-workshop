#!/usr/bin/env bash
# Inject Lightwell Network and/or OpenAI secrets from .env.secrets (never commit that file).
#
# The two credential sets are independent — supply either or both:
#   LIGHTWELL_NETWORK_USERNAME + LIGHTWELL_NETWORK_PASSWORD
#       -> Secret redhat-packages-credentials; re-runs nexus-reconcile so the
#          authenticated proxy repos and EDA webhooks get created.
#   OPENAI_API_KEY
#       -> Secret opencode-llm; wires OPENAI_API_KEY onto the opencode Deployment.
# Supplying neither is an error. Whichever half you supply is also pinned into
# the Argo Application as an existingSecret ref so the next sync cannot revert it.
#
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

# The two credential sets are independent: inject whichever ${ENV_FILE}
# actually supplies. Lightwell Network unlocks the Nexus proxy repos and the
# EDA webhook; OPENAI_API_KEY unlocks OpenCode agent remediation.
HAVE_LW=0
HAVE_LLM=0

if [[ -n "${LIGHTWELL_NETWORK_USERNAME:-}" && -n "${LIGHTWELL_NETWORK_PASSWORD:-}" ]]; then
  HAVE_LW=1
elif [[ -n "${LIGHTWELL_NETWORK_USERNAME:-}" || -n "${LIGHTWELL_NETWORK_PASSWORD:-}" ]]; then
  echo "ERROR: set both LIGHTWELL_NETWORK_USERNAME and LIGHTWELL_NETWORK_PASSWORD in ${ENV_FILE}, or neither" >&2
  exit 1
fi

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  HAVE_LLM=1
fi

if (( HAVE_LW == 0 && HAVE_LLM == 0 )); then
  echo "ERROR: ${ENV_FILE} supplies neither LIGHTWELL_NETWORK_USERNAME/PASSWORD nor OPENAI_API_KEY — nothing to inject" >&2
  exit 1
fi

echo "Injecting: lightwell=$([[ ${HAVE_LW} == 1 ]] && echo yes || echo no) llm=$([[ ${HAVE_LLM} == 1 ]] && echo yes || echo no)"

NEXUS_NS="lightwell-nexus-${GUID}"
SDLC_NS="sdlc-${GUID}"
ARGO_APP="${ARGO_APP:-lightwell-tenant-${GUID}}"
ARGO_NS="${ARGO_NS:-openshift-gitops}"

if [[ "${HAVE_LW}" == "1" ]]; then
  echo "Injecting redhat-packages-credentials into ${NEXUS_NS}..."
  oc create secret generic redhat-packages-credentials -n "${NEXUS_NS}" \
    --from-literal=username="${LIGHTWELL_NETWORK_USERNAME}" \
    --from-literal=password="${LIGHTWELL_NETWORK_PASSWORD}" \
    --dry-run=client -o yaml | oc apply -f -
fi

if [[ "${HAVE_LLM}" == "1" ]]; then
  echo "Injecting opencode-llm into ${SDLC_NS}..."
  oc create secret generic opencode-llm -n "${SDLC_NS}" \
    --from-literal=api_key="${OPENAI_API_KEY}" \
    --dry-run=client -o yaml | oc apply -f -
fi

if [[ "${HAVE_LLM}" == "1" ]] && oc get deploy opencode -n "${SDLC_NS}" &>/dev/null; then
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
  HAVE_LW="${HAVE_LW}" HAVE_LLM="${HAVE_LLM}" python3 - "${TMP}.in" "${TMP}.out" <<'PY'
import json, os, re, sys
inp, outp = sys.argv[1], sys.argv[2]
# Only rewrite the half we actually injected a Secret for. Adding an
# existingSecret ref for a Secret that does not exist would make the chart stop
# rendering it while nothing supplies it.
do_nexus = os.environ.get("HAVE_LW") == "1"
do_llm = os.environ.get("HAVE_LLM") == "1"
with open(inp) as f:
    app = json.load(f)
vals = app["spec"]["source"].setdefault("helm", {}).get("values") or ""

if do_nexus:
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

if do_llm:
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
# Never print vals: the Application's helm values carry the tenant password and
# the LiteLLM virtual key, and this script's output routinely ends up pasted
# into tickets and chat. Show only the keys we rewrote.
print("  helm values updated:", ", ".join(
    k for k, on in (("nexus.lightwellNetwork.existingSecret", do_nexus),
                    ("sdlc.llm.existingSecret", do_llm)) if on))
PY
  oc apply -f "${TMP}.out"
  rm -f "${TMP}.in" "${TMP}.out"
fi

# Only worth re-running when Lightwell credentials just landed — that is what
# lets reconcile create the authenticated proxy repos it previously skipped.
if [[ "${HAVE_LW}" == "1" && "${SKIP_NEXUS_RECONCILE:-0}" != "1" ]]; then
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
    HELM_ARGS=(
      --set "guid=${GUID}"
      --set "username=user-${GUID}"
      --set "password=${PASSWORD:-changeme}"
      --set "deployer.domain=${DOMAIN}"
      --set "nexus.lightwellNetwork.existingSecret=redhat-packages-credentials"
      --set "sdlc.enabled=true"
    )
    if [[ "${HAVE_LLM}" == "1" ]]; then
      HELM_ARGS+=(--set "sdlc.llm.existingSecret=opencode-llm")
    fi
    helm template inject "${CHART}" "${HELM_ARGS[@]}" \
      --show-only templates/nexus/reconcile-job.yaml | oc apply -f -
  else
    echo "WARN: no ingress domain; recreate nexus-reconcile via Argo sync" >&2
  fi
fi

echo "Done. Secrets applied from ${ENV_FILE} (not in git)."
