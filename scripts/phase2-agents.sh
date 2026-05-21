#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
log_phase "Phase 2 — Deploy 12 Reasoning Engines"
require_repo
require_gcloud_project
ensure_venvs

# shellcheck source=/dev/null
source "$VERSIONS_FILE"
if [[ "${SKIP_INFRA_CMEK:-0}" != "1" ]]; then
  if ! grep -q '^AGENT_ENGINE_KMS_KEY_' "$VERSIONS_FILE" 2>/dev/null; then
    echo "WARN: No AGENT_ENGINE_KMS_KEY_* in versions.env — deploy may fail if org requires CMEK"
    if [[ -t 0 && "${MIGRATION_AUTO_YES:-0}" != "1" ]]; then
      read -r -p "Continue anyway? [y/N] " reply
      [[ "${reply^^}" == "Y" || "${reply^^}" == "YES" ]] || exit 1
    else
      echo "Continuing (non-interactive or MIGRATION_AUTO_YES=1)."
    fi
  fi
fi

"$MIGRATION_DIR/scripts/validate-phase2-agent-sources.sh"

cd "$REPO_ROOT"
export DEPLOY_PARALLEL="${DEPLOY_PARALLEL:-8}"
export ADK_DEPLOY_TIMEOUT="${ADK_DEPLOY_TIMEOUT:-1200}"
LOG="$OUTPUT_DIR/phase2-deploy.log"
: >"$LOG"

echo "Tip: gcloud auth application-default set-quota-project ${GCP_PROJECT_ID:-agentic-lens}" | tee -a "$LOG"

PY="$REPO_ROOT/agentic-lens/.venv/bin/python3"

# Greenfield two-step (IMPLEMENTATION.md §7.2): specialists first so eng_lead/xray_manager preflight can resolve peer IDs.
PHASE2_STEP1=(
  chat events
  eng_scout eng_coder eng_quality_and_security_reviewer
  xray_librarian xray_architect xray_specialist xray_auditor
)
PHASE2_STEP2=(eng_lead xray_manager supervisor)

deploy_step() {
  local label="$1"
  shift
  echo "" | tee -a "$LOG"
  echo "========== Phase 2 — $label ==========" | tee -a "$LOG"
  if ! ./deploy.sh "$@" 2>&1 | tee -a "$LOG"; then
    echo "WARN: one or more agents failed in $label — check log; continuing if peers allow step 2." | tee -a "$LOG"
  fi
}

merge_peer_env() {
  if [[ -f "$REPO_ROOT/scripts/merge_peer_engine_env.py" ]]; then
    echo "Merging peer engine IDs into eng_lead / xray_manager configs..." | tee -a "$LOG"
    "$PY" "$REPO_ROOT/scripts/merge_peer_engine_env.py" "$REPO_ROOT" 2>&1 | tee -a "$LOG" || true
  fi
  if [[ -f "$REPO_ROOT/scripts/merge_engineering_vertex_env.py" ]]; then
    "$PY" "$REPO_ROOT/scripts/merge_engineering_vertex_env.py" "$REPO_ROOT" 2>&1 | tee -a "$LOG" || true
  fi
}

echo "Step 1/2: deploy specialists (9 agents, SKIP_PREFLIGHT=1)" | tee -a "$LOG"
SKIP_PREFLIGHT=1 deploy_step "Step 1 — specialists" "${PHASE2_STEP1[@]}"

merge_peer_env

echo "Step 2/2: deploy orchestrators (eng_lead, xray_manager, supervisor)" | tee -a "$LOG"
deploy_step "Step 2 — orchestrators" "${PHASE2_STEP2[@]}"

"$MIGRATION_DIR/scripts/grant-engine-telemetry-iam.sh" 2>&1 | tee -a "$LOG"
"$MIGRATION_DIR/scripts/grant-reasoning-engine-identity-iam.sh" 2>&1 | tee -a "$LOG"

# RE principals need aiplatform.user; orchestrators need peer IDs in the running engine config.
echo "Step 3/3: refresh eng_lead + xray_manager (peer env + IAM)" | tee -a "$LOG"
merge_peer_env
SKIP_PREFLIGHT=1 deploy_step "Step 3 — refresh orchestrators (peer IAM)" eng_lead xray_manager

"$MIGRATION_DIR/scripts/write-engine-ids-to-env.sh" 2>&1 | tee -a "$LOG"
"$MIGRATION_DIR/scripts/verify-phase2-engines.sh" 2>&1 | tee -a "$LOG"

echo ""
echo "Phase 2 complete. Log: $LOG"
echo "Peer IAM: output/grant-re-identity-iam.log (also appended above if tee used separately)"
