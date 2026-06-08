#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
log_phase "Phase 0 — Pre-flight"
require_repo
copy_templates_if_missing
require_versions

echo "Checking gcloud authentication..."
gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -1 || die "No active gcloud account"
gcloud auth application-default print-access-token >/dev/null 2>&1 || echo "WARN: ADC not set — run: gcloud auth application-default login"

require_gcloud_project
PN=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
echo "Project number: $PN"

if [[ "${ORG_ID:-}" == "" || "$ORG_ID" == *"REPLACE_ME"* ]]; then
  echo "WARN: ORG_ID not set in versions.env — resolving from project parent..."
  ORG_ID=$(gcloud projects describe "$PROJECT_ID" --format='value(parent)' 2>/dev/null | sed -n 's|^organizations/||p' || true)
  [[ -n "$ORG_ID" ]] && echo "Resolved ORG_ID=$ORG_ID" || echo "WARN: Could not resolve ORG_ID — Agent Identity IAM may fail"
fi

# Sync .env project fields
if [[ -f "$REPO_ROOT/scripts/update_env.py" && -f "$ENV_FILE" ]]; then
  ensure_venvs
  "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/update_env.py" GCP_PROJECT_ID "$PROJECT_ID" "$ENV_FILE" || true
  "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/update_env.py" GCP_PROJECT_NUMBER "$PN" "$ENV_FILE" || true
  "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/update_env.py" GCP_LOCATION "$REGION" "$ENV_FILE" || true
fi

echo ""
echo "Optional: clean local state in app bundle:"
echo "  $REPO_ROOT/scripts/clean_for_fresh_install.sh -f"
echo ""
echo "Review: artifacts/org-policy-preflight.md"
echo "Review: artifacts/agent-gateway-workbook.md"
echo ""
"$MIGRATION_DIR/scripts/collect-project-info.sh" || true

echo "Phase 0 complete."
