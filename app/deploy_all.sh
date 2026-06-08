#!/usr/bin/env bash
# Agentic-Prism: one-shot deploy. Set PROJECT_ID, REGION, MODEL_VERSION in versions.env and run.
# Creates venvs if missing, runs infra, deploys agents, writes Supervisor engine to .env. No manual steps.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
ENV_FILE="$ROOT_DIR/.env"
VERSIONS_FILE="$ROOT_DIR/versions.env"

# ---------------------------------------------------------------------------
# 1. Prereq: versions.env with PROJECT_ID, REGION, MODEL_VERSION
# ---------------------------------------------------------------------------
if [[ ! -f "$VERSIONS_FILE" ]]; then
  echo "ERROR: versions.env not found at $VERSIONS_FILE"
  exit 1
fi
# shellcheck source=versions.env
source "$VERSIONS_FILE"

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "ERROR: PROJECT_ID not set in versions.env"
  exit 1
fi
if [[ -z "${REGION:-}" ]]; then
  echo "ERROR: REGION not set in versions.env"
  exit 1
fi
if [[ -z "${MODEL_VERSION:-}" ]]; then
  echo "ERROR: MODEL_VERSION not set in versions.env"
  exit 1
fi

echo "Deploy all: PROJECT_ID=$PROJECT_ID REGION=$REGION MODEL_VERSION=$MODEL_VERSION"

# ---------------------------------------------------------------------------
# 1b. Ensure root .venv exists with requirements (step 04 needs google-cloud-dlp)
# ---------------------------------------------------------------------------
if [[ ! -x "$ROOT_DIR/.venv/bin/python3" ]]; then
  echo "Creating root .venv and installing requirements (needed for infra step 04 DLP)..."
  python3 -m venv "$ROOT_DIR/.venv"
  "$ROOT_DIR/.venv/bin/pip" install -q -r "$ROOT_DIR/requirements.txt"
fi

# ---------------------------------------------------------------------------
# 1c. Ensure agentic-lens/.venv exists with requirements (deploy.sh needs ADK)
# ---------------------------------------------------------------------------
if [[ ! -x "$ROOT_DIR/agentic-lens/.venv/bin/python3" ]]; then
  echo "Creating agentic-lens/.venv and installing requirements (needed for agent deploy)..."
  python3 -m venv "$ROOT_DIR/agentic-lens/.venv"
  "$ROOT_DIR/agentic-lens/.venv/bin/pip" install -q -r "$ROOT_DIR/agentic-lens/requirements.txt"
fi

# ---------------------------------------------------------------------------
# 2. Ensure .env exists and set GCP_PROJECT_ID, GCP_LOCATION, GCP_PROJECT_NUMBER
# ---------------------------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Creating .env from env.example..."
  cp "$ROOT_DIR/env.example" "$ENV_FILE"
fi

# Prefer root .venv for scripts (update_env, etc.); agent deploy uses agentic-lens/.venv
PYTHON="${ROOT_DIR}/.venv/bin/python"
[[ ! -x "$PYTHON" ]] && PYTHON="python3"

"$PYTHON" "$ROOT_DIR/scripts/update_env.py" "GCP_PROJECT_ID" "$PROJECT_ID" "$ENV_FILE"
"$PYTHON" "$ROOT_DIR/scripts/update_env.py" "GCP_LOCATION" "$REGION" "$ENV_FILE"
GCP_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null || true)
if [[ -n "$GCP_NUM" ]]; then
  "$PYTHON" "$ROOT_DIR/scripts/update_env.py" "GCP_PROJECT_NUMBER" "$GCP_NUM" "$ENV_FILE"
fi

# ---------------------------------------------------------------------------
# 3. Run infra (capture output for CMEK parsing)
# ---------------------------------------------------------------------------
APPLY_LOG=$(mktemp)
trap 'rm -f "$APPLY_LOG"' EXIT
echo "Running infrastructure (infra/apply.sh)..."
if ! "$ROOT_DIR/infra/apply.sh" 2>&1 | tee "$APPLY_LOG"; then
  echo "Infrastructure failed. Check output above."
  exit 1
fi

