#!/usr/bin/env bash
# Pre-install all agent dependencies into agentic-lens/.venv so adk deploy
# doesn't spend time downloading/building wheels during Agent Engine deploys.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_VENV="$ROOT_DIR/agentic-lens/.venv"

echo "Pre-installing agent dependencies into agentic-lens/.venv..."

if [[ ! -x "$AGENT_VENV/bin/python3" ]]; then
  echo "agentic-lens/.venv not found; creating virtualenv and installing base agentic-lens requirements..."
  python3 -m venv "$AGENT_VENV"
  PIP_NO_CACHE_DIR="${PIP_NO_CACHE_DIR:-0}" "$AGENT_VENV/bin/pip" install -U pip
  if [[ -f "$ROOT_DIR/agentic-lens/requirements.txt" ]]; then
    PIP_NO_CACHE_DIR="${PIP_NO_CACHE_DIR:-0}" "$AGENT_VENV/bin/pip" install -r "$ROOT_DIR/agentic-lens/requirements.txt"
  fi
fi

shopt -s nullglob
AGENT_REQS=("$ROOT_DIR"/agentic-lens/agents/*/requirements.txt)
if [[ ${#AGENT_REQS[@]} -eq 0 ]]; then
  echo "No agent requirements.txt files found under agentic-lens/agents; nothing to preinstall."
  exit 0
fi

for req in "${AGENT_REQS[@]}"; do
  agent_name="$(basename "$(dirname "$req")")"
  echo "  - Installing requirements for agent: $agent_name"
  PIP_NO_CACHE_DIR="${PIP_NO_CACHE_DIR:-0}" "$AGENT_VENV/bin/pip" install -r "$req"
done

echo "Agent dependencies pre-installed into agentic-lens/.venv."

