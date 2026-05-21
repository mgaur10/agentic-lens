#!/usr/bin/env bash
# Agentic-Prism partial infrastructure (APIs, bootstrap, X-Ray secret/IAM, Model Armor, CMEK).
# For full infra including IAM Terraform, Firestore, Artifact Registry, use: ./infra/apply.sh
# Usage: ./setup_infra.sh   (from repo root)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
AGENTIC_LENS="$ROOT_DIR/agentic-lens"
SECURITY_DIR="$AGENTIC_LENS/security"
POLICIES_DIR="$SECURITY_DIR/policies"

# ---------------------------------------------------------------------------
# 1. Load Config
# ---------------------------------------------------------------------------
if [[ ! -f "$ROOT_DIR/versions.env" ]]; then
  echo "ERROR: versions.env not found at $ROOT_DIR/versions.env"
  exit 1
fi
# shellcheck source=versions.env
source "$ROOT_DIR/versions.env"

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: PROJECT_ID not set in versions.env"
  exit 1
fi
if [[ -z "$REGION" ]]; then
  echo "ERROR: REGION not set in versions.env"
  exit 1
fi

echo "Using PROJECT_ID=$PROJECT_ID REGION=$REGION"

# ---------------------------------------------------------------------------
# 2. Enable APIs
# ---------------------------------------------------------------------------
echo "Enabling required APIs..."
gcloud services enable \
  aiplatform.googleapis.com \
  cloudkms.googleapis.com \
  discoveryengine.googleapis.com \
  modelarmor.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  --project="$PROJECT_ID"

# ---------------------------------------------------------------------------
# 3. Bootstrap Agent Engine (creates Workload Identity Pool for Agent Identity)
# ---------------------------------------------------------------------------
echo "Bootstrapping Agent Engine (Workload Identity Pool creation)..."
gcloud beta ai agent-engines create \
  --region="$REGION" \
  --display-name="bootstrap-init" \
  --project="$PROJECT_ID" \
  --quiet 2>/dev/null || echo "Agent Engine likely already exists or beta not installed, proceeding..."

# ---------------------------------------------------------------------------
# 3b. X-Ray Department — Create 5 identities (agent engines / placeholders)
# ---------------------------------------------------------------------------
XRAY_IDENTITIES=(xray_manager xray_librarian xray_architect xray_specialist xray_auditor)
echo "Initializing X-Ray Department identities..."
for name in "${XRAY_IDENTITIES[@]}"; do
  gcloud beta ai agent-engines create \
    --region="$REGION" \
    --display-name="$name" \
    --project="$PROJECT_ID" \
    --quiet 2>/dev/null || echo "  X-Ray identity $name already exists or skipped, proceeding..."
done

# ---------------------------------------------------------------------------
# 3c. X-Ray — Optional PAT secret (github-pat-token); public GitHub repos need no PAT
# ---------------------------------------------------------------------------
if ! gcloud secrets describe github-pat-token --project="$PROJECT_ID" &>/dev/null; then
  echo "Secret github-pat-token not found. Optional for public repos; use a PAT for private repos or API rate limits."
  read -s -p "Enter GitHub PAT (or Enter to skip): " GITHUB_PAT
  echo
  if [[ -n "$GITHUB_PAT" ]]; then
    echo -n "$GITHUB_PAT" | gcloud secrets create github-pat-token \
      --replication-policy="user-managed" \
      --locations="$REGION" \
      --data-file=- \
      --project="$PROJECT_ID"
    echo "Secret github-pat-token created."
  else
    echo "Skipping github-pat-token. Librarian can use unauthenticated GitHub API for public repositories."
  fi
else
  echo "Secret github-pat-token already exists."
fi

# Resolve ORG_ID for X-Ray IAM principals (optional in versions.env; else from project parent)
ORG_ID="${ORG_ID:-}"
if [[ -z "$ORG_ID" ]]; then
  ORG_ID=$(gcloud projects describe "$PROJECT_ID" --format='value(parent)' 2>/dev/null | sed -n 's|^organizations/||p' || true)
fi
if [[ -n "$ORG_ID" ]]; then
  XRAY_LIBRARIAN_PRINCIPAL="principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/projects/${PROJECT_ID}/locations/${REGION}/agents/agentic_lens_xray_librarian"
  # Grant secretAccessor on github-pat-token ONLY to xray_librarian
  if gcloud secrets describe github-pat-token --project="$PROJECT_ID" &>/dev/null; then
    echo "Granting roles/secretmanager.secretAccessor on github-pat-token to xray_librarian..."
    gcloud secrets add-iam-policy-binding github-pat-token \
      --member="${XRAY_LIBRARIAN_PRINCIPAL}" \
      --role="roles/secretmanager.secretAccessor" \
      --project="$PROJECT_ID" \
      --quiet 2>/dev/null || echo "  Binding may already exist or principal not yet active."
  fi
  # Audit logging: roles/logging.logWriter for all 5 X-Ray identities
  echo "Granting roles/logging.logWriter to all X-Ray identities..."
  for name in "${XRAY_IDENTITIES[@]}"; do
    principal="principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/projects/${PROJECT_ID}/locations/${REGION}/agents/agentic_lens_${name}"
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="${principal}" \
      --role="roles/logging.logWriter" \
      --quiet 2>/dev/null || echo "  Binding for $name may already exist or principal not yet active."
  done
else
  echo "WARNING: ORG_ID not set (add to versions.env or use an organization project). Skipping X-Ray IAM bindings (secretAccessor, logging.logWriter)."
fi

# ---------------------------------------------------------------------------
# 4. Terraform Apply
# ---------------------------------------------------------------------------
# 4a. Model Armor (security/policies)
# Model Armor API is not in us-east5; use us-east4 for templates when REGION=us-east5.
MA_REGION="$REGION"
[[ "$REGION" == "us-east5" ]] && MA_REGION="us-east4"
echo "--- Terraform: Model Armor (security/policies) [region=$REGION, model_armor_region=$MA_REGION] ---"
cd "$POLICIES_DIR"
terraform init
terraform apply \
  -var="project_id=$PROJECT_ID" \
  -var="region=$REGION" \
  -var="model_armor_region=$MA_REGION" \
  -auto-approve

# 4b. CMEK (security/ — kms.tf)
# Vertex AI service agent may not exist until API is used; wait then retry.
echo "--- Terraform: CMEK (security/) ---"
cd "$SECURITY_DIR"
terraform init
for attempt in 1 2 3; do
  if terraform apply \
    -var="project_id=$PROJECT_ID" \
    -var="region=$REGION" \
    -auto-approve; then
    break
  fi
  if [[ $attempt -lt 3 ]]; then
    echo "Vertex AI service agent may still be provisioning. Waiting 45s before retry..."
    sleep 45
  fi
done

# ---------------------------------------------------------------------------
# 5. Output — kms_key_id and model_armor_template_id(s)
# ---------------------------------------------------------------------------
echo ""
echo "========== Fortress Verification =========="

echo "model_armor_template_id (medium):"
(cd "$POLICIES_DIR" && terraform output medium_template_id 2>/dev/null) || true
echo "model_armor_template_id (high):"
(cd "$POLICIES_DIR" && terraform output high_template_id 2>/dev/null) || true

echo "kms_key_id:"
(cd "$SECURITY_DIR" && terraform output kms_key_id 2>/dev/null) || true

echo ""
echo "========== Setup complete. =========="
