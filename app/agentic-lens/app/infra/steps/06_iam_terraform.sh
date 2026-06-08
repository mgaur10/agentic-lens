#!/usr/bin/env bash
# Step 06: IAM Terraform (agent identities + Artifact Registry/Cloud Build for Glass UI).
# Per-agent IAM: set ORG_ID in versions.env to your Google Cloud organization ID (numeric). Each agent
# then gets its own bindings (agents.global.org-ORG_ID). Without ORG_ID, no agent IAM is created
# (project-level principalSet is off by default; enable via -var="use_project_level_principal_set=true" if needed).
set -euo pipefail
ROOT_DIR="${ROOT_DIR:?}"
AGENTIC_LENS="${AGENTIC_LENS:?}"
source "$ROOT_DIR/versions.env"
cd "$AGENTIC_LENS/security/iam"
terraform init -input=false
terraform apply \
  -var="project_id=$PROJECT_ID" \
  -var="org_id=${ORG_ID:-}" \
  -var="region=$REGION" \
  -var="github_pat_secret_name=${GITHUB_PAT_SECRET_NAME:-}" \
  -var="use_project_level_principal_set=${USE_PROJECT_LEVEL_PRINCIPAL_SET:-false}" \
  -auto-approve -input=false
echo "IAM Terraform step done."
