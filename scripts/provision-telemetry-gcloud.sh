#!/usr/bin/env bash
set -euo pipefail

# This script provisions the BigQuery dataset and table for Agent Gateway telemetry

GCP_PROJECT_ID="${GCP_PROJECT_ID:-$PROJECT_ID}"
REGION="${REGION:-us-central1}"

echo "Ensuring BigQuery Dataset prism_telemetry exists in ${GCP_PROJECT_ID}..."
bq --location="${REGION}" mk -d --description "Telemetry Dataset" "${GCP_PROJECT_ID}:prism_telemetry" || true

echo "Ensuring BigQuery Table prism_telemetry.demo_usage_logs exists in ${GCP_PROJECT_ID}..."
bq mk -t --description "Demo Usage Logs" "${GCP_PROJECT_ID}:prism_telemetry.demo_usage_logs" \
  timestamp:TIMESTAMP,usage_type:STRING,user_email:STRING,customer_name:STRING,opportunity_link:STRING || true

echo "Telemetry provisioning complete."
