#!/usr/bin/env bash
# Quick health check for bootstrap-infra platform (run after sync / helm apply).
set -euo pipefail

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

echo "=== Namespaces ==="
for ns in gitlab aap lightwell-tpa lightwell-tas lightwell-quay; do
  check "namespace $ns" "oc get ns $ns"
done

echo ""
echo "=== Operator CSVs (Succeeded) ==="
check "AAP operator CSV" "oc get csv -n aap -l operators.coreos.com/operator=aap-operator -o jsonpath='{.items[0].status.phase}' | grep -q Succeeded"
check "RHTPA CSV" "oc get csv -n lightwell-tpa -l operators.coreos.com/operator=rhtpa-operator -o jsonpath='{.items[0].status.phase}' | grep -q Succeeded"

echo ""
echo "=== Custom resources ==="
check "AAP CR" "oc get ansibleautomationplatform aap -n aap"
check "TPA CR" "oc get trustedprofileanalyzer trustedprofileanalyzer-sample -n lightwell-tpa"
check "QuayRegistry CR" "oc get quayregistry lightwell -n lightwell-quay"

echo ""
echo "=== Routes ==="
for ns in gitlab aap lightwell-quay; do
  check "route in $ns" "oc get route -n $ns --no-headers 2>/dev/null | grep -q ."
done

echo ""
echo "=== Workloads (sample) ==="
check "gitlab pod running" "oc get pods -n gitlab -l app=gitlab -o jsonpath='{.items[0].status.phase}' | grep -q Running"
check "AAP gateway route host" "oc get route -n aap -l app.kubernetes.io/managed-by=aap-operator -o jsonpath='{.items[0].spec.host}' | grep -q ."

echo ""
echo "=== Argo CD ==="
if oc get application lightwell-bootstrap-infra -n openshift-gitops &>/dev/null; then
  sync=$(oc get application lightwell-bootstrap-infra -n openshift-gitops -o jsonpath='{.status.sync.status}')
  health=$(oc get application lightwell-bootstrap-infra -n openshift-gitops -o jsonpath='{.status.health.status}')
  echo "Argo app lightwell-bootstrap-infra: sync=$sync health=$health"
  if [[ "$sync" != "Synced" ]]; then
    echo "  (Push demo-update to GitHub if revision is missing: git push -u origin demo-update)"
    fail=$((fail + 1))
  else
    ok=$((ok + 1))
  fi
fi

echo ""
echo "Tenant checks (after bootstrap-tenant):"
echo "  ./automation/gitops/bootstrap-tenant/scripts/verify-bootstrap-tenant.sh <guid>"

echo ""
echo "Summary: $ok passed, $fail failed (some FAILs are expected while pods/operators are still starting)"
