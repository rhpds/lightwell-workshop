#!/usr/bin/env bash
# Reset shared Lightwell platform (bootstrap-infra) on a test cluster.
# Tier 3: removes CRs, platform namespaces, and chart ClusterRoleBindings.
# Does NOT remove: openshift-gitops, operators (subscriptions), or tenant namespaces
# unless LIGHTWELL_RESET_TENANTS=1.
#
# Usage:
#   ./reset-lightwell-platform.sh              # infra only
#   LIGHTWELL_RESET_TENANTS=1 ./reset-lightwell-platform.sh
#   LIGHTWELL_RESET_GUID=dvb52-1 ./reset-lightwell-platform.sh   # one tenant only
#   LIGHTWELL_RESET_SDLC=1 ./reset-lightwell-platform.sh
set -euo pipefail

if ! oc whoami &>/dev/null; then
  echo "ERROR: oc not logged in" >&2
  exit 1
fi

if [[ -n "${LIGHTWELL_RESET_GUID:-}" ]]; then
  delete_tenant_cross_ns_rbac() {
    local guid="$1"
    for ns in gitlab aap keycloak; do
      for kind in role rolebinding; do
        oc delete "${kind}" -n "$ns" "lightwell-tenant-gitlab-reader-${guid}" --ignore-not-found 2>/dev/null || true
        oc delete "${kind}" -n "$ns" "lightwell-tenant-aap-reader-${guid}" --ignore-not-found 2>/dev/null || true
        oc delete "${kind}" -n "$ns" "lightwell-tenant-keycloak-reader-${guid}" --ignore-not-found 2>/dev/null || true
      done
    done
  }
  delete_one_tenant() {
    local guid="$1"
    local user="${LIGHTWELL_TENANT_USER:-user-${guid}}"
    echo "==> Removing tenant ${guid} (${user})..."
    oc delete application "lightwell-tenant-${guid}" -n openshift-gitops --ignore-not-found --wait=false 2>/dev/null || true
    oc delete application "sdlc-tenant-${guid}" -n openshift-gitops --ignore-not-found --wait=false 2>/dev/null || true
    delete_tenant_cross_ns_rbac "$guid"
    oc delete clusterrolebinding "anyuid-nexus-${guid}" --ignore-not-found 2>/dev/null || true
    for ns in "lightwell-nexus-${guid}" "lightwell-tenant-${guid}" "${user}-app"; do
      oc delete namespace "$ns" --wait=false 2>/dev/null || true
    done
    if [[ "${LIGHTWELL_RESET_SDLC:-0}" == "1" ]]; then
      oc delete namespace "sdlc-control-plane-${guid}" --ignore-not-found --wait=false 2>/dev/null || true
    fi
  }
  delete_one_tenant "${LIGHTWELL_RESET_GUID}"
  echo ""
  echo "Done (single tenant ${LIGHTWELL_RESET_GUID}). Wait for namespaces to terminate."
  exit 0
fi

delete_tenant_cross_ns_rbac() {
  local guid="$1"
  for ns in gitlab aap keycloak; do
    oc delete role,rolebinding -n "$ns" -l "lightwell.guid=${guid}" --ignore-not-found 2>/dev/null || true
    for kind in role rolebinding; do
      oc delete "${kind}" -n "$ns" "lightwell-tenant-gitlab-reader-${guid}" --ignore-not-found 2>/dev/null || true
      oc delete "${kind}" -n "$ns" "lightwell-tenant-aap-reader-${guid}" --ignore-not-found 2>/dev/null || true
      oc delete "${kind}" -n "$ns" "lightwell-tenant-keycloak-reader-${guid}" --ignore-not-found 2>/dev/null || true
    done
  done
}

delete_one_tenant() {
  local guid="$1"
  local user="${LIGHTWELL_TENANT_USER:-user-${guid}}"
  echo "==> Removing tenant ${guid} (${user})..."
  oc delete application "lightwell-tenant-${guid}" -n openshift-gitops --ignore-not-found --wait=false 2>/dev/null || true
  oc delete application "sdlc-tenant-${guid}" -n openshift-gitops --ignore-not-found --wait=false 2>/dev/null || true
  delete_tenant_cross_ns_rbac "$guid"
  oc delete clusterrolebinding "anyuid-nexus-${guid}" --ignore-not-found 2>/dev/null || true
  for ns in "lightwell-nexus-${guid}" "lightwell-tenant-${guid}" "${user}-app"; do
    oc delete namespace "$ns" --wait=false 2>/dev/null || true
  done
  if [[ "${LIGHTWELL_RESET_SDLC:-0}" == "1" ]]; then
    oc delete namespace "sdlc-control-plane-${guid}" --ignore-not-found --wait=false 2>/dev/null || true
  fi
}

