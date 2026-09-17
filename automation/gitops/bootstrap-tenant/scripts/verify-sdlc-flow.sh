#!/usr/bin/env bash
# Verify SDLC event flow (OpenCode, EDA activation, webhooks, Controller JTs).
# Optional smoke POSTs and cleanup of verify-side effects.
#
# Usage:
#   ./verify-sdlc-flow.sh <guid>              # static checks
#   ./verify-sdlc-flow.sh <guid> --smoke      # + HTTP ping (no Controller jobs)
#   ./verify-sdlc-flow.sh <guid> --smoke --smoke-rules  # + rule payloads (launches JTs)
#   ./verify-sdlc-flow.sh <guid> --cleanup    # remove artifacts from last --smoke-rules
#
# Requires: oc, curl, python3; logged into cluster with AAP + GitLab access.
set -euo pipefail

GUID="${1:-}"
shift || true
SMOKE=false
SMOKE_RULES=false
CLEANUP=false
AAP_NS="${AAP_NAMESPACE:-aap}"
GITLAB_NS="${GITLAB_NAMESPACE:-gitlab}"
SDLC_NS="${SDLC_NAMESPACE:-}"
STATE_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) SMOKE=true ;;
    --smoke-rules) SMOKE_RULES=true ;;
    --cleanup) CLEANUP=true ;;
    --state-file)
      shift
      STATE_FILE="${1:?}"
      ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ -z "${GUID}" ]]; then
  echo "Usage: $0 <guid> [--smoke] [--smoke-rules] [--cleanup]" >&2
  exit 1
fi

USER="${LIGHTWELL_USER:-user-${GUID}}"
NS_TENANT="lightwell-tenant-${GUID}"
NS_NEXUS="lightwell-nexus-${GUID}"
STATE_FILE="${STATE_FILE:-${TMPDIR:-/tmp}/sdlc-verify-${GUID}.state}"

ok=0
fail=0
warn=0

log_ok() { echo "OK   $*"; ok=$((ok + 1)); }
log_fail() { echo "FAIL $*"; fail=$((fail + 1)); }
log_warn() { echo "WARN $*"; warn=$((warn + 1)); }

cm_get() {
  local key="$1"
  oc get configmap tenant-integration -n "${NS_TENANT}" -o "jsonpath={.data.${key}}" 2>/dev/null || true
}

load_config() {
  if [[ -z "${SDLC_NS}" ]]; then
    SDLC_NS="$(cm_get SDLC_NAMESPACE)"
  fi
  if [[ -z "${SDLC_NS}" ]]; then
    SDLC_NS="sdlc-${GUID}"
  fi
  EDA_WEBHOOK_URL="$(cm_get EDA_WEBHOOK_URL)"
  EDA_ACTIVATION_NAME="$(cm_get EDA_ACTIVATION_NAME)"
  EDA_PROJECT_NAME="$(cm_get EDA_PROJECT_NAME)"
  EDA_ORG_NAME="$(cm_get EDA_ORGANIZATION_NAME)"
  [[ -z "${EDA_ORG_NAME}" ]] && EDA_ORG_NAME="$(cm_get AAP_ORG)"
  GITLAB_URL="$(cm_get GITLAB_URL)"
  GITLAB_PROJECT="$(cm_get REMEDIATION_APP_GITLAB_PATH)"
  NEXUS_URL="$(cm_get NEXUS_URL)"

  if [[ -z "${EDA_ACTIVATION_NAME}" ]]; then
    EDA_ACTIVATION_NAME="sdlc-remediation-${GUID}"
  fi
  if [[ -z "${EDA_WEBHOOK_URL}" ]]; then
    EDA_WEBHOOK_URL="http://${EDA_ACTIVATION_NAME}.${AAP_NS}.svc.cluster.local:5000/"
  fi

  DOMAIN="$(oc get ingresses.config cluster -o jsonpath='{.spec.domain}' 2>/dev/null || true)"
  route_host="$(oc get route "${EDA_ACTIVATION_NAME}" -n "${AAP_NS}" -o jsonpath='{.spec.host}' 2>/dev/null || true)"
  if [[ -n "${route_host}" ]]; then
    EDA_WEBHOOK_ROUTE_URL="https://${route_host}/"
  elif [[ -z "${EDA_WEBHOOK_ROUTE_URL:-}" && -n "${DOMAIN}" ]]; then
    EDA_WEBHOOK_ROUTE_URL="https://${EDA_ACTIVATION_NAME}-${AAP_NS}.${DOMAIN}/"
  fi

  AAP_PASS="$(oc get secret aap-admin-password -n "${AAP_NS}" -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)"
  if [[ -z "${AAP_PASS}" ]]; then
    log_fail "AAP admin password secret (namespace ${AAP_NS})"
    return 1
  fi
  AAP_HOST="$(oc get route -n "${AAP_NS}" -l app.kubernetes.io/managed-by=aap-operator -o jsonpath='{.items[0].spec.host}' 2>/dev/null || true)"
  [[ -z "${AAP_HOST}" ]] && AAP_HOST="$(oc get route aap -n "${AAP_NS}" -o jsonpath='{.spec.host}' 2>/dev/null || true)"
  AAP_BASE="https://${AAP_HOST}"
  return 0
}

