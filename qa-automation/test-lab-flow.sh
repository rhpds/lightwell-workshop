#!/usr/bin/env bash
# End-to-end test of the Lightwell lab, Modules 1 to 3, following the same
# steps the attendee is told to perform and asserting what the modules claim
# they will see. (Modules 0 and 4 are prose only — nothing to execute.)
#
#   Module 1  the platform components are reachable and seeded
#   Module 2  Path 1 — Renovate opens an MR, the attendee merges, CI builds
#   Module 3  Path 2 — AO + agents, auto_approve merges itself,
#             needs_approval waits for the attendee
#
# Each check names the module section it comes from, so a failure points at
# the paragraph that has become untrue rather than at a stack trace.
#
# Usage:
#   ./test-lab-flow.sh <guid>                # modules 1-3
#   ./test-lab-flow.sh <guid> --reset        # reset the Acme repos first
#   ./test-lab-flow.sh <guid> --only 1,2     # pick modules
#   ./test-lab-flow.sh <guid> --auto-only    # module 3, low-risk path only
#   ./test-lab-flow.sh <guid> --human-only   # module 3, high-risk path only
#
# Needs cluster-admin (reads tenant secrets). Safe to re-run: every trigger
# uses a fresh .rhlw suffix derived from the clock, because Nexus fires the
# webhook on *component created* and will ignore a repeat.
set -uo pipefail

GUID="${1:-}"; shift || true
RESET=false; RUN_AUTO=true; RUN_HUMAN=true; ONLY="1,2,3"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset) RESET=true ;;
    --only) ONLY="$2"; shift ;;
    --auto-only) RUN_HUMAN=false ;;
    --human-only) RUN_AUTO=false ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done
want() { [[ ",$ONLY," == *",$1,"* ]]; }
[[ -n "$GUID" ]] || { echo "usage: $0 <guid> [--reset] [--only 1,2,3] [--auto-only|--human-only]" >&2; exit 2; }

# Scratch files are per-guid. A fleet run drives ten tenants at once from one
# machine, and with a fixed /tmp path tenant A's SNOW rows get read as tenant
# B's — a silent wrong answer, not a crash.
TMP="/tmp/lw-${GUID}"; mkdir -p "$TMP"

HERE="$(cd "$(dirname "$0")" && pwd)"
# Resolve the repo independently of where this script is invoked from: a copy
# run out of /tmp would otherwise make REPO=/ and every helper path wrong.
REPO="${LW_REPO:-$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null)}"
if [[ ! -x "${REPO}/ao-trigger-helper/publish-remediation.sh" ]]; then
  REPO="$(cd "$HERE/.." && pwd)"
fi
[[ -x "${REPO}/ao-trigger-helper/publish-remediation.sh" ]] || {
  echo "cannot locate the repo; set LW_REPO=/path/to/lightwell-workshop" >&2; exit 2; }
# The Lightwell versioning regex maps the rhlw digits to `major`, and Renovate
# discards a candidate whose major increment exceeds maxMajorIncrement (500).
# A clock-derived suffix like rhlw-121618 is therefore silently skipped:
#   "Skipping ...@2.13.5.rhlw-999999 because major increment 878381
#    exceeds maxMajorIncrement 500"
# So derive the suffix from what the pom already has, +1, exactly as the lab's
# rhlw-00001 / rhlw-00002 sequence does.
next_suffix() {  # next_suffix <app> <artifactId>
  local cur
  cur="$(gl "${GL}/api/v4/projects/$(proj "$1")/repository/files/pom.xml/raw?ref=main" \
         | python3 -c "
import re,sys
t=sys.stdin.read()
m=re.search(r'<artifactId>\s*'+re.escape(sys.argv[1])+r'\s*</artifactId>\s*<version>([^<]+)</version>', t)
v=m.group(1) if m else ''
n=re.search(r'rhlw-(\d+)', v)
print(int(n.group(1))+1 if n else 1)" "$2")"
  printf 'rhlw-%05d' "${cur:-1}"
}
PASS=0; FAIL=0; SKIP=0

