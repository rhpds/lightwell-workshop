#!/usr/bin/env bash
# Run test-lab-flow.sh against many tenants at once and report two things:
# whether each tenant passed, and whether the *cluster* was the reason any of
# them did not.
#
# A tenant failing alone is a lab bug. Ten tenants failing together, with
# pods Pending and nodes at 95% of allocatable, is a capacity result — and
# the two look identical in a single tenant's log, which is why this script
# samples the cluster while the tests run rather than afterwards.
#
# Usage:
#   ./test-fleet.sh <guid> <guid> ...          # all in parallel
#   ./test-fleet.sh --jobs 3 <guid> ...        # at most 3 at a time
#   ./test-fleet.sh --guids a,b,c              # comma-separated
#   ./test-fleet.sh --from guids.txt           # one per line
#   ./test-fleet.sh --stagger 30 <guid> ...    # N seconds between starts
#   ./test-fleet.sh --only 1,2 <guid> ...      # passed through per tenant
#
# Anything after `--` goes to test-lab-flow.sh verbatim:
#   ./test-fleet.sh --guids a,b -- --reset --auto-only
#
# Needs cluster-admin on the cluster hosting every tenant.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FLOW="${HERE}/test-lab-flow.sh"
[[ -x "$FLOW" ]] || { echo "cannot find test-lab-flow.sh next to this script" >&2; exit 2; }

GUIDS=(); JOBS=0; STAGGER=0; PASS_THROUGH=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --jobs)    JOBS="$2"; shift ;;
    --stagger) STAGGER="$2"; shift ;;
    --guids)   IFS=, read -r -a _g <<< "$2"; GUIDS+=("${_g[@]}"); shift ;;
    --from)    while read -r l; do [[ -n "${l// }" ]] && GUIDS+=("$l"); done < "$2"; shift ;;
    --only|--reset|--auto-only|--human-only)
               PASS_THROUGH+=("$1")
               [[ "$1" == "--only" ]] && { PASS_THROUGH+=("$2"); shift; } ;;
    --)        shift; PASS_THROUGH+=("$@"); break ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)        echo "unknown arg: $1" >&2; exit 2 ;;
    *)         GUIDS+=("$1") ;;
  esac
  shift
