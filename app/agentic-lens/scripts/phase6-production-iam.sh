#!/usr/bin/env bash
# Phase 6 — Reasoning Engine identity IAM + refresh orchestrators + IAP prep.
# Full LB/IAP: artifacts/iap-load-balancer.md
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
log_phase "Phase 6 — Production IAM (Reasoning Engine identities)"
require_repo
require_gcloud_project
ensure_venvs

LOG="$OUTPUT_DIR/phase6-production-iam.log"
: >"$LOG"

"$MIGRATION_DIR/scripts/grant-reasoning-engine-identity-iam.sh" 2>&1 | tee -a "$LOG"

PY="$REPO_ROOT/agentic-lens/.venv/bin/python3"
if [[ -f "$REPO_ROOT/scripts/merge_peer_engine_env.py" ]]; then
  echo "Merging peer engine IDs..." | tee -a "$LOG"
  "$PY" "$REPO_ROOT/scripts/merge_peer_engine_env.py" "$REPO_ROOT" 2>&1 | tee -a "$LOG" || true
fi

cd "$REPO_ROOT"
export DEPLOY_PARALLEL="${DEPLOY_PARALLEL:-1}"
export ADK_DEPLOY_TIMEOUT="${ADK_DEPLOY_TIMEOUT:-1200}"
echo "Redeploying eng_lead + xray_manager (peer env in running engines)..." | tee -a "$LOG"
SKIP_PREFLIGHT=1 ./deploy.sh eng_lead xray_manager 2>&1 | tee -a "$LOG"

echo ""
echo "Phase 6 IAM complete. Log: $LOG"
echo "Manual IAP/LB: $MIGRATION_DIR/artifacts/iap-load-balancer.md"
