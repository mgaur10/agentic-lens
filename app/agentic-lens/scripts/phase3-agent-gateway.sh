#!/usr/bin/env bash
# Phase 3 — Agent Gateway / Registry (manual workbook), or skip for direct connectivity.
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
log_phase "Phase 3 — Agent Gateway"

if [[ "${SKIP_AGENT_GATEWAY:-0}" == "1" ]]; then
  echo "SKIP_AGENT_GATEWAY=1 — skipping Agent Gateway and Registry."
  echo "Connectivity: Glass UI → Cloud Run → Vertex Reasoning Engines (direct API)."
  echo "  See app/backend/agent_engine_client.py — no gateway URL in app/.env."
  echo "phase3_skipped_direct_connectivity=true" >>"$OUTPUT_DIR/phases.status"
  echo "Phase 3 skipped (approved for this migration)."
  exit 0
fi

WB="$MIGRATION_DIR/artifacts/agent-gateway-workbook.md"
echo "This phase is not automated in the application repo."
echo "Complete: $WB"
echo ""
echo "Suggested order:"
echo "  1. Document gateway resource ID in resource-inventory.csv"
echo "  2. Configure Model A tool policies (GitHub, googleapis, Discovery Engine)"
echo "  3. Register supervisor + department engines in Agent Registry"
echo "  4. Validate after Phase 5 with an X-Ray query"
echo ""
if [[ -f "$WB" ]]; then
  sed -n '1,80p' "$WB"
fi

read -r -p "Mark Phase 3 complete? [y/N] " reply
[[ "${reply^^}" == "Y" ]] && echo "phase3_complete=true" >>"$OUTPUT_DIR/phases.status" || true
