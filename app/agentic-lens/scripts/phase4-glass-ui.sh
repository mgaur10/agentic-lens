#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
log_phase "Phase 4 — Glass UI (Cloud Run)"
require_repo
require_gcloud_project

if [[ ! -f "$ENV_FILE" ]]; then
  die "Missing .env — run phase2 write-engine-ids or set AGENTIC_LENS_SUPERVISOR_ENGINE"
fi
if ! grep -q 'AGENTIC_LENS_SUPERVISOR_ENGINE=projects/' "$ENV_FILE" 2>/dev/null; then
  echo "WARN: AGENTIC_LENS_SUPERVISOR_ENGINE not set in .env"
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

export GCP_PROJECT_ID="${GCP_PROJECT_ID:-$PROJECT_ID}"
export REGION="${REGION:-$GCP_LOCATION}"

if [[ "${GLASS_UI_ALLOW_UNAUTHENTICATED:-0}" == "1" ]]; then
  export GLASS_UI_ALLOW_UNAUTHENTICATED=1
  echo "Deploying with public invoke (dev only)"
fi

cd "$REPO_ROOT"
./deploy-glass-ui.sh 2>&1 | tee "$OUTPUT_DIR/phase4-glass-ui.log"

"$MIGRATION_DIR/scripts/verify-health.sh" || true
echo "Phase 4 complete."
