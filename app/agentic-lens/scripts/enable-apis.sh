#!/bin/bash
# Enable all Google Cloud APIs required for Agentic-Prism (new project setup).
# Usage: ./enable-apis.sh [PROJECT_ID]
#   PROJECT_ID defaults to env GOOGLE_CLOUD_PROJECT or GCP_PROJECT_ID, or "agentic-prismv333".

set -e

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:-${GCP_PROJECT_ID:-agentic-prismv333}}}"

echo "=============================================="
echo "Agentic-Prism — Enabling required APIs"
echo "Project: $PROJECT_ID"
echo "=============================================="
echo ""

# Required for Agentic-Prism: Vertex AI Agent Engine, Model Armor, Discovery Engine, IAM, etc.
APIS=(
  aiplatform.googleapis.com
  telemetry.googleapis.com
  modelarmor.googleapis.com
  dlp.googleapis.com
  discoveryengine.googleapis.com
  cloudresourcemanager.googleapis.com
  cloudasset.googleapis.com
  iam.googleapis.com
  storage.googleapis.com
  compute.googleapis.com
)

for api in "${APIS[@]}"; do
  echo "Enabling $api..."
  if gcloud services enable "$api" --project="$PROJECT_ID" 2>/dev/null; then
    echo "  OK"
  else
    echo "  (may already be enabled or failed — check Console)"
  fi
done

echo ""
echo "=============================================="
echo "Done. Enabled ${#APIS[@]} APIs for project: $PROJECT_ID"
echo ""
echo "Next steps:"
echo "  1. Apply Model Armor Terraform: cd security/policies && terraform apply -var=\"project_id=$PROJECT_ID\" -var=\"region=us-central1\" -auto-approve"
echo "  2. Apply IAM Terraform: cd security/iam && terraform apply -var=\"project_id=$PROJECT_ID\" -var=\"org_id=YOUR_ORG_ID\" -var=\"region=us-central1\" -auto-approve"
echo "=============================================="
