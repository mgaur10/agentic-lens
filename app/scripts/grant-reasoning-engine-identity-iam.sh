#!/usr/bin/env bash
# Grant IAM to Agent Engine runtime principals (reasoningEngines/* path).
#
# Terraform (infra step 06) binds roles to principal://.../agents/agentic_lens_* .
# ADK deploy (deploy.sh) uses principal://.../reasoningEngines/<id> at runtime.
# Without this script, eng_lead → eng_coder peer calls fail with:
#   403 aiplatform.reasoningEngines.get
#
# Run after Phase 2 (all engines deployed) and again after any engine re-create.
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
require_repo
require_gcloud_project
ensure_venvs

PY="$REPO_ROOT/agentic-lens/.venv/bin/python3"
GET_ID="$REPO_ROOT/scripts/get_agent_engine_id.py"

ORG_ID="${ORG_ID:-}"
if [[ -z "$ORG_ID" ]]; then
  ORG_ID=$(gcloud organizations list --format='value(name)' 2>/dev/null | head -1 | sed 's|organizations/||' || true)
fi
[[ -n "$ORG_ID" ]] || die "ORG_ID required (versions.env or gcloud organizations list)"

PN=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SESSION_ROLE="projects/${PROJECT_ID}/roles/reasoningEngineSessionUser"
if ! gcloud iam roles describe reasoningEngineSessionUser --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "WARN: custom role reasoningEngineSessionUser missing — run infra step 06 (IAM terraform) or create role in Console."
  SESSION_ROLE=""
fi

# Agents that invoke peers (need roles/aiplatform.user on RE principal)
ORCH_AGENTS=(supervisor chat eng_lead xray_manager)
ENG_PEERS=(eng_scout eng_coder eng_quality_and_security_reviewer)
XRAY_PEERS=(xray_librarian xray_architect xray_specialist xray_auditor)
OTHER_AGENTS=(events)

ALL_AGENTS=("${ORCH_AGENTS[@]}" "${ENG_PEERS[@]}" "${XRAY_PEERS[@]}" "${OTHER_AGENTS[@]}")

bind_role() {
  local member="$1" role="$2"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$member" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null 2>&1 || echo "  WARN: bind $role (may already exist)"
}

grant_engine_principal() {
  local agent="$1"
  local engine_id="$2"
  local needs_aiplatform="${3:-0}"

  local principal="principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/${engine_id}"
  echo ""
  echo "[$agent] $engine_id"
  echo "  principal: ${principal:0:100}..."

  if [[ "$needs_aiplatform" == "1" ]]; then
    echo "  + roles/aiplatform.user (peer invoke + predict)"
    bind_role "$principal" "roles/aiplatform.user"
  fi
  if [[ -n "$SESSION_ROLE" ]]; then
    echo "  + $SESSION_ROLE"
    bind_role "$principal" "$SESSION_ROLE"
  fi
  echo "  + roles/serviceusage.serviceUsageConsumer"
  bind_role "$principal" "roles/serviceusage.serviceUsageConsumer"
  echo "  + roles/cloudtrace.agent"
  bind_role "$principal" "roles/cloudtrace.agent"
}

needs_aiplatform_user() {
  case "$1" in
    supervisor|chat|eng_lead|xray_manager|eng_scout|eng_coder|eng_quality_and_security_reviewer|events)
      return 0
      ;;
  esac
  return 1
}

echo "Granting Reasoning Engine identity IAM — project=$PROJECT_ID org=$ORG_ID"
echo "Terraform /agents/* principals are unchanged; this fixes runtime /reasoningEngines/* principals."

for agent in "${ALL_AGENTS[@]}"; do
  engine_id=$("$PY" "$GET_ID" "$agent" 2>/dev/null || true)
  if [[ -z "$engine_id" ]]; then
    echo "SKIP $agent — engine not found"
    continue
  fi
  na=0
  if needs_aiplatform_user "$agent"; then
    na=1
  fi
  grant_engine_principal "$agent" "$engine_id" "$na"
done

# Glass UI Cloud Run (calls department engines via ADC)
CR_SA="${PN}-compute@developer.gserviceaccount.com"
echo ""
echo "[glass-ui] Cloud Run default SA $CR_SA"
bind_role "serviceAccount:${CR_SA}" "roles/aiplatform.user"
if [[ -n "$SESSION_ROLE" ]]; then
  bind_role "serviceAccount:${CR_SA}" "$SESSION_ROLE"
fi

echo ""
echo "Done. Redeploy eng_lead/xray_manager if peer env vars changed after first deploy:"
echo "  cd migration/app && agentic-lens/.venv/bin/python3 scripts/merge_peer_engine_env.py ."
echo "  SKIP_PREFLIGHT=1 ./deploy.sh eng_lead xray_manager"
