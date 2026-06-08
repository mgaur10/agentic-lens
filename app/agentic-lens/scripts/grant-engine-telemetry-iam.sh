#!/usr/bin/env bash
# Grant telemetry/trace/logging roles to the Reasoning Engine service agent.
# Referenced in DEPLOY_GUIDE; included here for greenfield projects.
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
require_gcloud_project

PN=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SA_EMAIL="service-${PN}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

echo "Enabling telemetry-related APIs..."
gcloud services enable \
  telemetry.googleapis.com \
  cloudtrace.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  --project="$PROJECT_ID" 2>/dev/null || true

for role in roles/cloudtrace.agent roles/monitoring.metricWriter roles/logging.logWriter roles/serviceusage.serviceUsageConsumer; do
  echo "Binding $role → $SA_EMAIL"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$role" \
    --quiet 2>/dev/null || true
done

echo "Done. Reasoning Engine SA: $SA_EMAIL"
