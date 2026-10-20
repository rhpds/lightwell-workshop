#!/usr/bin/env bash
# Reset tenant Acme GitLab apps to their upstream GitHub seed state so Path 2
# (AO) demos can be re-run. Mirrors create-gitlab-tenant seed_app: clone GitHub
# → inject .lightwell/policy.json → force-push main → close leftover MRs /
# delete update-artifact-* branches.
#
# Usage:
#   ./reset-demo-repos.sh <guid>
#   ./reset-demo-repos.sh <guid> --dry-run
#   ./reset-demo-repos.sh <guid> --app wire-transfer-svc   # one app only
#
# Requires: oc, curl, git, python3; cluster-admin (or GitLab root PAT access).
# Does NOT touch the upstream GitHub repos — only re-seeds acme-<guid>/* on
# the shared cluster GitLab.

set -euo pipefail

GUID=""
DRY_RUN=false
ONLY_APP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    --dry-run) DRY_RUN=true ;;
    --app)
      shift
      ONLY_APP="${1:?--app requires a name}"
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      if [[ -z "${GUID}" ]]; then
        GUID="$1"
      else
        echo "Unexpected argument: $1" >&2
        exit 1
      fi
      ;;
  esac
  shift
done

if [[ -z "${GUID}" ]]; then
  echo "Usage: $0 <guid> [--dry-run] [--app NAME]" >&2
  exit 1
fi

for cmd in oc curl git python3; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "ERROR: ${cmd} required on PATH" >&2
    exit 1
  fi
done

GITLAB_NS="${GITLAB_NAMESPACE:-gitlab}"
GROUP="acme-${GUID}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

# name|sourceRepo|sourceRef|policy_json
APPS=(
  "wire-transfer-svc|https://github.com/redhat-ads-tech/wire-transfer-svc.git|main|{\"remediation_owner\":\"ao\",\"approval\":\"needs_approval\",\"riskClass\":\"HIGH\",\"riskRationale\":\"Payment-critical / PCI-scoped system — requires human review\"}"
  "benefits-mgmt-app|https://github.com/redhat-ads-tech/benefits-mgmt-app.git|main|{\"remediation_owner\":\"ao\",\"approval\":\"auto_approve\",\"riskClass\":\"LOW\",\"riskRationale\":\"Internal HR application — no regulated data\"}"
  "report-generator-app|https://github.com/redhat-ads-tech/report-generator-app.git|main|{\"remediation_owner\":\"renovate\",\"riskClass\":\"LOW\",\"riskRationale\":\"Internal reporting tool — no regulated data\"}"
)

GITLAB_HOST="$(oc get route gitlab -n "${GITLAB_NS}" -o jsonpath='{.spec.host}' 2>/dev/null || true)"
if [[ -z "${GITLAB_HOST}" ]]; then
  GITLAB_HOST="$(oc get route -n "${GITLAB_NS}" -o jsonpath='{.items[0].spec.host}' 2>/dev/null || true)"
fi
if [[ -z "${GITLAB_HOST}" ]]; then
  echo "ERROR: could not find GitLab route in ${GITLAB_NS}" >&2
  exit 1
fi
[[ "${GITLAB_HOST}" == http* ]] || GITLAB_HOST="https://${GITLAB_HOST}"

ROOT_TOKEN="$(oc get secret root-user-personal-token -n "${GITLAB_NS}" -o jsonpath='{.data.token}' 2>/dev/null | base64 -d || true)"
if [[ -z "${ROOT_TOKEN}" ]]; then
  echo "ERROR: secret root-user-personal-token not found in ${GITLAB_NS}" >&2
  exit 1
fi

api() {
  local method="$1" path="$2"
  shift 2
  curl -sk -H "PRIVATE-TOKEN: ${ROOT_TOKEN}" -H "Content-Type: application/json" \
    -X "${method}" "${GITLAB_HOST}/api/v4${path}" "$@"
}

enc_path() {
  python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$1"
}

project_id() {
  local path="$1" enc id
  enc="$(enc_path "${path}")"
  id="$(api GET "/projects/${enc}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || true)"
  echo "${id}"
}

close_open_mrs() {
  local pid="$1"
  local mrs
  mrs="$(api GET "/projects/${pid}/merge_requests?state=opened&per_page=50")"
  RESET_DRY_RUN="$([[ "${DRY_RUN}" == true ]] && echo 1 || echo 0)" \
  python3 -c '
import json,sys,urllib.request,ssl,os
pid,token,host=sys.argv[1:4]
mrs=json.load(sys.stdin)
ctx=ssl._create_unverified_context()
for m in mrs:
  iid=m["iid"]
  br=m.get("source_branch") or ""
  print(f"  closing MR !{iid} ({br})")
  if os.environ.get("RESET_DRY_RUN")=="1":
    continue
  req=urllib.request.Request(
    f"{host}/api/v4/projects/{pid}/merge_requests/{iid}",
    data=json.dumps({"state_event":"close"}).encode(),
    headers={"PRIVATE-TOKEN":token,"Content-Type":"application/json"},
    method="PUT",
  )
  with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
    r.read()
' "${pid}" "${ROOT_TOKEN}" "${GITLAB_HOST}" <<<"${mrs}"
}

