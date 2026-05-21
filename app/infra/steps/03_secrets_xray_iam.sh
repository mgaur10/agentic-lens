#!/usr/bin/env bash
# Step 03: Create github-pat-token secret (optional) and X-Ray IAM bindings.
set -euo pipefail

ROOT_DIR="${ROOT_DIR:?}"
source "$ROOT_DIR/versions.env"

GITHUB_PAT_SECRET_NAME="${GITHUB_PAT_SECRET_NAME:-github-pat-token}"
GITHUB_PAT_PLACEHOLDER_VALUE="${GITHUB_PAT_PLACEHOLDER_VALUE:-PLACEHOLDER_REPLACE_WITH_REAL_GITHUB_PAT}"

_create_github_pat_secret() {
  local value="$1"
  echo -n "$value" | gcloud secrets create "$GITHUB_PAT_SECRET_NAME" \
    --replication-policy="user-managed" --locations="$REGION" \
    --data-file=- --project="$PROJECT_ID"
}

if ! gcloud secrets describe "$GITHUB_PAT_SECRET_NAME" --project="$PROJECT_ID" &>/dev/null; then
  if [[ -n "${GITHUB_PAT:-}" ]]; then
    _create_github_pat_secret "$GITHUB_PAT"
    echo "Secret $GITHUB_PAT_SECRET_NAME created from GITHUB_PAT."
  elif [[ "${CREATE_GITHUB_PAT_PLACEHOLDER:-0}" == "1" ]]; then
    _create_github_pat_secret "$GITHUB_PAT_PLACEHOLDER_VALUE"
    echo "Secret $GITHUB_PAT_SECRET_NAME created with placeholder value (replace before private-repo use)."
    echo "Replace: echo -n 'ghp_YOUR_TOKEN' | gcloud secrets versions add $GITHUB_PAT_SECRET_NAME --data-file=- --project=$PROJECT_ID"
  elif [[ -t 0 ]]; then
    echo "Secret $GITHUB_PAT_SECRET_NAME not found. Optional: PAT for private repos or higher GitHub rate limits; public repos work without it."
    echo "Or set CREATE_GITHUB_PAT_PLACEHOLDER=1 for a placeholder secret, or GITHUB_PAT env."
    read -s -r -p "Enter GitHub PAT (or Enter to skip): " GITHUB_PAT
    echo
    if [[ -n "${GITHUB_PAT:-}" ]]; then
      _create_github_pat_secret "$GITHUB_PAT"
      echo "Secret $GITHUB_PAT_SECRET_NAME created."
    else
      echo "Skipped $GITHUB_PAT_SECRET_NAME (no secret created)."
    fi
  else
    echo "Non-interactive: skipped $GITHUB_PAT_SECRET_NAME (set GITHUB_PAT or CREATE_GITHUB_PAT_PLACEHOLDER=1)."
  fi
else
  echo "Secret $GITHUB_PAT_SECRET_NAME already exists."
fi

ORG_ID="${ORG_ID:-}"
[[ -z "$ORG_ID" ]] && ORG_ID=$(gcloud projects describe "$PROJECT_ID" --format='value(parent)' 2>/dev/null | sed -n 's|^organizations/||p' || true)
if [[ -z "$ORG_ID" ]]; then
  echo "WARNING: ORG_ID not set. Skipping X-Ray IAM bindings."
  exit 0
fi

LIBRARIAN_PRIN="principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/projects/${PROJECT_ID}/locations/${REGION}/agents/agentic_lens_xray_librarian"
if gcloud secrets describe "$GITHUB_PAT_SECRET_NAME" --project="$PROJECT_ID" &>/dev/null; then
  gcloud secrets add-iam-policy-binding "$GITHUB_PAT_SECRET_NAME" \
    --member="${LIBRARIAN_PRIN}" --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" --quiet 2>/dev/null || true
fi
for name in xray_manager xray_librarian xray_architect xray_specialist xray_auditor; do
  prin="principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/projects/${PROJECT_ID}/locations/${REGION}/agents/agentic_lens_${name}"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="${prin}" --role="roles/logging.logWriter" --quiet 2>/dev/null || true
done
echo "Secrets and X-Ray IAM done."
