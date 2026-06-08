#!/usr/bin/env bash
# Deploy Model Armor policies and SDP (DLP) config so they appear in the GCP console.
# 1. Enable Model Armor + DLP APIs
# 2. Create DLP inspect/deidentify templates (required for SDP advanced)
# 3. Terraform: create security-medium + security-high Model Armor templates
# 4. Update templates: logging + SDP advanced config (DLP templates)
#
# Usage: ./deploy_model_armor.sh   (from repo root; uses versions.env)
# Prereq: Python with google-cloud-dlp and google-cloud-modelarmor (e.g. agentic-lens/.venv: pip install -r agentic-lens/requirements.txt).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
AGENTIC_LENS="$ROOT_DIR/agentic-lens"
POLICIES_DIR="$AGENTIC_LENS/security/policies"

# ---------------------------------------------------------------------------
# 1. Load config (versions.env; for .env use: export $(grep -v '^#' .env | xargs) before running)
# ---------------------------------------------------------------------------
if [[ -f "$ROOT_DIR/versions.env" ]]; then
  # shellcheck source=versions.env
  source "$ROOT_DIR/versions.env"
fi

PROJECT_ID="${PROJECT_ID:-${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT}}}"
REGION="${REGION:-${GCP_LOCATION:-us-west1}}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: PROJECT_ID not set. Set in versions.env, .env, or env (GCP_PROJECT_ID / GOOGLE_CLOUD_PROJECT)."
  exit 1
fi

# Model Armor is only available in a subset of regions (e.g. us-central1, us-east4, us-west1).
# Use a fallback when REGION is not supported (e.g. us-east5 -> us-east4; northamerica-northeast2 -> us-west1).
MA_REGION="$REGION"
case "$REGION" in
  us-east5) MA_REGION="us-east4" ;;
  northamerica-northeast1|northamerica-northeast2|europe-*|asia-*|australia-*|southamerica-*)
    MA_REGION="us-west1"
    ;;
esac

echo "========== Model Armor + SDP deployment =========="
echo "PROJECT_ID=$PROJECT_ID  REGION=$REGION  MODEL_ARMOR_REGION=$MA_REGION"
echo ""

# ---------------------------------------------------------------------------
# 2. Enable APIs
# ---------------------------------------------------------------------------
echo "--- Enabling Model Armor and DLP APIs ---"
gcloud services enable modelarmor.googleapis.com dlp.googleapis.com --project="$PROJECT_ID"

# ---------------------------------------------------------------------------
# 3. Create DLP templates (inspect + deidentify) in Model Armor region
# Both use the same INFO_TYPES so they stay in sync; no separate sync script needed.
# ---------------------------------------------------------------------------
echo ""
echo "--- Creating DLP templates (required for SDP advanced) ---"
# Prefer root .venv (has google-cloud-dlp); else agentic-lens .venv; else system python3
PYTHON=""
[[ -x "$ROOT_DIR/.venv/bin/python3" ]] && PYTHON="$ROOT_DIR/.venv/bin/python3"
[[ -z "$PYTHON" && -x "$ROOT_DIR/agentic-lens/.venv/bin/python3" ]] && PYTHON="$ROOT_DIR/agentic-lens/.venv/bin/python3"
[[ -z "$PYTHON" ]] && PYTHON="python3"
"$PYTHON" "$ROOT_DIR/create_dlp_templates.py" "$PROJECT_ID" "$MA_REGION"

# ---------------------------------------------------------------------------
# 4. Terraform: create Model Armor templates (security-medium, security-high)
# ---------------------------------------------------------------------------
echo ""
echo "--- Terraform: Model Armor templates ---"
cd "$POLICIES_DIR"
terraform init -input=false
terraform apply \
  -var="project_id=$PROJECT_ID" \
  -var="region=$REGION" \
  -var="model_armor_region=$MA_REGION" \
  -auto-approve -input=false

# ---------------------------------------------------------------------------
# 5. Update Model Armor templates: logging + SDP advanced (DLP) config
# ---------------------------------------------------------------------------
echo ""
if [[ -f "$ROOT_DIR/update_model_armor_templates.py" ]]; then
  echo "--- Updating templates (logging + SDP advanced) ---"
  GCP_PROJECT_ID="$PROJECT_ID" GCP_LOCATION="$MA_REGION" "$PYTHON" "$ROOT_DIR/update_model_armor_templates.py" "$PROJECT_ID" "$MA_REGION"
else
  echo "--- Skipping template update (update_model_armor_templates.py not found); security-medium/high already created. ---"
fi

echo ""
echo "========== Deployment complete =========="
echo "Model Armor templates (console):"
echo "  https://console.cloud.google.com/ai/model-armor?project=$PROJECT_ID"
echo "  Region: $MA_REGION  →  security-medium, security-high"
echo "DLP templates (console):"
echo "  https://console.cloud.google.com/security/dlp?project=$PROJECT_ID"
echo "  Location: $MA_REGION  →  identification-template, deidentify-replace-with-infotype"
