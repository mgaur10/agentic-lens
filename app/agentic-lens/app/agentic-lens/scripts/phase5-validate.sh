#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
log_phase "Phase 5 — Validation"
require_repo
require_gcloud_project
ensure_venvs

cd "$REPO_ROOT"

if [[ "${RUN_PYTEST:-1}" == "1" ]]; then
  if [[ -f requirements-dev.txt ]]; then
    "$REPO_ROOT/.venv/bin/pip" install -q -r requirements-dev.txt 2>/dev/null || true
  fi
  "$REPO_ROOT/.venv/bin/pytest" tests/ -q 2>&1 | tee "$OUTPUT_DIR/phase5-pytest.log"
fi

if [[ "${RUN_SMOKE:-1}" == "1" && -f "$REPO_ROOT/scripts/smoke_glass_ui_departments.py" ]]; then
  if [[ -f "$OUTPUT_DIR/glass-ui-url.txt" ]]; then
    export GLASS_UI_URL="$(cat "$OUTPUT_DIR/glass-ui-url.txt")"
  else
    export GLASS_UI_URL=$(gcloud run services describe ai-prism-agent-glass-ui \
      --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)' 2>/dev/null || true)
  fi
  # If direct Cloud Run requires authentication, use the URL as the audience for OIDC ID tokens
  if [[ "${GLASS_UI_ALLOW_UNAUTHENTICATED:-0}" != "1" ]]; then
    export IAP_OAUTH_CLIENT_ID="${IAP_OAUTH_CLIENT_ID:-$GLASS_UI_URL}"
  fi
  if [[ -n "${IAP_OAUTH_CLIENT_ID:-}" && -z "${IAP_OAUTH_TOKEN:-}" ]]; then
    echo "Retrieving OIDC ID Token using service account impersonation..."
    IAP_OAUTH_TOKEN=$(gcloud auth print-identity-token \
      --impersonate-service-account="504643566830-compute@developer.gserviceaccount.com" \
      --audiences="$IAP_OAUTH_CLIENT_ID" \
      --include-email \
      --project="$PROJECT_ID" 2>/dev/null || true)
    if [[ -n "$IAP_OAUTH_TOKEN" ]]; then
      export IAP_OAUTH_TOKEN
      echo "OIDC ID Token retrieved successfully."
    else
      echo "Warning: Service account impersonation token generation failed, falling back to ADC."
    fi
  fi
  PROFILE="${SMOKE_PROFILE:-smoke}"
  echo "Smoke profile=$PROFILE URL=$GLASS_UI_URL"
  python3 "$REPO_ROOT/scripts/smoke_glass_ui_departments.py" \
    --profile "$PROFILE" \
    --report "$OUTPUT_DIR/smoke-report.json" 2>&1 | tee "$OUTPUT_DIR/phase5-smoke.log" || true
fi

echo "Phase 5 complete. Review logs in $OUTPUT_DIR/"
