#!/usr/bin/env bash
# Health check for one bootstrap-tenant release (per guid).
# Usage: ./verify-bootstrap-tenant.sh <guid> [username]
set -euo pipefail

GUID="${1:-}"
if [[ -z "${GUID}" ]]; then
  echo "Usage: $0 <guid> [username]" >&2
  echo "  username defaults to user-<guid>" >&2
  exit 1
fi
USER="${2:-user-${GUID}}"
DOMAIN="${LIGHTWELL_DOMAIN:-}"
if [[ -z "${DOMAIN}" ]]; then
  DOMAIN=$(oc get ingresses.config cluster -o jsonpath='{.spec.domain}' 2>/dev/null || true)
fi

ok=0
fail=0
check() {
  local name="$1"
  shift
  if eval "$@" &>/dev/null; then
    echo "OK   $name"
    ok=$((ok + 1))
  else
    echo "FAIL $name"
    fail=$((fail + 1))
  fi
}

NS_JOB="lightwell-tenant-${GUID}"
NS_NEXUS="lightwell-nexus-${GUID}"
NS_APP="${USER}-app"
ORG="user-${GUID}"

echo "=== Tenant ${GUID} (${USER}) ==="
echo ""

echo "=== Namespaces ==="
for ns in "${NS_APP}" "${NS_JOB}" "${NS_NEXUS}"; do
  check "namespace $ns" "oc get ns $ns"
done

echo ""
echo "=== Nexus ==="
check "nexus pod Running" "oc get pods -n ${NS_NEXUS} -l app=nexus -o jsonpath='{.items[0].status.phase}' | grep -q Running"
if oc get route nexus -n "${NS_NEXUS}" &>/dev/null; then
  host=$(oc get route nexus -n "${NS_NEXUS}" -o jsonpath='{.spec.host}')
  code=$(curl -sk -o /dev/null -w '%{http_code}' "https://${host}/" 2>/dev/null || echo "000")
  if [[ "${code}" =~ ^(200|302|401)$ ]]; then
    echo "OK   nexus route https://${host}/ (${code})"
    ok=$((ok + 1))
  else
    echo "FAIL nexus route https://${host}/ (${code})"
    fail=$((fail + 1))
  fi
else
  echo "FAIL nexus route"
  fail=$((fail + 1))
fi

echo ""
echo "=== Bootstrap Jobs (recent) ==="
for job in create-gitlab-tenant create-aap-tenant seed-tpa-uploader nexus-reconcile eda-bootstrap; do
  if oc get job "${job}" -n "${NS_JOB}" &>/dev/null 2>&1 || oc get job "${job}" -n "${NS_NEXUS}" &>/dev/null 2>&1; then
    jns="${NS_JOB}"
    oc get job "${job}" -n "${NS_NEXUS}" &>/dev/null && jns="${NS_NEXUS}"
    succeeded=$(oc get job "${job}" -n "${jns}" -o jsonpath='{.status.succeeded}' 2>/dev/null || echo "")
    if [[ "${succeeded}" == "1" ]]; then
      echo "OK   job ${job} (${jns})"
      ok=$((ok + 1))
    else
      echo "WARN job ${job} (${jns}) not succeeded yet (check: oc logs job/${job} -n ${jns})"
    fi
  fi
done

echo ""
echo "=== Argo CD ==="
if oc get application "lightwell-tenant-${GUID}" -n openshift-gitops &>/dev/null; then
  sync=$(oc get application "lightwell-tenant-${GUID}" -n openshift-gitops -o jsonpath='{.status.sync.status}')
  health=$(oc get application "lightwell-tenant-${GUID}" -n openshift-gitops -o jsonpath='{.status.health.status}')
  echo "Argo app lightwell-tenant-${GUID}: sync=${sync} health=${health}"
  if [[ "$sync" == "Synced" ]]; then ok=$((ok + 1)); else fail=$((fail + 1)); fi
else
  echo "SKIP Argo app lightwell-tenant-${GUID} (not installed)"
fi

if [[ -n "${DOMAIN}" ]]; then
  echo ""
  echo "=== URLs (domain ${DOMAIN}) ==="
  echo "  GitLab:  https://gitlab-gitlab.${DOMAIN}"
  echo "  Nexus:   https://nexus-${NS_NEXUS}.${DOMAIN} (or route host above)"
  echo "  AAP org: ${ORG}"
fi

echo ""
echo "Summary: $ok passed, $fail failed"
[[ "${fail}" -eq 0 ]] || exit 1
