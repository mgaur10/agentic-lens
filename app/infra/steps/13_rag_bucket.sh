#!/usr/bin/env bash
# Step 13: Create GCS bucket for user uploads (empty at start).
#
# Creates:
#   gs://vertex-rag-ingest-${PROJECT_ID}/incoming/
#
set -euo pipefail
ROOT_DIR="${ROOT_DIR:?}"
AGENTIC_LENS="${AGENTIC_LENS:?}"

source "$ROOT_DIR/versions.env"

BUCKET_NAME="${VERTEX_RAG_INGEST_BUCKET_NAME:-vertex-rag-ingest-${PROJECT_ID}}"
BUCKET_LOCATION="${VERTEX_RAG_BUCKET_LOCATION:-$REGION}"

cd "$AGENTIC_LENS/security/rag_ingest_bucket"
terraform init -input=false
terraform apply \
  -var="project_id=$PROJECT_ID" \
  -var="region=$REGION" \
  -var="bucket_name=$BUCKET_NAME" \
  -var="bucket_location=$BUCKET_LOCATION" \
  -auto-approve -input=false

echo "RAG ingest bucket created: gs://${BUCKET_NAME}"

# Optional: set defaults in .env so the user can upload and then run ingestion later.
ENV_PATH="$ROOT_DIR/.env"
if [[ -f "$ENV_PATH" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  [[ ! -x "$PYTHON_BIN" ]] && PYTHON_BIN="python3"

  "$PYTHON_BIN" "$ROOT_DIR/scripts/update_env.py" "VERTEX_RAG_PROJECT_ID" "$PROJECT_ID" "$ENV_PATH"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/update_env.py" "VERTEX_RAG_LOCATION" "$BUCKET_LOCATION" "$ENV_PATH"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/update_env.py" "VERTEX_RAG_GCS_PATH" "gs://${BUCKET_NAME}/incoming/" "$ENV_PATH"
fi

