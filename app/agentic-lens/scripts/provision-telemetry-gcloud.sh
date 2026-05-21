#!/usr/bin/env bash
# Provision telemetry infrastructure via gcloud: BigQuery dataset + table + IAM for Cloud Run.
# Usage:
#   PROJECT_ID=agentic-prismv333 REGION=us-west1 CLOUD_RUN_SA="123456789-compute@developer.gserviceaccount.com" ./provision-telemetry-gcloud.sh
# Or for a custom SA: CLOUD_RUN_SA=my-app@agentic-prismv333.iam.gserviceaccount.com

set -e
PROJECT_ID="${GCP_PROJECT_ID:-$PROJECT_ID}"
REGION="${REGION:-us-west1}"
# Cloud Run uses default compute SA unless you set a custom one. Format: NUMBER-compute@developer.gserviceaccount.com
CLOUD_RUN_SA="${CLOUD_RUN_SA:-}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "Set GCP_PROJECT_ID or PROJECT_ID"
  exit 1
fi
if [[ -z "$CLOUD_RUN_SA" ]]; then
  # Resolve default compute service account
  PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
  CLOUD_RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  echo "Using default compute SA: $CLOUD_RUN_SA"
fi

echo "Project: $PROJECT_ID Region: $REGION Cloud Run SA: $CLOUD_RUN_SA"

# 1. BigQuery dataset
bq --project_id="$PROJECT_ID" mk \
  --dataset \
  --location="$REGION" \
  --description="Application telemetry for Prism" \
  "${PROJECT_ID}:prism_telemetry" || true

# 2. Table with exact schema (REQUIRED: timestamp, usage_type, user_email; NULLABLE: customer_name, opportunity_link)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="${SCRIPT_DIR}/../telemetry/demo_usage_logs_schema.json"
if [[ -f "$SCHEMA_FILE" ]]; then
  bq --project_id="$PROJECT_ID" mk --table \
    "${PROJECT_ID}:prism_telemetry.demo_usage_logs" \
    "$SCHEMA_FILE" || true
else
  bq --project_id="$PROJECT_ID" mk --table \
    "${PROJECT_ID}:prism_telemetry.demo_usage_logs" \
    "timestamp:TIMESTAMP,usage_type:STRING,user_email:STRING,customer_name:STRING,opportunity_link:STRING" || true
fi

# 3. IAM: grant roles/bigquery.dataEditor to Cloud Run service account
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUD_RUN_SA}" \
  --role="roles/bigquery.dataEditor"

echo "Done. Dataset prism_telemetry and table demo_usage_logs are ready; $CLOUD_RUN_SA has roles/bigquery.dataEditor."