# ---------------------------------------------------------------------------
# 4. Append CMEK keys to versions.env if step 05 printed them
# ---------------------------------------------------------------------------
while IFS= read -r line; do
  key="${line%%=*}"
  if [[ "$key" =~ ^AGENT_ENGINE_KMS_KEY_ ]] && ! grep -q "^${key}=" "$VERSIONS_FILE" 2>/dev/null; then
    echo "$line" >> "$VERSIONS_FILE"
    echo "Appended to versions.env: $key"
  fi
done < <(grep -oE '^AGENT_ENGINE_KMS_KEY_[A-Z_]+=projects/[^[:space:]]+' "$APPLY_LOG" 2>/dev/null || true)

# ---------------------------------------------------------------------------
# 5. If RUN_SETUP_KB=1, set VERTEX_SEARCH_DATA_STORE_ID in .env
# ---------------------------------------------------------------------------
if [[ "${RUN_SETUP_KB:-0}" == "1" ]]; then
  "$PYTHON" "$ROOT_DIR/scripts/update_env.py" "VERTEX_SEARCH_DATA_STORE_ID" "events-web-knowledge" "$ENV_FILE"
  echo "Set VERTEX_SEARCH_DATA_STORE_ID=events-web-knowledge in .env"
fi

# ---------------------------------------------------------------------------
# 6. Run deploy.sh (agents)
# ---------------------------------------------------------------------------
echo "Deploying agents..."
source "$VERSIONS_FILE"
export ROOT_DIR
if ! "$ROOT_DIR/deploy.sh"; then
  echo "Agent deploy failed. Check output above."
  exit 1
fi

# ---------------------------------------------------------------------------
# 7. Resolve Supervisor engine and write AGENTIC_LENS_SUPERVISOR_ENGINE to .env
# ---------------------------------------------------------------------------
export PROJECT_ID REGION
SUPERVISOR_ENGINE=""
if [[ -x "$ROOT_DIR/agentic-lens/.venv/bin/python" ]]; then
  SUPERVISOR_ENGINE=$("$ROOT_DIR/agentic-lens/.venv/bin/python" "$ROOT_DIR/scripts/get_agent_engine_id.py" supervisor 2>/dev/null || true)
else
  SUPERVISOR_ENGINE=$(python3 "$ROOT_DIR/scripts/get_agent_engine_id.py" supervisor 2>/dev/null || true)
fi
if [[ -n "$SUPERVISOR_ENGINE" ]]; then
  "$PYTHON" "$ROOT_DIR/scripts/update_env.py" "AGENTIC_LENS_SUPERVISOR_ENGINE" "$SUPERVISOR_ENGINE" "$ENV_FILE"
  echo "Set AGENTIC_LENS_SUPERVISOR_ENGINE in .env"
else
  echo "WARNING: Could not resolve Supervisor engine. Set AGENTIC_LENS_SUPERVISOR_ENGINE in .env manually (e.g. scripts/get_agent_engine_id.py supervisor)."
fi

# ---------------------------------------------------------------------------
# 8. Optional: grant service usage to engines
# ---------------------------------------------------------------------------
if [[ -f "$ROOT_DIR/scripts/grant_service_usage_to_engines.sh" ]]; then
  echo "Granting service usage to engines..."
  "$ROOT_DIR/scripts/grant_service_usage_to_engines.sh" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 9. Deploy Glass UI and Load Balancer
# ---------------------------------------------------------------------------
echo "Deploying Glass UI and Load Balancer..."
export GCP_PROJECT_ID=$PROJECT_ID
export REGION=$REGION
if ! "$ROOT_DIR/deploy-glass-ui.sh"; then
  echo "Glass UI deploy failed."
  exit 1
fi
if ! "$ROOT_DIR/setup_lb_iap.sh"; then
  echo "Load Balancer setup failed."
  exit 1
fi

# ---------------------------------------------------------------------------
# 10. Summary
# ---------------------------------------------------------------------------
echo ""
echo "========== Deployment complete =========="
echo "AGENTIC_LENS_SUPERVISOR_ENGINE has been set in .env (if resolved)."
echo ""
echo "To test the UI locally:"
echo "  pip install -r requirements.txt  # if needed"
echo "  uvicorn glass_ui_api:app --reload --host 0.0.0.0 --port 8000"
echo "  Then open http://localhost:8000"
echo ""
echo "If any step failed, see agentic-lens/DEPLOY.md and PRODUCTION_CHECKLIST.md."
