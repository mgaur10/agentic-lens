#!/usr/bin/env bash
# Run all migration phases in order with confirmation gates.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

echo "Agentic Prism — greenfield migration (phased)"
echo "Migration dir: $MIGRATION_DIR"
echo "App root: $REPO_ROOT"
copy_templates_if_missing

"$SCRIPT_DIR/phase0-preflight.sh"
gate_confirm "Phase 0"

"$SCRIPT_DIR/phase1-infra.sh"
gate_confirm "Phase 1"

"$SCRIPT_DIR/phase2-agents.sh"
gate_confirm "Phase 2"

if [[ "${SKIP_AGENT_GATEWAY:-0}" == "1" ]]; then
  echo "SKIP_AGENT_GATEWAY=1 — Phase 3 (Agent Gateway) skipped; using direct Reasoning Engine connectivity."
  "$SCRIPT_DIR/phase3-agent-gateway.sh"
else
  "$SCRIPT_DIR/phase3-agent-gateway.sh"
  gate_confirm "Phase 3"
fi

"$SCRIPT_DIR/phase4-glass-ui.sh"
gate_confirm "Phase 4"

"$SCRIPT_DIR/phase5-validate.sh"

echo ""
echo "Phase 6: ./scripts/phase6-production-iam.sh (RE identity IAM) + artifacts/iap-load-balancer.md (IAP/LB)"
echo "Sign-off: CHECKLIST.md"
echo "Done."