c_ok=$'\033[32m'; c_no=$'\033[31m'; c_sk=$'\033[33m'; c_hd=$'\033[1m'; c_z=$'\033[0m'
step()  { printf "\n${c_hd}== %s${c_z}\n" "$*"; }
ok()    { PASS=$((PASS+1)); printf "  ${c_ok}PASS${c_z}  %s\n" "$*"; }
no()    { FAIL=$((FAIL+1)); printf "  ${c_no}FAIL${c_z}  %s\n" "$*"; }
skip()  { SKIP=$((SKIP+1)); printf "  ${c_sk}SKIP${c_z}  %s\n" "$*"; }
info()  { printf "        %s\n" "$*"; }

DOMAIN="$(oc get ingresses.config cluster -o jsonpath='{.spec.domain}' 2>/dev/null)"
[[ -n "$DOMAIN" ]] || { echo "cannot reach the cluster (oc login first)" >&2; exit 1; }
GL="https://gitlab-gitlab.${DOMAIN}"
SNOW="https://$(oc get route snow-mock -n "snow-${GUID}" -o jsonpath='{.spec.host}' 2>/dev/null)"
TPA="https://server-tpa-${GUID}.${DOMAIN}"
KC="https://sso.${DOMAIN}"
GROUP="acme-${GUID}"
GLTOK="$(oc get secret root-user-personal-token -n gitlab -o jsonpath='{.data.token}' | base64 -d)"

gl()  { curl -sk --max-time 30 -H "PRIVATE-TOKEN: ${GLTOK}" "$@"; }
proj(){ python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "${GROUP}/$1"; }
jqp() { python3 -c "import json,sys$1"; }

tpa_token() {
  local sec; sec="$(oc get secret tpa-oidc-client-secret -n keycloak -o jsonpath='{.data.client-secret}' | base64 -d)"
  curl -sk --max-time 40 "${KC}/realms/sso/protocol/openid-connect/token" \
    -d grant_type=client_credentials -d client_id=tpa-cli -d "client_secret=${sec}" \
    | jqp ";print(json.load(sys.stdin).get('access_token',''))"
}

# Wait for `cond` (a shell snippet) to succeed, polling. wait_for <secs> <label> <cmd...>
wait_for() {
  local budget="$1" label="$2"; shift 2
  local waited=0
  while (( waited < budget )); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 10; waited=$((waited+10))
    printf "        …%ss %s\n" "$waited" "$label"
  done
  return 1
}

mr_json() { gl "${GL}/api/v4/projects/$(proj "$1")/merge_requests/$2"; }
latest_mr() {
  gl "${GL}/api/v4/projects/$(proj "$1")/merge_requests?state=all&order_by=created_at" \
    | jqp ";ms=json.load(sys.stdin);print(ms[0]['iid'] if ms else '')"
}

#############################################################################
# MODULE 1 — "The Environment": every component the table lists must answer,
# and the tenant must be seeded with the three Acme apps.
#############################################################################
if want 1; then
step "Module 1 — the platform components are reachable"

check_url() {  # check_url <label> <url> <acceptable codes regex>
  local label="$1" url="$2" okre="$3" code
  code="$(curl -sk -o /dev/null --max-time 25 -w '%{http_code}' "$url" 2>/dev/null)"
  if [[ "$code" =~ $okre ]]; then ok "$label reachable (HTTP $code)"
  else no "$label not reachable (HTTP ${code:-000}) — $url"; fi
}
check_url "Nexus"         "https://nexus-lightwell-nexus-${GUID}.${DOMAIN}"        '^(200|302|401)$'
check_url "GitLab"        "${GL}/users/sign_in"                                    '^(200|302)$'
check_url "Renovate UI"   "https://renovate-operator-renovate-operator.${DOMAIN}"  '^(200|302|401)$'
check_url "ArgoCD"        "https://openshift-gitops-server-openshift-gitops.${DOMAIN}" '^(200|302|307)$'
check_url "TPA"           "https://tpa-${GUID}.${DOMAIN}"                           '^(200|302)$'
check_url "ServiceNow"    "${SNOW}"                                                '^(200|302)$'
check_url "Orchestrator"  "https://ao.${DOMAIN}"                                   '^(200|302|401)$'