echo "==> Deleting platform custom resources..."
oc delete ansibleautomationplatform aap -n aap --ignore-not-found --wait=false 2>/dev/null || true
oc delete quayregistry lightwell -n lightwell-quay --ignore-not-found --wait=false 2>/dev/null || true
oc delete trustedprofileanalyzer trustedprofileanalyzer-sample -n lightwell-tpa --ignore-not-found --wait=false 2>/dev/null || true
oc delete securesign securesign-sample -n lightwell-tas --ignore-not-found --wait=false 2>/dev/null || true

if [[ "${LIGHTWELL_RESET_SDLC:-0}" == "1" ]]; then
  echo "==> Removing SDLC demo namespaces..."
  oc delete namespace sdlc-control-plane sdlc-mcp-servers --ignore-not-found --wait=false 2>/dev/null || true
  while IFS= read -r ns; do
    [[ -z "$ns" ]] && continue
    oc delete namespace "$ns" --wait=false 2>/dev/null || true
  done < <(oc get ns -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | grep -E '^sdlc-control-plane-' || true)
fi

if [[ "${LIGHTWELL_RESET_TENANTS:-0}" == "1" ]]; then
  echo "==> Removing tenant namespaces (lightwell-nexus-*, *-app, lightwell-tenant-*)..."
  while IFS= read -r ns; do
    [[ -z "$ns" ]] && continue
    guid=""
    if [[ "$ns" =~ ^lightwell-nexus-(.+)$ ]]; then guid="${BASH_REMATCH[1]}"; fi
    if [[ "$ns" =~ ^lightwell-tenant-(.+)$ ]]; then guid="${BASH_REMATCH[1]}"; fi
    if [[ -n "$guid" ]]; then delete_tenant_cross_ns_rbac "$guid"; fi
    oc delete namespace "$ns" --wait=false 2>/dev/null || true
  done < <(oc get ns -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | grep -E '^lightwell-nexus-|^lightwell-tenant-|-app$' || true)
  while IFS= read -r crb; do
    [[ -z "$crb" ]] && continue
    oc delete clusterrolebinding "$crb" --ignore-not-found 2>/dev/null || true
  done < <(oc get clusterrolebinding -o name 2>/dev/null | grep 'anyuid-nexus-' | sed 's|clusterrolebinding/||' || true)
  while IFS= read -r app; do
    [[ -z "$app" ]] && continue
    oc delete application "$app" -n openshift-gitops --ignore-not-found --wait=false 2>/dev/null || true
  done < <(oc get applications -n openshift-gitops -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep -E '^lightwell-tenant-|^sdlc-tenant-' || true)
fi

echo "==> Deleting shared platform namespaces..."
for ns in gitlab aap lightwell-tpa lightwell-tas lightwell-quay lightwell-nexus; do
  oc delete namespace "$ns" --ignore-not-found --wait=false 2>/dev/null || true
done

echo "==> Deleting chart cluster-scoped RBAC..."
oc delete clusterrolebinding system:openshift:scc:anyuid-gitlab system:openshift:scc:anyuid-nexus --ignore-not-found 2>/dev/null || true
oc delete clusterrole gitlab-token-reader --ignore-not-found 2>/dev/null || true

echo "==> Remaining Lightwell-related namespaces (may still be Terminating):"
oc get ns 2>/dev/null | grep -iE 'gitlab|aap|lightwell|nexus|sdlc' || echo "  (none listed)"

echo ""
echo "Done. Wait for namespaces to finish terminating before redeploying bootstrap-infra."
echo "  oc get ns | grep -E 'gitlab|aap|lightwell'"
echo "Optional:"
echo "  LIGHTWELL_RESET_TENANTS=1     — all tenants"
echo "  LIGHTWELL_RESET_GUID=<guid>   — one tenant"
echo "  LIGHTWELL_RESET_SDLC=1        — shared or per-tenant SDLC namespaces"
