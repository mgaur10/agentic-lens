#!/usr/bin/env bash
# Step 05: Per-department CMEK (key ring + key per department, IAM for RE + Vertex AI).
# Creates keys for supervisor, chat, engineering, xray, events. If setup script
# prints AGENT_ENGINE_KMS_KEY_*=..., they are appended to versions.env automatically.
# For single-key only (legacy), use agentic-lens/security/kms.tf manually.
set -euo pipefail
ROOT_DIR="${ROOT_DIR:?}"
VERSIONS_FILE="$ROOT_DIR/versions.env"
source "$VERSIONS_FILE"

CMEK_SCRIPT="$ROOT_DIR/scripts/setup_cmek_per_department.sh"
if [[ ! -f "$CMEK_SCRIPT" ]]; then
  echo "setup_cmek_per_department.sh not found, skipping CMEK (deploy works without CMEK)."
  echo "CMEK step done (skipped)."
  exit 0
fi

CMEK_OUT=$(mktemp)
trap 'rm -f "$CMEK_OUT"' EXIT
"$CMEK_SCRIPT" 2>&1 | tee "$CMEK_OUT" || true

# Append any AGENT_ENGINE_KMS_KEY_*=... lines to versions.env if not already set
while IFS= read -r line; do
  key="${line%%=*}"
  if [[ "$key" =~ ^AGENT_ENGINE_KMS_KEY_ ]] && ! grep -q "^${key}=" "$VERSIONS_FILE" 2>/dev/null; then
    echo "$line" >> "$VERSIONS_FILE"
    echo "Appended to versions.env: $key"
  fi
done < <(grep -oE '^AGENT_ENGINE_KMS_KEY_[A-Z_]+=projects/[^[:space:]]+' "$CMEK_OUT" 2>/dev/null || true)

echo "CMEK step done."