step "Module 1 — the tenant is seeded"
for app in benefits-mgmt-app wire-transfer-svc report-generator-app; do
  code="$(curl -sk -o /dev/null --max-time 25 -w '%{http_code}' \
    -H "PRIVATE-TOKEN: ${GLTOK}" "${GL}/api/v4/projects/$(proj "$app")")"
  [[ "$code" == 200 ]] && ok "GitLab project ${GROUP}/${app}" \
                       || no "GitLab project ${GROUP}/${app} missing (HTTP $code)"
done
nx="$(curl -sk --max-time 30 -u "admin:$(oc get secret nexus-admin-secret -n "lightwell-nexus-${GUID}" -o jsonpath='{.data.password}' | base64 -d)" \
      "https://nexus-lightwell-nexus-${GUID}.${DOMAIN}/service/rest/v1/repositories" 2>/dev/null \
      | jqp ";
import sys
try: rs=json.load(sys.stdin)
except Exception: rs=[]
print(','.join(sorted(r['name'] for r in rs if 'lightwell' in r['name'] or 'redhat-packages' in r['name'])))")"
[[ "$nx" == *lightwell-remediated* ]] \
  && ok "Nexus Lightwell repos present: ${nx:0:72}" \
  || no "Nexus Lightwell repos missing (got: ${nx:-none})"
fi

#############################################################################
# MODULE 2 — "Renovate (Path 1)": the attendee creates a RenovateJob, publishes
# a remediation, Renovate opens an MR, they merge it, CI builds.
#############################################################################
if want 2; then
step "Module 2 — the RenovateJob the attendee creates"
# The inline renovateConfig is not optional decoration: it repoints the Maven
# datasource at the tenant Nexus and disables the dockerfile/github-actions
# managers. Without it Renovate queries the real packages.redhat.com (which
# the tenant cannot reach), logs "no-result" for every Maven package, and
# instead opens unrelated bumps like java-jdk v27. Keep this in step with
# module-02-renovate.adoc.
TENANT_PW="$(oc get application "lightwell-tenant-${GUID}" -n openshift-gitops \
  -o jsonpath='{.spec.source.helm.values}' 2>/dev/null | awk '/^password:/{print $2}')"
NEXUS_HOST="nexus-lightwell-nexus-${GUID}.${DOMAIN}"
if oc get renovatejob "renovate-${GUID}" -n "user-${GUID}-renovate" >/dev/null 2>&1; then
  have="$(oc get renovatejob "renovate-${GUID}" -n "user-${GUID}-renovate" -o json \
          | jqp ";
import sys
d=json.load(sys.stdin)
print((((d.get('spec') or {}).get('renovateConfig') or {}).get('inline') or ''))")"
  if [[ "$have" == *"$NEXUS_HOST"* && "$have" == *customManagers* ]]; then
    ok "RenovateJob renovate-${GUID} exists with a customManager on the tenant Nexus"
  else
    no "RenovateJob exists but has no customManager pointing at ${NEXUS_HOST}"
    info "Renovate will query packages.redhat.com and never see the .rhlw build."
    oc delete renovatejob "renovate-${GUID}" -n "user-${GUID}-renovate" >/dev/null 2>&1
    info "deleted it; recreating as the module specifies"
  fi
fi
if ! oc get renovatejob "renovate-${GUID}" -n "user-${GUID}-renovate" >/dev/null 2>&1; then
  if oc apply -f - >/dev/null 2>&1 <<EOF
apiVersion: renovate-operator.mogenius.com/v1alpha1
kind: RenovateJob
metadata:
  name: renovate-${GUID}
  namespace: user-${GUID}-renovate
