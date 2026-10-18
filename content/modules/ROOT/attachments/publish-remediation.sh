#!/usr/bin/env bash
# Publish a Lightwell remediation to the tenant's Nexus and TPA.
# Reproduces the publication flow of the Lightwell Network:
#   1. Uploads a remediated Maven artifact to Nexus (lightwell-remediated repo)
#   2. Publishes OSV advisories to TPA so the base version shows vulnerabilities
#      that are resolved by the remediated version
#
# Usage: ./publish-remediation.sh <groupId:artifactId:version> <rhlw-suffix> [description]
#
# Example:
#   ./publish-remediation.sh com.fasterxml.jackson.core:jackson-databind:2.13.5 rhlw-00001 "Jackson Databind"

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <groupId:artifactId:version> <rhlw-suffix> [description]"
  echo ""
  echo "Example:"
  echo "  $0 com.fasterxml.jackson.core:jackson-databind:2.13.5 rhlw-00001 \"Jackson Databind\""
  exit 1
fi

GAV="$1"
RHLW_SUFFIX="$2"
DESCRIPTION="${3:-Lightwell-remediated build}"

# Parse GAV
GROUP_ID=$(echo "${GAV}" | cut -d: -f1)
ARTIFACT_ID=$(echo "${GAV}" | cut -d: -f2)
BASE_VERSION=$(echo "${GAV}" | cut -d: -f3)
RHLW_VERSION="${BASE_VERSION}.${RHLW_SUFFIX}"
GROUP_PATH=$(echo "${GROUP_ID}" | tr '.' '/')

echo "=== Publishing Lightwell Remediation ==="
echo ""
echo "  Package:     ${GROUP_ID}:${ARTIFACT_ID}"
echo "  Base version: ${BASE_VERSION}"
echo "  LW version:  ${RHLW_VERSION}"
echo "  Description: ${DESCRIPTION}"
echo ""

# Discover tenant GUID
# Derived from the logged-in user, which is right in the Showroom terminal.
# Overridable because anyone debugging as cluster-admin would otherwise get
# GUID=admin and every namespace lookup would miss.
GUID="${GUID:-$(oc whoami | sed 's/user-//')}"
USERNAME="user-${GUID}"

# ---------------------------------------------------------------------------
# Part 1: Nexus — upload remediated artifact
# ---------------------------------------------------------------------------
echo "--- Discovering Nexus ---"
NEXUS_NS="lightwell-nexus-${GUID}"
NEXUS_HOST=$(oc get route nexus -n "${NEXUS_NS}" -o jsonpath='{.spec.host}' 2>/dev/null || oc get route -n "${NEXUS_NS}" -o jsonpath='{.items[0].spec.host}' 2>/dev/null)
NEXUS_PASS=$(oc get secret nexus-admin-secret -n "${NEXUS_NS}" -o jsonpath='{.data.password}' | base64 -d)
echo "  Nexus host: ${NEXUS_HOST}"
echo "  Nexus namespace: ${NEXUS_NS}"
echo ""

# Create POM
echo "--- Creating POM ---"
POM_FILE=$(mktemp)

