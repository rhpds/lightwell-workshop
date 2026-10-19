#!/usr/bin/env bash
# POST a CI/CD lifecycle event to the tenant EDA route. EDA starts a short AO
# lifecycle execution (build/deploy eda_trigger) — not Approval PATCH, not Nexus Start.
#
# Usage:
#   ./trigger-cicd-signal.sh <guid> build  {succeeded|failed} <gitlab_path>
#   ./trigger-cicd-signal.sh <guid> deploy {healthy|degraded}  <gitlab_path>
#
# Examples:
#   ./trigger-cicd-signal.sh cng2l build  succeeded acme-cng2l/wire-transfer-svc
#   ./trigger-cicd-signal.sh cng2l deploy healthy   acme-cng2l/wire-transfer-svc
set -euo pipefail

GUID="${1:-}"
KIND="${2:-}"
RESULT="${3:-}"
GITLAB_PATH="${4:-}"

usage() {
  echo "Usage: $0 <guid> {build|deploy} {succeeded|failed|healthy|degraded} <gitlab_path>" >&2
  exit 2
}

[[ -n "${GUID}" && -n "${KIND}" && -n "${RESULT}" && -n "${GITLAB_PATH}" ]] || usage

AAP_NS="${AAP_NS:-aap}"
EDA_HOST="$(oc get route "sdlc-remediation-${GUID}" -n "${AAP_NS}" -o jsonpath='{.spec.host}' 2>/dev/null || true)"
if [[ -z "${EDA_HOST}" ]]; then
  echo "ERROR: route sdlc-remediation-${GUID} not found in ${AAP_NS}" >&2
  exit 1
fi
EDA_URL="https://${EDA_HOST}/"

case "${KIND}/${RESULT}" in
  build/succeeded|build/failed)
    STATUS="$( [[ "${RESULT}" == succeeded ]] && echo Succeeded || echo Failed )"
    BODY=$(cat <<EOF
{"type":"pipelinerun_terminal","guid":"${GUID}","gitlab_path":"${GITLAB_PATH}","status":"${STATUS}"}
EOF
)
    ;;
  deploy/healthy)
    BODY=$(cat <<EOF
{"type":"argo_app_health","guid":"${GUID}","gitlab_path":"${GITLAB_PATH}","sync":"Synced","health":"Healthy"}
EOF
)
    ;;
  deploy/degraded)
    BODY=$(cat <<EOF
{"type":"argo_app_health","guid":"${GUID}","gitlab_path":"${GITLAB_PATH}","sync":"Synced","health":"Degraded"}
EOF
)
    ;;
  *)
    usage
    ;;
esac

echo "POST ${EDA_URL}"
echo " ${BODY}"
curl -sk -X POST "${EDA_URL}" \
  -H 'Content-Type: application/json' \
  -d "${BODY}" \
  -w "\nHTTP %{http_code}\n"