spec:
  schedule: "*/5 * * * *"
  parallelism: 1
  secretRef: renovate-token
  serviceAccount:
    name: renovate-runner
  provider:
    name: gitlab
    endpoint: ${GL}/api/v4
  discoveryFilters:
    - "${GROUP}/report-generator-app"
  image: ghcr.io/renovatebot/renovate:44.145.1
  access:
    adminUsers:
      - "user-${GUID}@demo.redhat.com"
  renovateConfig:
    fileName: config.json
    inline: |
      {
        "onboarding": false,
        "requireConfig": "optional",
        "branchConcurrentLimit": 0,
        "prConcurrentLimit": 0,
        "prHourlyLimit": 0,
        "commitMessagePrefix": "[Lightwell]",
        "commitMessageExtra": "({{{newVersion}}})",
        "hostRules": [
          {
            "matchHost": "${NEXUS_HOST}",
            "hostType": "maven",
            "username": "admin",
            "password": "${TENANT_PW}"
          }
        ],
        "customManagers": [
          {
            "customType": "regex",
            "managerFilePatterns": ["/(^|/)pom\\.xml\$/"],
            "matchStringsStrategy": "any",
            "matchStrings": [
              "<groupId>(?<groupId>[^<]+)</groupId>\\s*<artifactId>(?<artifactId>[^<]+)</artifactId>\\s*<version>(?<currentValue>[^<\${}]+)</version>"
            ],
            "depNameTemplate": "{{{groupId}}}:{{{artifactId}}}",
            "datasourceTemplate": "maven",
            "registryUrlTemplate": "https://${NEXUS_HOST}/repository/maven-public",
            "versioningTemplate": "regex:^(?<compatibility>.*?)([.-]rhlw-(?<major>\\d+)(\\.n(?<minor>\\d+))?)?\$"
          }
        ],
        "packageRules": [
          {
            "matchPackageNames": ["com.acme.*:*"],
            "enabled": false
          }
        ],
        "dockerfile": { "enabled": false },
        "github-actions": { "enabled": false }
      }
EOF
  then ok "RenovateJob created with the Lightwell Nexus config"
  else no "could not create the RenovateJob"; fi
fi

step "Module 2 — publish the Lightwell remediation  ('A New Lightwell Remediation Becomes Available')"
rg_before="$(latest_mr report-generator-app)"
M2SUF="$(next_suffix report-generator-app jackson-databind)"
if GUID="$GUID" "${REPO}/ao-trigger-helper/publish-remediation.sh" \
     com.fasterxml.jackson.core:jackson-databind:2.13.5 "$M2SUF" "Jackson Databind" \
     >${TMP}/m2-publish.log 2>&1; then
  ok "published jackson-databind 2.13.5.${M2SUF}"
  grep -q 'advisories published' ${TMP}/m2-publish.log \
    && ok "OSV advisories published to TPA" \
    || no "no advisories published — 'Confirming the Vulnerability' needs them"
else
  no "publish failed — see ${TMP}/m2-publish.log"
fi

step "Module 2 — Renovate reacts  ('Watching Renovate React')"
# Must be the *Lightwell* MR. Renovate also proposes ordinary upstream bumps
# (java-jdk, base images) on this repo, and an earlier version of this test
# accepted the first new MR of any kind and merged it — a green run that
# proved nothing about the Lightwell preset.
# Must also be a *new* MR. An earlier version accepted one that was already
# open from a previous run and merged it, passing without Renovate having
# done anything this cycle.
RG_SEEN="$(gl "${GL}/api/v4/projects/$(proj report-generator-app)/merge_requests?state=all&per_page=100" \
  | jqp ";print(','.join(str(m['iid']) for m in json.load(sys.stdin)))")"
lw_mr() {
  gl "${GL}/api/v4/projects/$(proj report-generator-app)/merge_requests?state=opened&per_page=50" \
    | SEEN="$RG_SEEN" jqp ";
import os
seen=set(os.environ.get('SEEN','').split(','))
ms=json.load(sys.stdin)
hit=[m for m in ms if 'jackson-databind' in (m.get('title') or '') and str(m['iid']) not in seen]
print(hit[0]['iid'] if hit else '')"
}
_rg_mr() { [[ -n "$(lw_mr)" ]]; }
if wait_for 1200 "Renovate polls on a 5-minute schedule" _rg_mr; then
  rg_iid="$(lw_mr)"
  rg_title="$(mr_json report-generator-app "$rg_iid" | jqp ";print(json.load(sys.stdin)['title'])")"
  ok "Renovate opened the Lightwell MR !${rg_iid}: ${rg_title:0:58}"
  [[ "$rg_title" == *rhlw-* ]] \
    && ok "it targets the .rhlw remediated build, not an upstream bump" \
    || no "title has no .rhlw version: ${rg_title:0:70}"

  step "Module 2 — the attendee reviews and merges  ('Reviewing and Approving the MR')"
  if gl -X PUT "${GL}/api/v4/projects/$(proj report-generator-app)/merge_requests/${rg_iid}/merge" \
       | grep -q '"state":"merged"'; then
    ok "merged (what the attendee does by clicking Merge)"
  else
    no "merge failed"
  fi

  step "Module 2 — the pipeline builds  ('Watching the Pipeline')"
  _rg_built() { oc get pipelinerun -n "build-${GUID}" --no-headers 2>/dev/null \
                  | grep -q 'build-push-to-main.*True .*Succeeded'; }
  wait_for 900 "waiting for build-push-to-main" _rg_built \
    && ok "push build succeeded" || no "no successful build after the Renovate merge"