done
(( ${#GUIDS[@]} )) || { echo "usage: $0 [--jobs N] [--stagger S] <guid> ..." >&2; exit 2; }
(( JOBS > 0 )) || JOBS=${#GUIDS[@]}

RUN="/tmp/lw-fleet-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN"
echo "Fleet run: ${#GUIDS[@]} tenants, up to ${JOBS} at a time"
echo "Logs:      ${RUN}"
echo

#############################################################################
# Cluster sampler
#
# Runs for the life of the fleet. Everything it records is a number a human
# can check afterwards — "the cluster looked busy" is not a finding.
#############################################################################
sample_cluster() {
  local out="${RUN}/cluster-samples.tsv"
  printf 'ts\tpods_pending\tpods_notready\tunschedulable\toomkilled\tevicted\tnode_cpu_pct\tnode_mem_pct\n' > "$out"
  while :; do
    local pending notready unsched oom evicted cpu mem
    pending=$(oc get pods -A --field-selector=status.phase=Pending --no-headers 2>/dev/null | wc -l | tr -d ' ')
    # Columns are NAMESPACE NAME READY STATUS RESTARTS AGE — STATUS is $4.
    # Reading $3 counts the "1/1" READY column and reports almost every pod
    # in the cluster as broken.
    notready=$(oc get pods -A --no-headers 2>/dev/null \
               | awk '$4!="Running" && $4!="Completed" && $4!="Succeeded"' | wc -l | tr -d ' ')
    unsched=$(oc get events -A --field-selector=reason=FailedScheduling --no-headers 2>/dev/null | wc -l | tr -d ' ')
    oom=$(oc get pods -A -o jsonpath='{range .items[*]}{range .status.containerStatuses[*]}{.lastState.terminated.reason}{"\n"}{end}{end}' 2>/dev/null \
          | grep -c OOMKilled || true)
    evicted=$(oc get pods -A --no-headers 2>/dev/null | grep -c Evicted || true)
    # `oc adm top` needs metrics-server; absent is a dash, not a zero.
    read -r cpu mem <<< "$(oc adm top nodes --no-headers 2>/dev/null \
      | awk '{gsub(/%/,"",$3); gsub(/%/,"",$5); c+=$3; m+=$5; n++}
             END {if(n) printf "%.0f %.0f", c/n, m/n; else print "- -"}')"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$(date +%H:%M:%S)" "$pending" "$notready" "$unsched" "$oom" "$evicted" "${cpu:--}" "${mem:--}" >> "$out"
    sleep 30
  done
}
sample_cluster & SAMPLER=$!
cleanup() { kill "$SAMPLER" 2>/dev/null; }
trap cleanup EXIT INT TERM

#############################################################################
# Per-tenant run
#############################################################################
one() {
  # Separate statements on purpose: `local a=$1 b=${a}` expands every word
  # before it assigns any of them, so b would see an unset a.
  local guid="$1"
  local log="${RUN}/${guid}.log"
  local start end
  start=$(date +%s)
  "$FLOW" "$guid" ${PASS_THROUGH[@]+"${PASS_THROUGH[@]}"} > "$log" 2>&1
  local rc=$?
  end=$(date +%s)
  # Strip the colour codes the flow script emits before counting.
  local p f s
  p=$(sed 's/\x1b\[[0-9;]*m//g' "$log" | grep -c '^  PASS' || true)
  f=$(sed 's/\x1b\[[0-9;]*m//g' "$log" | grep -c '^  FAIL' || true)
  s=$(sed 's/\x1b\[[0-9;]*m//g' "$log" | grep -c '^  SKIP' || true)
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$guid" "$rc" "$p" "$f" "$s" "$((end-start))" \
    > "${RUN}/result-${guid}.tsv"
  printf '  %-12s rc=%s  %s passed  %s failed  %s skipped  (%ss)\n' \
    "$guid" "$rc" "$p" "$f" "$s" "$((end-start))"
}

# Count only tenant jobs. `jobs -rp` would also count the sampler, quietly
# making --jobs N run N-1 tenants.
PIDS=()
running() { local n=0 p; for p in ${PIDS[@]+"${PIDS[@]}"}; do kill -0 "$p" 2>/dev/null && n=$((n+1)); done; echo "$n"; }

for g in "${GUIDS[@]}"; do
  while (( $(running) >= JOBS )); do sleep 5; done
  one "$g" &
  PIDS+=($!)
  printf '  started %s\n' "$g"
  (( STAGGER > 0 )) && sleep "$STAGGER"
done
for p in "${PIDS[@]}"; do wait "$p"; done
kill "$SAMPLER" 2>/dev/null

#############################################################################
# Report
#############################################################################
echo
echo "== Per tenant"
printf '  %-14s %-5s %7s %7s %8s %8s\n' GUID RC PASSED FAILED SKIPPED SECONDS
cat "${RUN}"/result-*.tsv 2>/dev/null | sort > "${RUN}/results.tsv"
while IFS=$'\t' read -r g rc p f s d; do
  printf '  %-14s %-5s %7s %7s %8s %8s\n' "$g" "$rc" "$p" "$f" "$s" "$d"
done < "${RUN}/results.tsv"

GREEN=$(awk -F'\t' '$2==0' "${RUN}/results.tsv" 2>/dev/null | wc -l | tr -d ' ')
TOTAL=${#GUIDS[@]}
echo
echo "  ${GREEN}/${TOTAL} tenants fully passed"

echo
echo "== Checks that failed in more than one tenant"
# A check failing everywhere is a platform or content bug; a check failing in
# one tenant is that tenant. Sorting by how many tenants hit it puts the
# systemic ones first, which is the question a fleet run exists to answer.
SHARED=$(sed 's/\x1b\[[0-9;]*m//g' "${RUN}"/*.log 2>/dev/null \
  | grep '^  FAIL' | sed 's/^  FAIL  //' | sort | uniq -c | sort -rn \
  | awk '$1 > 1 {printf "  %2d tenants  %s\n", $1, substr($0, index($0,$2))}' \
  | head -20)
if [[ -n "$SHARED" ]]; then echo "$SHARED"; else echo "  (no check failed in more than one tenant)"; fi

echo
echo "== Cluster during the run"
awk -F'\t' 'NR>1 {
    if ($2>mp) mp=$2; if ($3>mn) mn=$3;
    if ($5>mo) mo=$5; if ($6>me) me=$6;
    if ($7!="-" && $7>mc) mc=$7; if ($8!="-" && $8>mm) mm=$8;
    # FailedScheduling is a cluster-wide running count that already includes
    # events from before this run, so the peak means nothing. The increase
    # over the run is the part this fleet caused.
    if (!n) u0=$4; u=$4; n++
  }
  END {
    if (!n) { print "  no samples"; exit }
    printf "  samples                %d (every 30s)\n", n
    printf "  peak pods Pending      %d\n", mp
    printf "  peak pods not Ready    %d\n", mn
    printf "  new FailedScheduling   %d during the run\n", (u>u0 ? u-u0 : 0)
    printf "  OOMKilled containers   %d\n", mo
    printf "  Evicted pods           %d\n", me
    printf "  peak node CPU          %s%%\n", (mc?mc:"n/a")
    printf "  peak node memory       %s%%\n", (mm?mm:"n/a")
  }' "${RUN}/cluster-samples.tsv"

cat <<EOF

  Read it this way: pods Pending, new FailedScheduling, OOMKilled or Evicted
  above zero means tenants were competing for capacity, so a slow or
  timed-out check is a cluster result rather than a lab bug. All at zero
  means the cluster had room and any failure belongs to the lab.

  Logs and raw samples: ${RUN}
EOF

(( GREEN == TOTAL ))
