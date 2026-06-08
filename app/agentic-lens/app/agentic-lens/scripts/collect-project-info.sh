#!/usr/bin/env bash
# Snapshot project metadata for the migration workbook.
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "$0")/_common.sh"
require_repo
require_gcloud_project

OUT="$OUTPUT_DIR/project-info-$(date +%Y%m%d-%H%M%S).txt"
{
  echo "project_id=$PROJECT_ID"
  echo "region=$REGION"
  echo "org_id=${ORG_ID:-}"
  echo "project_number=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  echo "gcloud_account=$(gcloud config get-value account 2>/dev/null || true)"
  echo "--- enabled_apis (sample) ---"
  gcloud services list --enabled --project="$PROJECT_ID" --filter='name:aiplatform OR name:modelarmor OR name:discoveryengine OR name:run' --format='value(name)' 2>/dev/null || true
  echo "--- reasoning_engines ---"
  if [[ -x "$REPO_ROOT/agentic-lens/.venv/bin/python3" ]]; then
    "$REPO_ROOT/agentic-lens/.venv/bin/python3" -c "
import vertexai
from vertexai.preview import reasoning_engines
vertexai.init(project='$PROJECT_ID', location='$REGION')
for e in reasoning_engines.ReasoningEngine.list()[:20]:
    print(e.resource_name, getattr(e, 'display_name', ''))
" 2>/dev/null || echo "(deploy venv / engines not available yet)"
  fi
  echo "--- cloud_run ---"
  gcloud run services list --project="$PROJECT_ID" --region="$REGION" --format='table(name,status.url)' 2>/dev/null || true
} | tee "$OUT"

echo "Wrote $OUT"
echo "Fill artifacts/resource-inventory.csv from this output."
