#!/usr/bin/env bash
# Step 11: Apply ADK config_agent_utils patch so deploy does not fail with ImportError.
# Run only if agentic-lens/.venv exists (created by local setup). Skip if no venv.
set -euo pipefail
ROOT_DIR="${ROOT_DIR:?}"
VENV_PY="$ROOT_DIR/agentic-lens/.venv/bin/python"
PATCH_SCRIPT="$ROOT_DIR/scripts/patch_adk_config_agent_utils.py"
if [[ -x "$VENV_PY" && -f "$PATCH_SCRIPT" ]]; then
  "$VENV_PY" "$PATCH_SCRIPT" || true
  echo "Patch ADK step done."
else
  echo "Skipping patch ADK (agentic-lens/.venv not found or patch script missing)."
  echo "After creating .venv, run: agentic-lens/.venv/bin/python scripts/patch_adk_config_agent_utils.py"
  echo "Then run ./deploy.sh"
fi
