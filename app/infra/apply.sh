#!/usr/bin/env bash
# Agentic-Prism consolidated infrastructure: one script to run all infra steps.
# Usage: ./infra/apply.sh [step_from [step_to]]
#   With no args: runs steps 01–12 (telemetry and setup_kb optional via env).
#   With args: run only steps from step_from to step_to (e.g. ./infra/apply.sh 03 05).
# Optional env: RUN_TELEMETRY=1 (include step 08), RUN_SETUP_KB=1 (include step 10).
# Step 05: per-department CMEK. Step 11: ADK patch (if .venv exists). Step 12: VPC-SC perimeter (set VPC_SC_ALLOWED_USER_EMAIL or VPC_SC_ALLOWED_MEMBERS).
# Prereq: Create GCP project, copy versions.env from env.example or set PROJECT_ID and REGION.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
STEPS_DIR="$SCRIPT_DIR/steps"

if [[ ! -f "$ROOT_DIR/versions.env" ]]; then
  echo "ERROR: versions.env not found at $ROOT_DIR/versions.env"
  exit 1
fi
# shellcheck source=../versions.env
source "$ROOT_DIR/versions.env"

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "ERROR: PROJECT_ID not set in versions.env"
  exit 1
fi
if [[ -z "${REGION:-}" ]]; then
  echo "ERROR: REGION not set in versions.env"
  exit 1
fi

# Resolve ORG_ID for IAM Terraform (step 06)
export ORG_ID="${ORG_ID:-}"
if [[ -z "$ORG_ID" ]]; then
  ORG_ID=$(gcloud projects describe "$PROJECT_ID" --format='value(parent)' 2>/dev/null | sed -n 's|^organizations/||p' || true)
fi
export ORG_ID

export ROOT_DIR
export AGENTIC_LENS="${ROOT_DIR}/agentic-lens"

FROM="${1:-01}"
# Include vertex-rag bucket + corpus steps.
TO="${2:-14}"

# Optional: include telemetry (08) and setup_kb (10). Step 10 runs only if RUN_SETUP_KB=1.
# Step 09 is Artifact Registry (always run if in range).
run_step() {
  local n="$1"
  local name="$2"
  local script="$STEPS_DIR/${n}_${name}.sh"
  if [[ ! -f "$script" ]]; then
    echo "Step $n: script not found $script"
    return 1
  fi
  echo ""
  echo "========== Step $n: $name =========="
  bash "$script"
}

# Step number to integer (01 -> 1, 10 -> 10)
step_num() { echo "$((10#$1))"; }
step_in_range() {
  local s="$1"
  local sn; sn=$(step_num "$s")
  local fn; fn=$(step_num "$FROM")
  local tn; tn=$(step_num "$TO")
  [[ $sn -ge $fn && $sn -le $tn ]] && return 0
  return 1
}

echo "Infra apply: PROJECT_ID=$PROJECT_ID REGION=$REGION ORG_ID=${ORG_ID:-<not set>}"
echo "Steps: $FROM -> $TO (RUN_TELEMETRY=${RUN_TELEMETRY:-0}, RUN_SETUP_KB=${RUN_SETUP_KB:-0})"

for step in 01_enable_apis 02_bootstrap_agent_engine 03_secrets_xray_iam 04_model_armor 05_cmek 06_iam_terraform 07_firestore_terraform 08_telemetry 09_artifact_registry 10_setup_kb 11_patch_adk 12_vpc_sc 13_rag_bucket 14_vertex_rag_corpus; do
  num="${step%%_*}"
  name="${step#*_}"
  if ! step_in_range "$num"; then
    continue
  fi
  if [[ "$num" == "08" && "${RUN_TELEMETRY:-0}" != "1" ]]; then
    echo "Skipping step 08 (telemetry); set RUN_TELEMETRY=1 to include."
    continue
  fi
  if [[ "$num" == "10" && "${RUN_SETUP_KB:-0}" != "1" ]]; then
    echo "Skipping step 10 (setup_kb); set RUN_SETUP_KB=1 to include."
    continue
  fi
  run_step "$num" "$name" || exit $?
done

echo ""
echo "========== Infra apply complete =========="
echo "If step 05 ran: add the AGENT_ENGINE_KMS_KEY_* lines to versions.env (see output above)."
echo "Next: ./deploy.sh (agents), then ./deploy-glass-ui.sh (Glass UI)."
echo "If you ran step 10 (setup_kb), add VERTEX_SEARCH_DATA_STORE_ID to .env for the UI."
echo "After first deploy (if needed): ./scripts/grant_service_usage_to_engines.sh"
echo "Step 12 (VPC-SC): set VPC_SC_ALLOWED_USER_EMAIL or VPC_SC_ALLOWED_MEMBERS for allowed ingress/egress identity."