else
  no "Renovate never opened an MR for jackson-databind"
  info "Renovate may still have opened unrelated bumps — those do not count."
  info "Check the job logs in user-${GUID}-renovate (schedule */5) and that"
  info "renovate.json extends the Lightwell preset in report-generator-app."
fi
fi

#############################################################################
# MODULE 3 — "AI Remediation (Path 2)"
#############################################################################
if ! want 3; then
  printf "\n${c_hd}== Result${c_z}\n"
  printf "  ${c_ok}%d passed${c_z}  ${c_no}%d failed${c_z}  ${c_sk}%d skipped${c_z}\n" "$PASS" "$FAIL" "$SKIP"
  (( FAIL == 0 )); exit $?
fi

step "Module 3 preflight — the environment the module assumes"

for app in benefits-mgmt-app wire-transfer-svc report-generator-app; do
  pol="$(gl "${GL}/api/v4/projects/$(proj "$app")/repository/files/.lightwell%2Fpolicy.json/raw?ref=main")"
  case "$app:$pol" in
    benefits-mgmt-app:*auto_approve*LOW*)      ok  "$app policy: auto_approve / LOW" ;;
    wire-transfer-svc:*needs_approval*HIGH*)   ok  "$app policy: needs_approval / HIGH" ;;
    report-generator-app:*renovate*)           ok  "$app policy: renovate (skipped by AO)" ;;
    *) no "$app policy unexpected: ${pol:0:90}"
       info "Module 3 'Two Applications, Two Policies' lists these explicitly." ;;
  esac
done

TOK="$(tpa_token)"
if [[ -z "$TOK" ]]; then
  no "cannot get a TPA token"
else
  counts="$(curl -sk --max-time 90 "${TPA}/api/v3/advisory?limit=1000" -H "Authorization: Bearer ${TOK}" \
    | jqp ";
import collections
items=json.load(sys.stdin).get('items',[])
c=collections.Counter((a.get('labels') or {}).get('importer','?') for a in items)
print(c.get('CVElist-v5',0), c.get('GHSA-OSV',0))")"
  cve_n="${counts% *}"; osv_n="${counts#* }"
  if (( cve_n > 0 && osv_n > 0 )); then
    ok "TPA datasets ingested (CVElist-v5=${cve_n}, GHSA-OSV=${osv_n})"
  else
    no "TPA dataset incomplete (CVElist-v5=${cve_n}, GHSA-OSV=${osv_n})"
    info "Without CVE records every MR renders 'CVE: not referenced'."
    info "Re-POST: curl -k -X POST \"\$TPA/api/v3/dataset?labels.importer=CVElist-v5\" \\"
    info "  -H 'Content-Type: application/zip' -H \"Authorization: Bearer \$TOK\" --data-binary @lb1815-cve.zip"
  fi
fi

if $RESET; then
  step "Reset the Acme repos to seed state"
  if "${REPO}/ao-trigger-helper/reset-demo-repos.sh" "$GUID" >${TMP}/m3-reset.log 2>&1; then
    ok "repos reset to upstream + policy.json"
  else
    no "reset failed — see ${TMP}/m3-reset.log"
  fi
fi

