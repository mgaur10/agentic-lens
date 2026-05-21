#!/usr/bin/env bash
# Step 02: Bootstrap Agent Engine (Workload Identity Pool) and X-Ray department identities.
set -euo pipefail

ROOT_DIR="${ROOT_DIR:?}"
source "$ROOT_DIR/versions.env"

echo "Bootstrapping Agent Engine (Workload Identity Pool)..."
gcloud beta ai agent-engines create \
  --region="$REGION" \
  --display-name="bootstrap-init" \
  --project="$PROJECT_ID" \
  --quiet 2>/dev/null || echo "Agent Engine likely already exists or beta not installed, proceeding..."

XRAY_IDENTITIES=(xray_manager xray_librarian xray_architect xray_specialist xray_auditor)
echo "Initializing X-Ray Department identities..."
for name in "${XRAY_IDENTITIES[@]}"; do
  gcloud beta ai agent-engines create \
    --region="$REGION" \
    --display-name="$name" \
    --project="$PROJECT_ID" \
    --quiet 2>/dev/null || echo "  X-Ray identity $name already exists or skipped, proceeding..."
done
echo "Bootstrap and X-Ray identities done."
