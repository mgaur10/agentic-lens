#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
log_phase "Phase 1 — Infrastructure"
require_repo
require_gcloud_project
ensure_venvs

# Migration default: create github-pat-token with placeholder if missing (replace token later)
export CREATE_GITHUB_PAT_PLACEHOLDER="${CREATE_GITHUB_PAT_PLACEHOLDER:-1}"
export VERTEX_RAG_LOCATION="us-west1"

cd "$REPO_ROOT"
APPLY_LOG="$OUTPUT_DIR/phase1-infra.log"

run_range() {
  local from="$1" to="$2"
  echo "Running infra/apply.sh $from $to" | tee -a "$APPLY_LOG"
  RUN_TELEMETRY="${RUN_TELEMETRY:-0}" RUN_SETUP_KB="${RUN_SETUP_KB:-0}" \
    CREATE_GITHUB_PAT_PLACEHOLDER="${CREATE_GITHUB_PAT_PLACEHOLDER:-0}" \
    ./infra/apply.sh "$from" "$to" 2>&1 | tee -a "$APPLY_LOG"
}

# 01–03: APIs, bootstrap, secrets (optional PAT → placeholder secret when configured)
run_range 01 03

# 04 Model Armor
if [[ "${SKIP_INFRA_MODEL_ARMOR:-0}" != "1" ]]; then
  run_range 04 04
else
  echo "SKIP_INFRA_MODEL_ARMOR=1 — verify org Model Armor templates exist" | tee -a "$APPLY_LOG"
fi

# 05 CMEK
if [[ "${SKIP_INFRA_CMEK:-0}" != "1" ]]; then
  run_range 05 05
  echo ">>> Append AGENT_ENGINE_KMS_KEY_* lines from log to versions.env <<<" | tee -a "$APPLY_LOG"
  (grep -oE '^AGENT_ENGINE_KMS_KEY_[A-Z_]+=projects/[^[:space:]]+' "$APPLY_LOG" 2>/dev/null || true) | while read -r line; do
    if [[ -n "$line" ]]; then
      key="${line%%=*}"
      grep -q "^${key}=" "$VERSIONS_FILE" 2>/dev/null || echo "$line" >>"$VERSIONS_FILE"
    fi
  done
else
  echo "SKIP_INFRA_CMEK=1 — ensure versions.env has org CMEK keys" | tee -a "$APPLY_LOG"
fi

# 06–07 IAM + Firestore
run_range 06 07

# 08 Telemetry
if [[ "${RUN_TELEMETRY:-0}" == "1" ]]; then
  RUN_TELEMETRY=1 run_range 08 08
fi

# 09 Artifact Registry
run_range 09 09

# 10 Events KB
if [[ "${RUN_SETUP_KB:-0}" == "1" ]]; then
  RUN_SETUP_KB=1 run_range 10 10
  echo "Set VERTEX_SEARCH_DATA_STORE_ID in .env from setup_kb output" | tee -a "$APPLY_LOG"
fi

# 11 ADK patch, 13–14 RAG (skip 12 if configured)
run_range 11 11
if [[ "${SKIP_INFRA_VPC_SC:-1}" != "1" ]]; then
  export VPC_SC_ALLOWED_USER_EMAIL="${VPC_SC_ALLOWED_USER_EMAIL:-}"
  export VPC_SC_ALLOWED_MEMBERS="${VPC_SC_ALLOWED_MEMBERS:-}"
  run_range 12 12
else
  echo "SKIP_INFRA_VPC_SC=1 — use org perimeter; see artifacts/vpc-sc-ingress.md" | tee -a "$APPLY_LOG"
fi
run_range 13 14

echo ""
echo "Phase 1 log: $APPLY_LOG"
echo "Phase 1 complete. Verify CMEK keys in versions.env before Phase 2."
