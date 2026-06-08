#!/usr/bin/env bash
# Step 08 (optional): Telemetry. Run when RUN_TELEMETRY=1.
set -euo pipefail
ROOT_DIR="${ROOT_DIR:?}"
AGENTIC_LENS="${AGENTIC_LENS:?}"
source "$ROOT_DIR/versions.env"
GCP_PROJECT_ID="$PROJECT_ID" REGION="$REGION" "$AGENTIC_LENS/scripts/provision-telemetry-gcloud.sh"
echo "Telemetry step done."
