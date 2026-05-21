#!/usr/bin/env bash
# Step 01: Enable required GCP APIs.
# Expects: PROJECT_ID, REGION (from apply.sh / versions.env).
set -euo pipefail

ROOT_DIR="${ROOT_DIR:?}"
source "$ROOT_DIR/versions.env"

gcloud services enable \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  cloudkms.googleapis.com \
  discoveryengine.googleapis.com \
  modelarmor.googleapis.com \
  dlp.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  firestore.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  bigquery.googleapis.com \
  accesscontextmanager.googleapis.com \
  --project="${PROJECT_ID}"

echo "APIs enabled."
