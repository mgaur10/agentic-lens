#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
require_gcloud_project

URL=$(gcloud run services describe ai-prism-agent-glass-ui \
  --region="$REGION" --project="$PROJECT_ID" \
  --format='value(status.url)' 2>/dev/null || true)

if [[ -z "$URL" ]]; then
  echo "Cloud Run service ai-prism-agent-glass-ui not found in $REGION"
  exit 1
fi

echo "Glass UI URL: $URL"

# Private Cloud Run: use identity token when not using public invoke.
AUTH_HEADER=()
if [[ "${GLASS_UI_ALLOW_UNAUTHENTICATED:-0}" != "1" ]]; then
  if _tok=$(gcloud auth print-identity-token 2>/dev/null); then
    AUTH_HEADER=(-H "Authorization: Bearer ${_tok}")
  fi
fi

# Prefer /api/healthz (not intercepted by Cloud Run edge /healthz quirks or SPA catch-all).
HEALTH_PATH="/api/healthz"
echo "GET $URL${HEALTH_PATH}"
curl -sS "${AUTH_HEADER[@]}" -o "$OUTPUT_DIR/healthz.json" -w "HTTP %{http_code}\n" "${URL}${HEALTH_PATH}" || true
echo "GET $URL${HEALTH_PATH}?deep=1"
curl -sS "${AUTH_HEADER[@]}" -o "$OUTPUT_DIR/healthz-deep.json" -w "HTTP %{http_code}\n" "${URL}${HEALTH_PATH}?deep=1" || true

if command -v jq >/dev/null 2>&1; then
  jq . "$OUTPUT_DIR/healthz-deep.json" 2>/dev/null || cat "$OUTPUT_DIR/healthz-deep.json"
fi

echo "$URL" >"$OUTPUT_DIR/glass-ui-url.txt"
echo "Saved URL to $OUTPUT_DIR/glass-ui-url.txt"