delete_remediation_branches() {
  local pid="$1"
  local branches
  branches="$(api GET "/projects/${pid}/repository/branches?per_page=100")"
  RESET_DRY_RUN="$([[ "${DRY_RUN}" == true ]] && echo 1 || echo 0)" \
  python3 -c '
import json,sys,urllib.request,ssl,os,urllib.parse
pid,token,host=sys.argv[1:4]
branches=json.load(sys.stdin)
ctx=ssl._create_unverified_context()
for b in branches:
  name=b.get("name") or ""
  if not (name.startswith("update-artifact-") or name.startswith("remediate-")):
    continue
  print(f"  deleting branch {name}")
  if os.environ.get("RESET_DRY_RUN")=="1":
    continue
  enc=urllib.parse.quote(name, safe="")
  req=urllib.request.Request(
    f"{host}/api/v4/projects/{pid}/repository/branches/{enc}",
    headers={"PRIVATE-TOKEN":token},
    method="DELETE",
  )
  try:
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
      r.read()
  except Exception as e:
    print(f"    WARN: {e}")
' "${pid}" "${ROOT_TOKEN}" "${GITLAB_HOST}" <<<"${branches}"
}

reset_app() {
  local name="$1" source_repo="$2" source_ref="$3" policy_json="$4"
  local project_path="${GROUP}/${name}"
  local pid work push_url push_auth

  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo " Reset ${project_path}"
  echo " From:  ${source_repo} @ ${source_ref}"
  echo "════════════════════════════════════════════════════════════"

  pid="$(project_id "${project_path}")"
  if [[ -z "${pid}" ]]; then
    echo "ERROR: GitLab project ${project_path} not found" >&2
    return 1
  fi
  echo "  project id=${pid}"

  echo "  closing open MRs…"
  close_open_mrs "${pid}"

  echo "  deleting remediation branches…"
  delete_remediation_branches "${pid}"

  if [[ "${DRY_RUN}" == true ]]; then
    echo "  (dry-run — skip clone/force-push)"
    return 0
  fi

  # Unprotect main for force-push (same as bootstrap seed).
  api DELETE "/projects/${pid}/protected_branches/${DEFAULT_BRANCH}" -o /dev/null || true

  work="$(mktemp -d)"
  echo "  cloning ${source_repo} (${source_ref})…"
  # Full clone — GitLab rejects force-push of a shallow history ("shallow update not allowed").
  git -c http.sslVerify=false clone --branch "${source_ref}" "${source_repo}" "${work}/src"
  (
    cd "${work}/src"
    git checkout -B "${DEFAULT_BRANCH}"
    git config user.email "lightwell-seed@example.com"
    git config user.name "lightwell-tenant-seed"

    mkdir -p .lightwell
    printf '%s\n' "${policy_json}" > .lightwell/policy.json
    git add .lightwell/policy.json
    if ! git diff --cached --quiet; then
      # Demo helper: never block on local GPG pinentry.
      git -c commit.gpgsign=false commit -m "Add .lightwell/policy.json for Lightwell remediation routing"
    fi

    push_url="${GITLAB_HOST}/${project_path}.git"
    push_auth="$(echo "${push_url}" | sed "s#https://#https://oauth2:${ROOT_TOKEN}@#" | sed "s#http://#http://oauth2:${ROOT_TOKEN}@#")"
    git remote add gitlab "${push_auth}"
    echo "  force-pushing ${DEFAULT_BRANCH} → ${project_path}…"
    git -c http.sslVerify=false push gitlab "${DEFAULT_BRANCH}" --force
  )
  rm -rf "${work}"

  api POST "/projects/${pid}/protected_branches" \
    -d "{\"name\":\"${DEFAULT_BRANCH}\",\"push_access_level\":40,\"merge_access_level\":40}" \
    -o /dev/null || true

  echo "  OK — ${project_path} reset to upstream ${source_ref}"
}

echo "Tenant guid: ${GUID}"
echo "GitLab:      ${GITLAB_HOST}"
echo "Group:       ${GROUP}"
[[ "${DRY_RUN}" == true ]] && echo "Mode:        DRY-RUN"

for entry in "${APPS[@]}"; do
  IFS='|' read -r name repo ref policy <<<"${entry}"
  if [[ -n "${ONLY_APP}" && "${name}" != "${ONLY_APP}" ]]; then
    continue
  fi
  reset_app "${name}" "${repo}" "${ref}" "${policy}"
done

echo ""
echo "Done. Acme apps match GitHub seed + .lightwell/policy.json."
echo "Re-run Path 2 with:  ./trigger-nexus-webhook.sh ${GUID} needs-approval"
