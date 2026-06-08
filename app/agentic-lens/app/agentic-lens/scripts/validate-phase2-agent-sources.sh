#!/usr/bin/env bash
# Preflight: agent sources required for greenfield Phase 2 (12 Reasoning Engines).
# Run from migration/: ./scripts/validate-phase2-agent-sources.sh
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
require_repo

AGENTS_DIR="$REPO_ROOT/agentic-lens/agents"
errors=0

fail() {
  echo "ERROR: $*" >&2
  errors=1
}

echo "Validating Phase 2 agent sources under $AGENTS_DIR ..."

if [[ ! -f "$AGENTS_DIR/eng_scout/root_agent.yaml" ]]; then
  fail "eng_scout/root_agent.yaml missing (required for ADK config deploy path)"
fi

if grep -qE 'config\.yaml' "$AGENTS_DIR/eng_scout/agent.py" \
  && ! grep -qE 'root_agent\.yaml' "$AGENTS_DIR/eng_scout/agent.py"; then
  fail "eng_scout/agent.py must load root_agent.yaml (not config.yaml only)"
fi

# Supervisor sub_agents import these modules at container startup (root_agent.yaml code: refs).
for agent in chat xray_manager; do
  f="$AGENTS_DIR/$agent/agent.py"
  if [[ ! -f "$f" ]]; then
    fail "$agent/agent.py missing"
    continue
  fi
  if grep -qE 'LlmAgent\.from_config' "$f"; then
    fail "$agent/agent.py still uses LlmAgent.from_config — use config_agent_utils.from_config"
  fi
done

# cloudpickle pin (Agent Engine runtime)
for req in "$AGENTS_DIR"/*/requirements.txt; do
  [[ -f "$req" ]] || continue
  if grep -qE '^cloudpickle==3\.0\.0' "$req" 2>/dev/null; then
    fail "$(basename "$(dirname "$req")")/requirements.txt pins cloudpickle==3.0.0 (use >=2.0.0,<3)"
  fi
done

if [[ "$errors" -ne 0 ]]; then
  echo ""
  echo "Fix sources in the repo, then: ./sync-app-bundle.sh (from migration/)"
  exit 1
fi

echo "OK — Phase 2 agent sources look ready."