aap_curl() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  if [[ -n "${data}" ]]; then
    curl -sk -u "admin:${AAP_PASS}" -X "${method}" "${AAP_BASE}${path}" \
      -H "Content-Type: application/json" -d "${data}"
  else
    curl -sk -u "admin:${AAP_PASS}" -X "${method}" "${AAP_BASE}${path}"
  fi
}

eda_post() {
  local url="$1"
  local body="$2"
  local code="000"
  if [[ "${url}" == http://*svc.cluster.local* ]]; then
    local pod="sdlc-verify-$$"
    local overrides
    overrides="$(python3 -c "
import json,sys
url,body=sys.argv[1],sys.argv[2]
print(json.dumps({
  'spec': {
    'restartPolicy': 'Never',
    'containers': [{
      'name': 'curl',
      'image': 'curlimages/curl:8.5.0',
      'command': ['curl','-sS','-o','/dev/null','-w','%{http_code}',
        '-X','POST', url, '-H','Content-Type: application/json', '-d', body],
      'securityContext': {
        'allowPrivilegeEscalation': False,
        'runAsNonRoot': True,
        'capabilities': {'drop': ['ALL']},
      },
    }],
  },
}))
" "${url}" "${body}")"
    if code="$(oc run "${pod}" --rm -i --restart=Never -n "${AAP_NS}" \
      --image=curlimages/curl:8.5.0 --overrides="${overrides}" 2>/dev/null | tail -1)"; then
      :
    else
      code="000"
    fi
    if [[ "${code}" != "200" && -n "${EDA_WEBHOOK_ROUTE_URL:-}" ]]; then
      code="$(curl -sk -o /dev/null -w '%{http_code}' -X POST "${EDA_WEBHOOK_ROUTE_URL}" \
        -H "Content-Type: application/json" -d "${body}" 2>/dev/null || echo "000")"
    fi
  else
    code="$(curl -sk -o /dev/null -w '%{http_code}' -X POST "${url}" \
      -H "Content-Type: application/json" \
      -d "${body}" 2>/dev/null || echo "000")"
  fi
  [[ "${code}" == "200" ]]
}

max_controller_job_id() {
  aap_curl GET "/api/controller/v2/jobs/?order_by=-id&page_size=1" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('results') or []
print(r[0]['id'] if r else 0)
" 2>/dev/null || echo "0"
}

cleanup_state() {
  if [[ ! -f "${STATE_FILE}" ]]; then
    log_warn "no state file ${STATE_FILE} (nothing to clean)"
    return 0
  fi
  # shellcheck disable=SC1090
  source "${STATE_FILE}"
  echo "=== Cleanup (state: ${STATE_FILE}) ==="

  if [[ -n "${VERIFY_JOB_IDS:-}" ]]; then
    IFS=',' read -r -a ids <<< "${VERIFY_JOB_IDS}"
    for id in "${ids[@]}"; do
      [[ -z "${id}" ]] && continue
      st="$(aap_curl GET "/api/controller/v2/jobs/${id}/" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)"
      if [[ "${st}" == "running" || "${st}" == "pending" ]]; then
        aap_curl POST "/api/controller/v2/jobs/${id}/cancel/" "" >/dev/null 2>&1 || true
        echo "  cancelled job ${id} (${st})"
      elif [[ "${st}" == "successful" || "${st}" == "failed" ]]; then
        aap_curl DELETE "/api/controller/v2/jobs/${id}/" "" >/dev/null 2>&1 || true
        echo "  deleted job ${id} (${st})"
      fi
    done
  fi

  if [[ -n "${VERIFY_GITLAB_HOOK_ID:-}" && -n "${GITLAB_TOKEN:-}" && -n "${GITLAB_PROJECT_ID:-}" ]]; then
    curl -sk -X DELETE -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
      "${GITLAB_URL}/api/v4/projects/${GITLAB_PROJECT_ID}/hooks/${VERIFY_GITLAB_HOOK_ID}" >/dev/null 2>&1 || true
    echo "  removed GitLab verify hook ${VERIFY_GITLAB_HOOK_ID}"
  fi

  rm -f "${STATE_FILE}"
  log_ok "cleanup complete"
}

run_checks() {
  echo "=== SDLC flow verify: ${GUID} (${USER}) ==="
  echo "    EDA webhook (in-cluster): ${EDA_WEBHOOK_URL}"
  [[ -n "${EDA_WEBHOOK_ROUTE_URL:-}" ]] && echo "    EDA webhook (route):        ${EDA_WEBHOOK_ROUTE_URL}"
  echo ""

  echo "=== OpenCode ==="
  if oc get deployment opencode -n "${SDLC_NS}" &>/dev/null; then
    phase="$(oc get pods -n "${SDLC_NS}" -l app=opencode -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo Unknown)"
    if [[ "${phase}" == "Running" ]]; then
      log_ok "opencode pod Running (${SDLC_NS})"
    else
      log_fail "opencode pod (${phase})"
    fi
  else
    log_warn "opencode deployment not in ${SDLC_NS} (skip if SDLC layer not installed)"
  fi

  echo ""
  echo "=== EDA ==="
  if oc get svc "${EDA_ACTIVATION_NAME}" -n "${AAP_NS}" &>/dev/null; then
    log_ok "EDA service ${EDA_ACTIVATION_NAME} (${AAP_NS})"
  else
    log_fail "EDA service ${EDA_ACTIVATION_NAME}"
  fi

  act_json="$(aap_curl GET "/api/eda/v1/activations/" | python3 -c "
import json,sys
name='${EDA_ACTIVATION_NAME}'
for a in json.load(sys.stdin).get('results',[]):
  if a.get('name')==name:
    print(json.dumps(a))
    break
" 2>/dev/null || true)"
  if [[ -z "${act_json}" ]]; then
    log_fail "EDA activation ${EDA_ACTIVATION_NAME}"
  else
    st="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['status'])" "${act_json}")"
    gh="$(python3 -c "import json,sys; print((json.loads(sys.argv[1]).get('git_hash') or '')[:12])" "${act_json}")"
    creds="$(python3 -c "import json,sys; print(len(json.loads(sys.argv[1]).get('eda_credentials') or []))" "${act_json}")"
    if [[ "${st}" == "running" ]]; then
      log_ok "activation ${EDA_ACTIVATION_NAME} status=running git=${gh} eda_credentials=${creds}"
    else
      log_fail "activation ${EDA_ACTIVATION_NAME} status=${st}"
    fi
    if [[ "${creds}" -lt 1 ]]; then
      log_warn "activation missing EDA Controller credential (run_job_template needs it)"
    fi
  fi

  if [[ -n "${EDA_WEBHOOK_ROUTE_URL:-}" ]]; then
    code="$(curl -sk -o /dev/null -w '%{http_code}' -X POST "${EDA_WEBHOOK_ROUTE_URL}" \
      -H "Content-Type: application/json" -d '{"lightwell_verify":true}' 2>/dev/null || echo "000")"
    if [[ "${code}" == "200" ]]; then
      log_ok "EDA route POST (${EDA_WEBHOOK_ROUTE_URL})"
    else
      log_warn "EDA route POST returned ${code} (create Route or fix DNS/TLS)"
    fi
  fi

  echo ""
  echo "=== Controller job templates (${EDA_ORG_NAME}) ==="
  for jt in "SDLC Query TPA" "SDLC Trigger Impact Analyzer" "SDLC Trigger MR Verifier"; do
    jt_q="$(python3 -c "import urllib.parse; print(urllib.parse.quote('${jt}'))")"
    found="$(aap_curl GET "/api/controller/v2/job_templates/?search=${jt_q}" | python3 -c "
import json,sys
jt=sys.argv[1]
org='${EDA_ORG_NAME}'
for x in json.load(sys.stdin).get('results',[]):
  if x.get('name')==jt and x.get('summary_fields',{}).get('organization',{}).get('name')==org:
    print(x['id']); break
" "${jt}" 2>/dev/null || true)"
    if [[ -n "${found}" ]]; then
      log_ok "job template '${jt}' (id=${found})"
    else
      log_fail "job template '${jt}' in org ${EDA_ORG_NAME}"
    fi
  done

  echo ""
  echo "=== GitLab project webhook ==="
  GITLAB_TOKEN="$(oc get secret root-user-personal-token -n "${GITLAB_NS}" -o jsonpath='{.data.token}' 2>/dev/null | base64 -d || true)"
  if [[ -z "${GITLAB_TOKEN}" || -z "${GITLAB_URL}" || -z "${GITLAB_PROJECT}" ]]; then
    log_warn "GitLab token/URL/project not available"
  else
    enc_path="$(python3 -c "import urllib.parse; print(urllib.parse.quote('${GITLAB_PROJECT}', safe=''))")"
    GITLAB_PROJECT_ID="$(curl -sk -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
      "${GITLAB_URL}/api/v4/projects/${enc_path}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || true)"
    if [[ -z "${GITLAB_PROJECT_ID}" ]]; then
      log_fail "GitLab project ${GITLAB_PROJECT}"
    else
      hook_ok="$(curl -sk -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
        "${GITLAB_URL}/api/v4/projects/${GITLAB_PROJECT_ID}/hooks" | python3 -c "
import json,sys
url='${EDA_WEBHOOK_URL}'.rstrip('/')
route='${EDA_WEBHOOK_ROUTE_URL:-}'.rstrip('/')
for h in json.load(sys.stdin):
  u=h.get('url','').rstrip('/')
  if u==url or (route and u==route):
    if h.get('merge_requests_events'): print('yes'); break
" 2>/dev/null || true)"
      if [[ "${hook_ok}" == "yes" ]]; then
        log_ok "GitLab MR webhook → EDA (${GITLAB_PROJECT})"
      else
        log_warn "no GitLab hook to EDA URL (add MR webhook in project settings)"
      fi
    fi
  fi

  echo ""
  echo "=== Nexus reconcile ==="
  if oc get job nexus-reconcile -n "${NS_NEXUS}" &>/dev/null; then
    if [[ "$(oc get job nexus-reconcile -n "${NS_NEXUS}" -o jsonpath='{.status.succeeded}')" == "1" ]]; then
      log_ok "job nexus-reconcile"
    else
      log_warn "job nexus-reconcile not succeeded"
    fi
  else
    log_warn "job nexus-reconcile missing"
  fi
  if [[ -n "${NEXUS_URL}" ]]; then
    code="$(curl -sk -o /dev/null -w '%{http_code}' "${NEXUS_URL}/" 2>/dev/null || echo "000")"
    if [[ "${code}" =~ ^(200|302|401)$ ]]; then
      log_ok "nexus URL ${NEXUS_URL} (${code})"
    else
      log_fail "nexus URL ${NEXUS_URL} (${code})"
    fi
  fi

  echo ""
  echo "=== Tenant bootstrap ==="
  if [[ "$(oc get job eda-bootstrap -n "${NS_TENANT}" -o jsonpath='{.status.succeeded}' 2>/dev/null || echo "")" == "1" ]]; then
    log_ok "job eda-bootstrap"
  else
    log_warn "job eda-bootstrap not succeeded (activation may still be OK if configured manually)"
  fi
}

run_smoke() {
  echo ""
  echo "=== Smoke (connectivity) ==="
  body='{"lightwell_verify":true,"note":"verify-sdlc-flow ping"}'
  if eda_post "${EDA_WEBHOOK_URL}" "${body}"; then
    log_ok "POST in-cluster EDA webhook"
  else
    log_fail "POST in-cluster EDA webhook"
  fi
}

run_smoke_rules() {
  echo ""
  echo "=== Smoke (rules — launches Controller jobs) ==="
  baseline="$(max_controller_job_id)"
  echo "    baseline max job id: ${baseline}"

  payloads=(
    'Nexus CREATED|{"action":"CREATED","component":{"name":"org.lightwell.verify:probe","version":"0.0.0-verify","format":"maven2"}}'
    'tpa_results|{"type":"tpa_results","affected_repos":[{"repo_url":"https://verify.local/none.git"}],"package_info":{"cve_id":"CVE-VERIFY"}}'
    'GitLab MR|{"object_kind":"merge_request","project":{"id":1,"git_http_url":"https://verify.local/g/a"},"object_attributes":{"iid":99999,"state":"opened","source_branch":"update-artifact-verify-0.0.0","target_branch":"main"}}'
  )
  for item in "${payloads[@]}"; do
    label="${item%%|*}"
    body="${item#*|}"
    if eda_post "${EDA_WEBHOOK_URL}" "${body}"; then
      log_ok "smoke payload: ${label}"
    else
      log_fail "smoke payload: ${label}"
    fi
    sleep 2
  done

  sleep 8
  new_ids="$(aap_curl GET "/api/controller/v2/jobs/?order_by=-id&page_size=20" | python3 -c "
import json,sys
base=int(sys.argv[1])
ids=[]
for x in json.load(sys.stdin).get('results',[]):
  if int(x['id'])>base:
    ids.append(str(x['id']))
print(','.join(ids))
" "${baseline}" 2>/dev/null || true)"

  {
    echo "VERIFY_JOB_IDS=${new_ids}"
    echo "VERIFY_BASELINE_JOB_ID=${baseline}"
    echo "GUID=${GUID}"
    echo "GITLAB_URL=${GITLAB_URL:-}"
    echo "GITLAB_PROJECT_ID=${GITLAB_PROJECT_ID:-}"
    echo "GITLAB_TOKEN=${GITLAB_TOKEN:-}"
    echo "VERIFY_GITLAB_HOOK_ID=${VERIFY_GITLAB_HOOK_ID:-}"
  } > "${STATE_FILE}"
  echo "    recorded job ids for cleanup: ${new_ids:-none} → ${STATE_FILE}"
}

main() {
  if ! command -v oc &>/dev/null; then
    echo "ERROR: oc not in PATH" >&2
    exit 1
  fi
  if ! oc whoami &>/dev/null; then
    echo "ERROR: not logged into OpenShift" >&2
    exit 1
  fi

  if [[ "${CLEANUP}" == true ]]; then
    load_config || true
    GITLAB_TOKEN="$(oc get secret root-user-personal-token -n "${GITLAB_NS}" -o jsonpath='{.data.token}' 2>/dev/null | base64 -d || true)"
    cleanup_state
    exit 0
  fi

  load_config
  run_checks
  if [[ "${SMOKE}" == true ]]; then
    run_smoke
  fi
  if [[ "${SMOKE_RULES}" == true ]]; then
    run_smoke_rules
    echo ""
    echo "Run cleanup after review: $0 ${GUID} --cleanup"
  fi

  echo ""
  echo "Summary: ${ok} passed, ${fail} failed, ${warn} warnings"
  [[ "${fail}" -eq 0 ]] || exit 1
}

main
