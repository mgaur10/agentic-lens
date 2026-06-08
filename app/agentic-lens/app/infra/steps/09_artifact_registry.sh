#!/usr/bin/env bash
# Step 09: Create Artifact Registry repository for Glass UI image (prism-glass-ui).
# deploy-glass-ui.sh and cloudbuild_glass_ui.yaml use us-west1.
set -euo pipefail

ROOT_DIR="${ROOT_DIR:?}"
source "$ROOT_DIR/versions.env"

AR_REGION="${AR_REGION:-us-west1}"
REPO="prism-glass-ui"

if gcloud artifacts repositories describe "$REPO" --location="$AR_REGION" --project="$PROJECT_ID" &>/dev/null; then
  echo "Artifact Registry repository $REPO already exists in $AR_REGION."
else
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker \
    --location="$AR_REGION" \
    --project="$PROJECT_ID"
  echo "Created Artifact Registry repository $REPO in $AR_REGION."
fi
echo "Artifact Registry step done."
