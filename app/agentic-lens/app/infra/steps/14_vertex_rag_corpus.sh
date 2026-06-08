#!/usr/bin/env bash
# Step 14: Create an empty Managed Vertex AI RAG corpus.
#
# The Events concierge will retrieve from this RagCorpus.
#
set -euo pipefail
ROOT_DIR="${ROOT_DIR:?}"
AGENTIC_LENS="${AGENTIC_LENS:?}"

source "$ROOT_DIR/versions.env"

RAG_CORPUS_ID="${VERTEX_RAG_CORPUS_ID:-events-rag}"
RAG_DISPLAY_NAME="${VERTEX_RAG_DISPLAY_NAME:-agentic-lens-events-rag}"
RAG_DESCRIPTION="${VERTEX_RAG_DESCRIPTION:-Managed RAG corpus for Concierge Events}"
RAG_LOCATION="${VERTEX_RAG_LOCATION:-$REGION}"

PYTHON_BIN="$AGENTIC_LENS/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

cd "$AGENTIC_LENS/security/rag_corpus"
terraform init -input=false
terraform apply \
  -var="project_id=$PROJECT_ID" \
  -var="location=$RAG_LOCATION" \
  -var="corpus_id=$RAG_CORPUS_ID" \
  -var="display_name=$RAG_DISPLAY_NAME" \
  -var="description=$RAG_DESCRIPTION" \
  -var="python_bin=$PYTHON_BIN" \
  -var="setup_script_path=$ROOT_DIR/backend/setup_vertex_rag_corpus.py" \
  -auto-approve -input=false

# Resolve actual corpus resource name by display_name, because Vertex RAG may
# assign a numeric corpus ID instead of using the requested logical ID.
ACTUAL_CORPUS_NAME=$("$PYTHON_BIN" - <<PY
import vertexai
from vertexai.preview import rag

project_id = "${PROJECT_ID}"
location = "${RAG_LOCATION}"
display_name = "${RAG_DISPLAY_NAME}"

vertexai.init(project=project_id, location=location)
matches = [c for c in rag.list_corpora() if (getattr(c, "display_name", "") or "") == display_name]
if matches:
    print(matches[0].name or "")
else:
    print("")
PY
)

if [[ -n "$ACTUAL_CORPUS_NAME" ]]; then
  echo "RAG corpus created/initialized: ${ACTUAL_CORPUS_NAME}"
else
  echo "RAG corpus created/initialized: projects/${PROJECT_ID}/locations/${RAG_LOCATION}/ragCorpora/${RAG_CORPUS_ID}"
fi

ENV_PATH="$ROOT_DIR/.env"
if [[ -f "$ENV_PATH" ]]; then
  "$PYTHON_BIN" "$ROOT_DIR/scripts/update_env.py" "VERTEX_RAG_PROJECT_ID" "$PROJECT_ID" "$ENV_PATH"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/update_env.py" "VERTEX_RAG_LOCATION" "$RAG_LOCATION" "$ENV_PATH"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/update_env.py" "VERTEX_RAG_CORPUS_ID" "$RAG_CORPUS_ID" "$ENV_PATH"
  if [[ -n "$ACTUAL_CORPUS_NAME" ]]; then
    "$PYTHON_BIN" "$ROOT_DIR/scripts/update_env.py" "VERTEX_RAG_CORPUS_NAME" "$ACTUAL_CORPUS_NAME" "$ENV_PATH"
  fi
  "$PYTHON_BIN" "$ROOT_DIR/scripts/update_env.py" "VERTEX_RAG_DISPLAY_NAME" "$RAG_DISPLAY_NAME" "$ENV_PATH"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/update_env.py" "VERTEX_RAG_DESCRIPTION" "$RAG_DESCRIPTION" "$ENV_PATH"
fi

