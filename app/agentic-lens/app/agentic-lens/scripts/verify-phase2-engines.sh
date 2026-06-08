#!/usr/bin/env bash
# Confirm all 12 Reasoning Engines are discoverable via API (Active / listed).
# Run from migration/: ./scripts/verify-phase2-engines.sh
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
require_repo
require_gcloud_project
ensure_venvs

PY="$REPO_ROOT/agentic-lens/.venv/bin/python3"
GET_ID="$REPO_ROOT/scripts/get_agent_engine_id.py"

AGENTS=(
  supervisor chat eng_lead events xray_manager
  eng_scout eng_coder eng_quality_and_security_reviewer
  xray_librarian xray_architect xray_specialist xray_auditor
)

missing=()
echo "Checking ${#AGENTS[@]} engines in ${GCP_PROJECT_ID:-?} (${GCP_LOCATION:-us-west1}) ..."
for a in "${AGENTS[@]}"; do
  id=$("$PY" "$GET_ID" "$a" 2>/dev/null || true)
  if [[ -z "$id" ]]; then
    echo "  MISSING  $a"
    missing+=("$a")
  else
    echo "  OK       $a  (${id##*/})"
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo ""
  echo "FAIL: ${#missing[@]} agent(s) not listed: ${missing[*]}"
  echo "See deploy log and Logs Explorer (reasoning_engine_id from failed deploy)."
  exit 1
fi

echo ""
echo "OK — 12/12 Reasoning Engines listed."