# Carry the upstream licence into the remediated POM. A real Lightwell rebuild
# keeps the original licence; a POM that declares none reads as "the licence
# was removed" to anything comparing the two, which is exactly what the
# merge request's License compliance check does.
LICENSE_BLOCK=$(curl -sk --max-time 30 \
  "https://${NEXUS_HOST}/repository/maven-public/${GROUP_PATH}/${ARTIFACT_ID}/${BASE_VERSION}/${ARTIFACT_ID}-${BASE_VERSION}.pom" 2>/dev/null \
  | python3 -c "
import re, sys
pom = sys.stdin.read()
m = re.search(r'<licenses>.*?</licenses>', pom, re.S)
print(('    ' + m.group(0).strip()) if m else '')
" 2>/dev/null || true)
if [ -n "${LICENSE_BLOCK}" ]; then
  echo "  Carrying upstream licence through"
else
  echo "  WARN: no <licenses> found upstream for ${ARTIFACT_ID} ${BASE_VERSION}"
fi

cat > "${POM_FILE}" <<POMEOF
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>${GROUP_ID}</groupId>
    <artifactId>${ARTIFACT_ID}</artifactId>
    <version>${RHLW_VERSION}</version>
    <name>${DESCRIPTION}</name>
    <description>Lightwell-remediated build of ${ARTIFACT_ID} ${BASE_VERSION}</description>
${LICENSE_BLOCK}
</project>
POMEOF
echo "  POM created"

# Create placeholder JAR
echo "--- Creating JAR ---"
JAR_FILE=$(mktemp)
echo "remediated-${RHLW_VERSION}" > /tmp/lw-placeholder.txt
jar cf "${JAR_FILE}" /tmp/lw-placeholder.txt 2>/dev/null || zip -j "${JAR_FILE}" /tmp/lw-placeholder.txt 2>/dev/null
echo "  JAR created"

# Create maven-metadata.xml
echo "--- Creating Maven metadata ---"
META_FILE=$(mktemp)
cat > "${META_FILE}" <<METAEOF
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>${GROUP_ID}</groupId>
  <artifactId>${ARTIFACT_ID}</artifactId>
  <versioning>
    <latest>${RHLW_VERSION}</latest>
    <release>${RHLW_VERSION}</release>
    <versions>
      <version>${RHLW_VERSION}</version>
    </versions>
  </versioning>
</metadata>
METAEOF
echo "  Metadata created"

# Upload to Nexus
REPO="lightwell-remediated"
BASE_URL="https://${NEXUS_HOST}/repository/${REPO}/${GROUP_PATH}/${ARTIFACT_ID}"

echo ""
echo "--- Publishing to Nexus (${REPO}) ---"

echo -n "  Uploading POM... "
HTTP=$(curl -sk -u "admin:${NEXUS_PASS}" -X PUT \
  "${BASE_URL}/${RHLW_VERSION}/${ARTIFACT_ID}-${RHLW_VERSION}.pom" \
  -H "Content-Type: application/xml" --data-binary @"${POM_FILE}" -o /dev/null -w "%{http_code}")
echo "HTTP ${HTTP}"

echo -n "  Uploading JAR... "
HTTP=$(curl -sk -u "admin:${NEXUS_PASS}" -X PUT \
  "${BASE_URL}/${RHLW_VERSION}/${ARTIFACT_ID}-${RHLW_VERSION}.jar" \
  -H "Content-Type: application/java-archive" --data-binary @"${JAR_FILE}" -o /dev/null -w "%{http_code}")
echo "HTTP ${HTTP}"

echo -n "  Uploading metadata... "
HTTP=$(curl -sk -u "admin:${NEXUS_PASS}" -X PUT \
  "${BASE_URL}/maven-metadata.xml" \
  -H "Content-Type: application/xml" --data-binary @"${META_FILE}" -o /dev/null -w "%{http_code}")
echo "HTTP ${HTTP}"

rm -f "${POM_FILE}" "${JAR_FILE}" "${META_FILE}" /tmp/lw-placeholder.txt

echo ""
echo "  ${GROUP_ID}:${ARTIFACT_ID}:${RHLW_VERSION}"
echo "  is now available in https://${NEXUS_HOST}/repository/${REPO}"

# ---------------------------------------------------------------------------
# Part 2: TPA — publish OSV advisories
# ---------------------------------------------------------------------------
echo ""
echo "--- Discovering TPA ---"
TPA_NS="tpa-${GUID}"

# Derive TPA and SSO hostnames from the Nexus hostname
# Nexus:  nexus-lightwell-nexus-{guid}.apps.{cluster}
# TPA:    tpa-{guid}.apps.{cluster}
# SSO:    sso.apps.{cluster}
APPS_DOMAIN=$(echo "${NEXUS_HOST}" | sed "s/^nexus-lightwell-nexus-${GUID}\.//")
# Prefer the real server Route. tpa-{guid} is the tpa-short-url Route, which
# serves the UI redirect but not /api, so every API call against it returns
# nothing and the script dies on pipefail with no message.
TPA_HOST=$(oc get route -n "tpa-${GUID}" -l app.kubernetes.io/name=server \
  -o jsonpath='{.items[0].spec.host}' 2>/dev/null)
if [ -z "${TPA_HOST}" ]; then
  TPA_HOST=$(oc get route -n "tpa-${GUID}" -o jsonpath='{range .items[*]}{.spec.host}{"\n"}{end}' 2>/dev/null \
    | grep -E "^server-" | head -1)
fi
TPA_HOST="${TPA_HOST:-tpa-${GUID}.${APPS_DOMAIN}}"
KC_HOST="sso.${APPS_DOMAIN}"

echo "  TPA host: ${TPA_HOST}"
echo "  Keycloak: ${KC_HOST}"

# Get the OIDC client secret for TPA
OIDC_SECRET=$(oc get secret oidc-cli -n "${TPA_NS}" -o jsonpath='{.data.client-secret}' 2>/dev/null | base64 -d 2>/dev/null)
if [ -z "${OIDC_SECRET}" ]; then
  echo ""
  echo "  ERROR: Cannot read the TPA OIDC secret (oidc-cli) in namespace ${TPA_NS}."
  echo "  Your user may not have permission to read secrets in that namespace."
  echo "  Ask your cluster administrator to grant read access, or run this script"
  echo "  as a cluster admin."
  echo ""
  echo "  Nexus remediation was published successfully — only TPA advisories were skipped."
  echo ""
  echo "=== Remediation published (Nexus only) ==="
  exit 0
fi

echo -n "  Acquiring token... "
# Not piped straight into python: an unreachable Keycloak returns an empty
# body, python raises, and set -o pipefail turns that into a bare exit 1 with
# nothing printed -- the failure path below never gets a chance to run.
TOKEN_RAW=$(curl -sk --max-time 60 -X POST \
  "https://${KC_HOST}/realms/sso/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=tpa-cli" \
  -d "client_secret=${OIDC_SECRET}" \
  -d "scope=create:document read:document" || true)
TPA_TOKEN=$(printf '%s' "${TOKEN_RAW}" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('access_token',''))
except Exception:
    print('')
" 2>/dev/null || true)

if [ -z "${TPA_TOKEN}" ]; then
  echo "FAILED"
  echo ""
  echo "  ERROR: Could not acquire an OIDC token from Keycloak."
  echo "  Check that the Keycloak server is reachable at https://${KC_HOST}"
  echo "  and that the tpa-cli client is configured in the sso realm."
  echo ""
  echo "  Nexus remediation was published successfully — only TPA advisories were skipped."
  echo ""
  echo "=== Remediation published (Nexus only) ==="
  exit 0
fi
echo "OK"

# Query TPA for existing vulnerabilities affecting this package
VULN_RAW=$(curl -sk --max-time 60 -w '\n%{http_code}' \
  "https://${TPA_HOST}/api/v3/vulnerability?q=${ARTIFACT_ID}&limit=100" \
  -H "Authorization: Bearer ${TPA_TOKEN}" || true)
VULN_CODE=$(printf '%s' "${VULN_RAW}" | tail -1)
if [ "${VULN_CODE}" != "200" ]; then
  # Previously this was piped straight into python with 2>/dev/null, so an
  # unreachable or erroring TPA killed the script on pipefail with no output
  # at all. Say what happened instead.
  echo ""
  echo "  ERROR: TPA vulnerability query returned HTTP ${VULN_CODE:-000}"
  echo "  URL: https://${TPA_HOST}/api/v3/vulnerability"
  echo "  The Nexus upload above succeeded; only advisory publication is affected."
  exit 1
fi
VULN_IDS=$(printf '%s' "${VULN_RAW}" | sed '$d' | python3 -c "
import sys, json
data = json.load(sys.stdin)
ids = [v['identifier'] for v in data.get('items', []) if v.get('identifier','').startswith('CVE-')]
print(' '.join(ids[:10]))
")

if [ -z "${VULN_IDS}" ]; then
  echo ""
  echo "  No CVEs found for ${ARTIFACT_ID} in TPA — skipping advisory publication."
  echo ""
  echo "=== Remediation published (Nexus only) ==="
  exit 0
fi

# Convert to array and pick up to 3
read -ra CVE_ARRAY <<< "${VULN_IDS}"
CVE_COUNT=${#CVE_ARRAY[@]}
if [ "${CVE_COUNT}" -gt 3 ]; then CVE_COUNT=3; fi

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
GAV_HASH=$(echo -n "${GAV}" | sha256sum | cut -c1-10)
NUM_BASE=$(printf "%d" "0x${GAV_HASH:0:5}")
YEAR=$(date +%Y)

echo ""
echo ""
echo "--- Publishing Lightwell OSV advisories ---"

for i in $(seq 0 $((CVE_COUNT - 1))); do
  CVE_ID="${CVE_ARRAY[$i]}"
  ADV_ID="RHLW-${YEAR}-$((NUM_BASE + i))"
  OSV_FILE=$(mktemp)

  cat > "${OSV_FILE}" <<OSVEOF
{
  "schema_version": "1.6.8",
  "id": "${ADV_ID}",
  "published": "${NOW}",
  "modified": "${NOW}",
  "severity": [
    {
      "type": "CVSS_V3",
      "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    }
  ],
  "references": [
    {
      "url": "https://access.redhat.com/security/updates/lightwell",
      "type": "WEB"
    }
  ],
  "summary": "${DESCRIPTION}: Lightwell remediation for ${CVE_ID}",
  "details": "${GROUP_ID}:${ARTIFACT_ID} ${BASE_VERSION} is affected by ${CVE_ID}. The Lightwell-remediated build ${RHLW_VERSION} resolves this vulnerability while preserving API compatibility.",
  "aliases": ["${CVE_ID}"],
  "affected": [
    {
      "package": {
        "ecosystem": "Maven",
        "name": "${GROUP_ID}:${ARTIFACT_ID}"
      },
      "ranges": [
        {
          "type": "ECOSYSTEM",
          "events": [
            {
              "introduced": "0"
            },
            {
              "fixed": "${RHLW_VERSION}"
            }
          ]
        }
      ]
    }
  ],
  "credits": [
    {
      "name": "Red Hat Lightwell",
      "type": "REMEDIATION_DEVELOPER"
    }
  ],
  "database_specific": {
    "lightwell": {
      "source": "pnc-build",
      "backport_base_version": "${BASE_VERSION}"
    }
  }
}
OSVEOF

  echo -n "  ${ADV_ID} (${CVE_ID}): "
  HTTP=$(curl -sk -X POST "https://${TPA_HOST}/api/v3/advisory" \
    -H "Authorization: Bearer ${TPA_TOKEN}" \
    -H "Content-Type: application/json" \
    --data-binary @"${OSV_FILE}" -o /dev/null -w "%{http_code}")
  echo "HTTP ${HTTP}"

  rm -f "${OSV_FILE}"
done

echo ""
echo "=== Remediation published ==="
echo ""
echo "  Nexus:  ${GROUP_ID}:${ARTIFACT_ID}:${RHLW_VERSION}"
echo "          https://${NEXUS_HOST}/repository/${REPO}"
echo ""
echo "  TPA:    ${CVE_COUNT} advisories published"
echo "          https://${TPA_HOST}"
echo ""