#############################################################################
run_path() {
  local kind="$1" gav="$2" desc="$3" app="$4" emoji="$5" risk="$6"
  local before after iid

  step "[$kind] Publish the remediation  (module: 'Publishing the ... Remediation')"
  before="$(latest_mr "$app")"
  local suf; suf="$(next_suffix "$app" "$(echo "$gav" | cut -d: -f2)")"
  if GUID="$GUID" "${REPO}/ao-trigger-helper/publish-remediation.sh" "$gav" "$suf" "$desc" \
       >${TMP}/m3-publish-${kind}.log 2>&1; then
    if grep -q 'advisories published' ${TMP}/m3-publish-${kind}.log; then
      ok "published $gav.$suf with advisories"
    else
      ok "published $gav.$suf (no advisories — CVE columns will be empty)"
    fi
  else
    no "publish failed — see ${TMP}/m3-publish-${kind}.log"; return
  fi

  step "[$kind] A merge request appears  (module: 'The Merge Request the Agent Wrote')"
  _new_mr() { local n; n="$(latest_mr "$app")"; [[ -n "$n" && "$n" != "$before" ]]; }
  if wait_for 420 "waiting for the agent to open the MR" _new_mr; then
    iid="$(latest_mr "$app")"
    ok "MR !$iid opened on $app"
  else
    no "no merge request appeared within 7 minutes"
    info "Check: SDLC Prepare Remediation in AAP — a TPA 504 makes the blast radius empty and it fails closed."
    return
  fi

  local body; body="$(mr_json "$app" "$iid")"
  local title cve pend
  title="$(printf '%s' "$body" | jqp ";print(json.load(sys.stdin)['title'])")"
  cve="$(printf '%s'   "$body" | jqp ";
import re
d=json.load(sys.stdin)['description']
m=re.search(r'\| CVE \| (.+?) \|', d)
print((m.group(1) if m else '').strip())")"
  pend="$(printf '%s'  "$body" | jqp ";print(json.load(sys.stdin)['description'].count('Pending'))")"

  [[ "$title" == *"$emoji"* ]] \
    && ok "title carries the $risk risk marker: ${title:0:60}" \
    || no "title missing $emoji ($risk): ${title:0:70}"

  case "$cve" in
    *CVE-*) ok "Summary names a real CVE: ${cve:0:58}" ;;
    *)      no "Summary shows '${cve}' — the module says the CVE comes from TPA"
            info "Usually the TPA dataset or the advisory lookup, not the agent." ;;
  esac

  (( pend > 0 )) \
    && ok "validation table starts Pending (${pend} rows) — the agent does not test its own change" \
    || skip "table already filled; the Pending window (~110s) was missed"

  step "[$kind] The pipeline fills the table  (module: 'The Pipeline Fills in the Validation Table')"
  _filled() { mr_json "$app" "$iid" | grep -q 'Passed'; }
  if wait_for 600 "waiting for build-pull-request" _filled; then
    local passed
    passed="$(mr_json "$app" "$iid" | jqp ";print(json.load(sys.stdin)['description'].count('Passed'))")"
    ok "table filled by the pipeline (${passed} checks Passed)"
  else
    no "validation table never filled"
  fi

  if [[ "$kind" == auto ]]; then
    step "[auto] It merges itself  (module: 'The Low-Risk Application Merges Itself')"
    _merged() { mr_json "$app" "$iid" | grep -q '"state":"merged"'; }
    if wait_for 900 "waiting for the policy-driven merge" _merged; then
      local created merged passed_at_merge
      created="$(mr_json "$app" "$iid" | jqp ";print(json.load(sys.stdin)['created_at'])")"
      merged="$(mr_json "$app" "$iid"  | jqp ";print(json.load(sys.stdin)['merged_at'])")"
      passed_at_merge="$(mr_json "$app" "$iid" | jqp ";print(json.load(sys.stdin)['description'].count('Passed'))")"
      ok "merged with no human action"
      info "opened ${created:11:8}  merged ${merged:11:8}"
      (( passed_at_merge > 0 )) \
        && ok "merged *after* the checks reported — the ADR-050 gate held" \
        || no "merged with an empty validation table (the gate did not hold)"
    else
      no "auto_approve MR never merged"
    fi
  else
    step "[human] It waits for you  (module: 'The Judgement Call')"
    sleep 20
    local state action
    state="$(mr_json "$app" "$iid" | jqp ";print(json.load(sys.stdin)['state'])")"
    action="$(mr_json "$app" "$iid" | jqp ";
