#!/usr/bin/env bash
# Wrapper: SDLC flow verify lives in lw-sdlc-opencode (canonical SCM repo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../../lw-sdlc-opencode" && pwd)"
exec "${ROOT}/gitops/scripts/verify-sdlc-flow.sh" "$@"
