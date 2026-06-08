#!/usr/bin/env bash
# Step 10 (optional): Discovery Engine data store for Events (Vertex AI Search).
# Run when RUN_SETUP_KB=1. Creates data store and target site; output DATA_STORE_ID for .env.
# Expects: PROJECT_ID, REGION, ROOT_DIR from apply.sh.
set -euo pipefail

ROOT_DIR="${ROOT_DIR:?}"
# shellcheck source=../../versions.env
source "$ROOT_DIR/versions.env"

PYTHON=""
[[ -x "$ROOT_DIR/agentic-lens/.venv/bin/python3" ]] && PYTHON="$ROOT_DIR/agentic-lens/.venv/bin/python3"
[[ -z "$PYTHON" ]] && PYTHON="python3"

GCP_PROJECT_ID="$PROJECT_ID" GCP_LOCATION="$REGION" "$PYTHON" "$ROOT_DIR/backend/setup_kb.py" || true
echo "Add VERTEX_SEARCH_DATA_STORE_ID (and optionally VERTEX_SEARCH_ENGINE_ID) to .env from the script output above."
echo "Setup KB step done."