d=json.load(sys.stdin)['description']
print('human review' if 'Requires human review before merge' in d else 'MISSING')")"
    [[ "$state" == opened ]] \
      && ok "MR left open — AO did not merge it" \
      || no "MR state is '$state'; the module says it waits for a person"
    [[ "$action" == "human review" ]] \
      && ok "Recommended Action demands human review regardless of results" \
      || no "Recommended Action does not demand review"

    step "[human] The attendee merges it in GitLab"
    if gl -X PUT "${GL}/api/v4/projects/$(proj "$app")/merge_requests/${iid}/merge" \
         | grep -q '"state":"merged"'; then
      ok "merged by the user (what the attendee does by clicking Merge)"
    else
      no "merge failed"
    fi
  fi

  step "[$kind] Build and deploy  (module: 'Build, Sign, Promote, Deploy')"
  _built() { oc get pipelinerun -n "build-${GUID}" --no-headers 2>/dev/null \
               | grep -q 'build-push-to-main.*True .*Succeeded'; }
  if wait_for 900 "waiting for build-push-to-main" _built; then
    ok "push build succeeded"
  else
    no "no successful build-push-to-main"
  fi
}

$RUN_AUTO  && run_path auto  "org.apache.commons:commons-text:1.9" "Apache Commons Text" \
                             "benefits-mgmt-app" "🟢" "LOW"
$RUN_HUMAN && run_path human "com.h2database:h2:1.4.200"           "H2 Database Engine" \
                             "wire-transfer-svc" "🔴" "HIGH"

#############################################################################
step "ServiceNow  (module: 'The Incident Opens Before the Change Does' / 'The Incident Closes Last')"

inc="$(curl -sk --max-time 40 "${SNOW}/api/v1/incidents")"
printf '%s' "$inc" | jqp ";
import sys
d=json.load(sys.stdin); r=d.get('result',d)
items=r if isinstance(r,list) else r.get('incidents',[])
lw=[i for i in items if (i.get('created_by') or '')=='Lightwell AO']
print('COUNT', len(lw))
for i in lw[:6]:
    print('ROW', i.get('number'), i.get('state'), (i.get('short_description') or '')[:64])
" > ${TMP}/m3-snow.txt
n="$(grep -c '^ROW' ${TMP}/m3-snow.txt || true)"
(( n > 0 )) && ok "Lightwell AO raised ${n} incidents" || no "no incidents raised by Lightwell AO"
grep '^ROW' ${TMP}/m3-snow.txt | while read -r _ num state rest; do info "$num  $state  $rest"; done

if grep -q '\[unknown\]' ${TMP}/m3-snow.txt; then
  no "an incident description still says [unknown] — the CVE did not reach SNOW"
else
  ok "no '[unknown]' in incident descriptions"
fi

_parent_resolved() { grep '^ROW' ${TMP}/m3-snow.txt | grep -q 'Resolved'; }
_parent_resolved \
  && ok "a parent incident reached Resolved (only happens on deploy Healthy)" \
  || skip "no parent Resolved yet — deploy may still be in flight"

step "TPA  (module: 'Proving It in TPA')"
if [[ -n "${TOK:-}" ]]; then
  for app in benefits-mgmt-app wire-transfer-svc; do
    n="$(curl -sk --max-time 60 "${TPA}/api/v2/sbom?q=${app}&limit=100" -H "Authorization: Bearer ${TOK}" \
         | jqp ";print(len(json.load(sys.stdin).get('items',[])))")"
    (( n > 0 )) && ok "TPA holds ${n} SBOM(s) for ${app}" || no "no SBOM in TPA for ${app}"
  done
else
  skip "no TPA token"
fi

#############################################################################
printf "\n${c_hd}== Result${c_z}\n"
printf "  ${c_ok}%d passed${c_z}  ${c_no}%d failed${c_z}  ${c_sk}%d skipped${c_z}\n" "$PASS" "$FAIL" "$SKIP"
(( FAIL == 0 ))
