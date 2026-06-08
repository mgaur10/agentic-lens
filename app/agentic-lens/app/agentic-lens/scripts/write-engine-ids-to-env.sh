#!/usr/bin/env bash
# Resolve Reasoning Engine resource names and write to repo .env
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
require_repo
require_gcloud_project
ensure_venvs

PY="$REPO_ROOT/agentic-lens/.venv/bin/python3"
GET_ID="$REPO_ROOT/scripts/get_agent_engine_id.py"
UPDATE="$REPO_ROOT/scripts/update_env.py"

[[ -x "$PY" ]] || die "Missing agentic-lens venv"

agents=(supervisor chat eng_lead events xray_manager eng_scout eng_coder eng_quality_and_security_reviewer xray_librarian xray_architect xray_specialist xray_auditor)
declare -A MAP=(
  [supervisor]=AGENTIC_LENS_SUPERVISOR_ENGINE
  [chat]=CHAT_ENGINE_ID
  [eng_lead]=ENG_ENGINE_ID
  [events]=EVENTS_ENGINE_ID
  [xray_manager]=XRAY_ENGINE_ID
  [eng_scout]=AGENTIC_LENS_ENGINE_SCOUT
  [eng_coder]=AGENTIC_LENS_ENGINE_CODER
  [eng_quality_and_security_reviewer]=AGENTIC_LENS_ENGINE_QUALITY_AND_SECURITY_REVIEWER
  [xray_librarian]=AGENTIC_LENS_ENGINE_XRAY_LIBRARIAN
  [xray_architect]=AGENTIC_LENS_ENGINE_XRAY_ARCHITECT
  [xray_specialist]=AGENTIC_LENS_ENGINE_XRAY_SPECIALIST
  [xray_auditor]=AGENTIC_LENS_ENGINE_XRAY_AUDITOR
)


OUT_ENV="$OUTPUT_DIR/engine-ids.env"
: >"$OUT_ENV"

for a in "${agents[@]}"; do
  id=$("$PY" "$GET_ID" "$a" 2>/dev/null || true)
  if [[ -z "$id" ]]; then
    echo "WARN: no engine for $a"
    continue
  fi
  key="${MAP[$a]}"
  echo "$key=$id" | tee -a "$OUT_ENV"
  if [[ -f "$UPDATE" && -f "$ENV_FILE" ]]; then
    "$REPO_ROOT/.venv/bin/python" "$UPDATE" "$key" "$id" "$ENV_FILE" 2>/dev/null || true
  fi
done

# Mirror supervisor to SUPERVISOR_ENGINE_ID
sup=$("$PY" "$GET_ID" supervisor 2>/dev/null || true)
if [[ -n "$sup" && -f "$UPDATE" && -f "$ENV_FILE" ]]; then
  "$REPO_ROOT/.venv/bin/python" "$UPDATE" "SUPERVISOR_ENGINE_ID" "$sup" "$ENV_FILE" 2>/dev/null || true
fi

# Optional snapshot for inventory (ignore if artifacts/ is read-only)
cp "$OUT_ENV" "$MIGRATION_DIR/artifacts/engine-ids-filled.env.example" 2>/dev/null || true
echo ""
echo "Engine IDs written to $ENV_FILE (if update_env.py available) and $OUT_ENV"
echo "Copy any missing keys from $OUT_ENV into .env manually."
