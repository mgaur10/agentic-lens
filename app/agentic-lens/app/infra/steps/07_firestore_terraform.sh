#!/usr/bin/env bash
# Step 07: Firestore Terraform (X-Ray knowledge base).
# If state tracks resources from a different project, refresh can fail with 403; remove from state and re-apply.
set -euo pipefail
ROOT_DIR="${ROOT_DIR:?}"
AGENTIC_LENS="${AGENTIC_LENS:?}"
source "$ROOT_DIR/versions.env"
cd "$AGENTIC_LENS/security/db"
terraform init -input=false

APPLY_OUT=$(mktemp)
trap 'rm -f "$APPLY_OUT"' EXIT
if ! terraform apply -var="project_id=$PROJECT_ID" -var="region=$REGION" -auto-approve -input=false 2>&1 | tee "$APPLY_OUT"; then
  if grep -q "already exists\|Error 409" "$APPLY_OUT" 2>/dev/null; then
    echo "Firestore database already exists in GCP; importing into state..."
    terraform import -var="project_id=$PROJECT_ID" -var="region=$REGION" -input=false \
      google_project_service.firestore "$PROJECT_ID/firestore.googleapis.com" 2>/dev/null || true
    terraform import -var="project_id=$PROJECT_ID" -var="region=$REGION" -input=false \
      google_firestore_database.default "projects/$PROJECT_ID/databases/(default)" 2>/dev/null || true
    # Only re-apply if plan would not replace the database (avoid destroy+recreate when DB exists in another region)
    if terraform plan -var="project_id=$PROJECT_ID" -var="region=$REGION" -input=false -no-color 2>/dev/null | grep -q "must be replaced\|forces replacement"; then
      echo "Existing Firestore database is in a different region; keeping current state (no replace)."
    else
      terraform apply -var="project_id=$PROJECT_ID" -var="region=$REGION" -auto-approve -input=false
    fi
  elif terraform state list 2>/dev/null | grep -q "google_firestore_database.default"; then
    echo "Removing stale state (different project), then re-applying..."
    terraform state rm google_firestore_database.default 2>/dev/null || true
    terraform state rm google_project_service.firestore 2>/dev/null || true
    terraform apply -var="project_id=$PROJECT_ID" -var="region=$REGION" -auto-approve -input=false
  else
    exit 1
  fi
fi
echo "Firestore Terraform step done."
