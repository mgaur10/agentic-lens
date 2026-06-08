#!/usr/bin/env bash
# Step 12: VPC Service Controls (VPC-SC) — Access Context Manager policy, access level, and service perimeter.
# Ingress and egress rules allow only the specified user(s). Requires ORG_ID (project must be in an org).
#
# Set allowed identity via env (one of):
#   VPC_SC_ALLOWED_USER_EMAIL=you@example.com     → used as user:you@example.com
#   VPC_SC_ALLOWED_MEMBERS=user:a@b.com,user:c@d.com  → used as-is (comma-separated)
# If unset, uses current gcloud account: $(gcloud config get-value account)
set -euo pipefail

ROOT_DIR="${ROOT_DIR:?}"
AGENTIC_LENS="${AGENTIC_LENS:?}"
source "$ROOT_DIR/versions.env"

if [[ -z "${ORG_ID:-}" ]]; then
  echo "Skipping step 12 (VPC-SC): ORG_ID not set. VPC-SC requires an organization."
  echo "Set ORG_ID in versions.env or use an organization project, then re-run."
  exit 0
fi

# Resolve allowed_members for Terraform (JSON array of "user:email" or "serviceAccount:...")
if [[ -n "${VPC_SC_ALLOWED_MEMBERS:-}" ]]; then
  # Comma-separated list; ensure each has user: or serviceAccount: prefix
  members_json="["
  first=1
  IFS=',' read -ra parts <<< "$VPC_SC_ALLOWED_MEMBERS"
  for m in "${parts[@]}"; do
    m=$(echo "$m" | xargs)
    [[ -z "$m" ]] && continue
    if [[ "$m" != user:* && "$m" != serviceAccount:* ]]; then
      m="user:$m"
    fi
    [[ $first -eq 0 ]] && members_json+=","
    members_json+="\"$m\""
    first=0
  done
  members_json+="]"
  if [[ "$members_json" == "[]" ]]; then
    echo "ERROR: VPC_SC_ALLOWED_MEMBERS is set but no valid members parsed."
    exit 1
  fi
elif [[ -n "${VPC_SC_ALLOWED_USER_EMAIL:-}" ]]; then
  email=$(echo "$VPC_SC_ALLOWED_USER_EMAIL" | xargs)
  members_json="[\"user:${email}\"]"
else
  current=$(gcloud config get-value account 2>/dev/null || true)
  if [[ -n "$current" ]]; then
    members_json="[\"user:${current}\"]"
    echo "Using current gcloud account for VPC-SC allowed identity: $current"
  elif [[ ! -t 0 ]]; then
    echo "Skipping step 12 (VPC-SC): no TTY and VPC_SC_ALLOWED_USER_EMAIL / VPC_SC_ALLOWED_MEMBERS not set."
    exit 0
  else
    echo "Set VPC_SC_ALLOWED_USER_EMAIL (e.g. you@example.com) or VPC_SC_ALLOWED_MEMBERS (comma-separated user: or serviceAccount:)."
    read -r -p "Enter email for allowed ingress/egress (user: will be prefixed): " email
    if [[ -z "${email:-}" ]]; then
      echo "Skipping step 12 (VPC-SC): no allowed identity provided."
      exit 0
    fi
    members_json="[\"user:${email}\"]"
  fi
fi

echo "VPC-SC allowed members: $members_json"

# Enable API (idempotent)
gcloud services enable accesscontextmanager.googleapis.com --project="$PROJECT_ID" 2>/dev/null || true

VPC_SC_DIR="$AGENTIC_LENS/security/vpc_sc"
cd "$VPC_SC_DIR"
terraform init -input=false
terraform apply \
  -var="project_id=$PROJECT_ID" \
  -var="org_id=$ORG_ID" \
  -var="allowed_members=$members_json" \
  -auto-approve -input=false

echo "VPC-SC step done. Perimeter restricts access to allowed members only (ingress and egress)."
